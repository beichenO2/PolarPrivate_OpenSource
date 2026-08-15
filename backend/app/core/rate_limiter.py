"""Per-service rate limiting for the /v1 LLM gateway.

Phase 1: Semaphore (max concurrent) + TokenBucket (RPM) per binding service.
Phase 2: Adaptive throttle based on upstream 429/5xx feedback.
Phase 3: BurstAbsorber queue + cross-binding overflow.

All state is in-memory; a process restart resets budgets (acceptable for
a single-instance gateway like PolarPrivate).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.logging_config import get_logger

if TYPE_CHECKING:
    import httpx

_LOG = get_logger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ServiceLimitConfig:
    max_concurrent: int
    rpm: int
    burst: int = 0  # Phase 3: extra burst tokens above rpm


_DEFAULT_LIMITS = ServiceLimitConfig(max_concurrent=3, rpm=20)

_SERVICE_LIMITS: dict[str, ServiceLimitConfig] = {
    "llm.glm51.enterprise": ServiceLimitConfig(max_concurrent=10, rpm=60),
    "llm.aliyun.codingplan": ServiceLimitConfig(max_concurrent=8, rpm=60),
    "llm.aliyun.dashscope":  ServiceLimitConfig(max_concurrent=50, rpm=600),
    "llm.minimax":           ServiceLimitConfig(max_concurrent=12, rpm=60),
}

_ENV_PREFIX = "PRIVPORTAL_RL_"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except (ValueError, TypeError):
        return default


# ── Cooldown / adaptive-throttle tuning ──────────────────────────────────────
# Cooldown is purely a *pacing* signal now: after an upstream 429 we briefly slow
# new requests to the same service. acquire() WAITS through it — it is never a
# rejection. The retrying request itself honours the upstream Retry-After inline
# (see v1_gateway), so the cooldown only spaces out *concurrent* callers.
#   - default cooldown: used when upstream sends no Retry-After
#   - cap: bounds how long concurrent callers pace, even if Retry-After is huge
#   - RPM floor: adaptive throttle can't collapse a service to ~1 req/min
_COOLDOWN_DEFAULT_SEC = _env_float("PRIVPORTAL_RL_COOLDOWN_SEC", 5.0)
_COOLDOWN_MAX_SEC = _env_float("PRIVPORTAL_RL_COOLDOWN_MAX_SEC", 30.0)
_RPM_FLOOR_RATIO = _env_float("PRIVPORTAL_RL_RPM_FLOOR_RATIO", 0.5)
_RPM_FLOOR_MIN = _env_float("PRIVPORTAL_RL_RPM_FLOOR_MIN", 10.0)


def _load_env_overrides() -> None:
    """Override _SERVICE_LIMITS from env: PRIVPORTAL_RL_<SERVICE>=concurrent,rpm."""
    for key, val in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        svc = key[len(_ENV_PREFIX):].lower().replace("__", ".")
        parts = val.split(",")
        if len(parts) >= 2:
            try:
                _SERVICE_LIMITS[svc] = ServiceLimitConfig(
                    max_concurrent=int(parts[0]),
                    rpm=int(parts[1]),
                )
            except ValueError:
                pass


_load_env_overrides()


# ── Token Bucket ─────────────────────────────────────────────────────────────

class TokenBucket:
    """Fixed-rate token bucket: refills *rpm* tokens per 60-second window.

    Uses a continuous-refill model for smooth rate limiting rather than
    bursty per-window resets.
    """

    __slots__ = ("_rpm", "_tokens", "_max_tokens", "_last_refill")

    def __init__(self, rpm: int) -> None:
        self._rpm = max(1, rpm)
        self._max_tokens = float(rpm)
        self._tokens = float(rpm)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        added = elapsed * (self._rpm / 60.0)
        self._tokens = min(self._max_tokens, self._tokens + added)
        self._last_refill = now

    def try_acquire(self) -> bool:
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    def seconds_until_token(self) -> float:
        self._refill()
        if self._tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self._tokens
        return deficit / (self._rpm / 60.0)

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens

    @property
    def rpm(self) -> int:
        return self._rpm

    def set_rpm(self, new_rpm: int) -> None:
        self._refill()
        self._rpm = max(1, new_rpm)
        self._max_tokens = float(self._rpm)
        self._tokens = min(self._tokens, self._max_tokens)


# ── Sliding Window Stats (Phase 2) ──────────────────────────────────────────

class SlidingWindowStats:
    """Track success / 429 / error counts in a rolling 60-second window."""

    __slots__ = ("_window_sec", "_events")

    def __init__(self, window_sec: float = 60.0) -> None:
        self._window_sec = window_sec
        self._events: deque[tuple[float, str]] = deque()

    def record(self, event_type: str) -> None:
        """event_type: 'ok' | '429' | 'error'"""
        self._events.append((time.monotonic(), event_type))
        self._trim()

    def _trim(self) -> None:
        cutoff = time.monotonic() - self._window_sec
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def counts(self) -> dict[str, int]:
        self._trim()
        out: dict[str, int] = {"ok": 0, "429": 0, "error": 0}
        for _, t in self._events:
            out[t] = out.get(t, 0) + 1
        return out

    @property
    def total(self) -> int:
        self._trim()
        return len(self._events)

    @property
    def rate_429(self) -> float:
        c = self.counts()
        total = sum(c.values())
        return c["429"] / total if total > 0 else 0.0


# ── ServiceBudget ────────────────────────────────────────────────────────────

class ServiceBudget:
    """Per-binding rate limiter: Semaphore (concurrency) + TokenBucket (RPM).

    Cooldown: after upstream 429, all new requests wait until cooldown expires.
    """

    def __init__(self, service_name: str, config: ServiceLimitConfig) -> None:
        self.service_name = service_name
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._bucket = TokenBucket(config.rpm)
        self._cooldown_until: float = 0.0
        self._stats = SlidingWindowStats()
        self._in_flight = 0
        self._total_acquired = 0
        self._total_rejected = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block only on the concurrency semaphore (connection safety).

        Soft limiting — there is **no local RPM self-throttling and no cooldown
        wait**. We never pre-emptively cap our own request rate below what a
        subscription actually allows (that would throttle ourselves while other
        paid subscriptions sit idle). The real upstream limit is discovered via a
        429, which sets a short cooldown used purely as a *routing signal*: the
        gateway then diverts new traffic for that tier to other, non-cooling
        subscriptions (see model_routing.select_service_by_weight skip_services).

        The semaphore is only here so we don't open an unbounded number of
        simultaneous sockets to a single provider — it is connection management,
        not rate limiting, and is sized generously.
        """
        await self._semaphore.acquire()
        self._in_flight += 1
        self._total_acquired += 1

    def release(self, *, is_error: bool = False, is_429: bool = False) -> None:
        """Release the semaphore slot and record outcome."""
        self._in_flight = max(0, self._in_flight - 1)
        self._semaphore.release()

        if is_429:
            self._stats.record("429")
        elif is_error:
            self._stats.record("error")
        else:
            self._stats.record("ok")

    def set_cooldown(self, seconds: float) -> None:
        """Freeze this service for *seconds* (after upstream 429)."""
        target = time.monotonic() + seconds
        if target > self._cooldown_until:
            self._cooldown_until = target
            _LOG.warning(
                "rate_limit_cooldown",
                service=self.service_name,
                cooldown_sec=seconds,
            )

    @property
    def is_cooling_down(self) -> bool:
        return time.monotonic() < self._cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        r = self._cooldown_until - time.monotonic()
        return max(0.0, r)

    # ── Phase 2: Adaptive throttle ───────────────────────────────────────

    def maybe_adjust(self) -> None:
        """No-op: adaptive *self*-throttling is intentionally disabled.

        Previously this lowered our own RPM when upstream 429s rose — i.e. it
        throttled our own traffic instead of using spare capacity on other
        subscriptions. Under the soft-routing model a 429 sets a cooldown and the
        router diverts to other subscriptions, so there is nothing to "tune" here.
        Kept as a no-op so the periodic adjust loop and call sites stay valid.
        """
        return

    def stats_snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot for the /api/rate-limits endpoint."""
        counts = self._stats.counts()
        return {
            "service": self.service_name,
            "in_flight": self._in_flight,
            "max_concurrent": self._config.max_concurrent,
            "rpm_configured": self._config.rpm,
            "rpm_current": self._bucket.rpm,
            "bucket_available": round(self._bucket.available, 1),
            "cooldown_remaining_sec": round(self.cooldown_remaining, 1),
            "window_60s": counts,
            "total_acquired": self._total_acquired,
            "total_rejected": self._total_rejected,
        }


# ── BurstAbsorber (Phase 3) ─────────────────────────────────────────────────

class BurstAbsorber:
    """Bounded async queue: hold requests when budget exhausted instead of
    rejecting immediately. Waiters wake when a token becomes available."""

    def __init__(self, max_queue: int = 20, max_wait_sec: float = 15.0) -> None:
        self._max_queue = max_queue
        self._max_wait = max_wait_sec
        self._waiters: deque[asyncio.Event] = deque()

    @property
    def queue_depth(self) -> int:
        return len(self._waiters)

    @property
    def is_full(self) -> bool:
        return len(self._waiters) >= self._max_queue

    async def wait_for_budget(self, budget: ServiceBudget) -> bool:
        """Block until budget.acquire() succeeds or timeout."""
        if self.is_full:
            return False
        event = asyncio.Event()
        self._waiters.append(event)
        try:
            deadline = time.monotonic() + self._max_wait
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                acquired = await budget.acquire(timeout=min(remaining, 2.0))
                if acquired:
                    return True
                try:
                    await asyncio.wait_for(event.wait(), timeout=min(remaining, 2.0))
                except asyncio.TimeoutError:
                    pass
                event.clear()
        finally:
            try:
                self._waiters.remove(event)
            except ValueError:
                pass

    def notify_one(self) -> None:
        """Wake one waiter (called after a release)."""
        for w in self._waiters:
            if not w.is_set():
                w.set()
                break


# ── Fair Scheduler (Phase 2) ─────────────────────────────────────────────────

_CLIENT_PRIORITY: dict[str, int] = {
    "polarclaw": 10,    # real-time chat — highest
    "polarui": 8,       # user-facing UI
    "autooffice": 5,    # background document generation
    "knowlever": 3,     # batch knowledge compilation
    "digist": 3,        # batch digest
    "sotgent": 2,       # monitoring / admin
}
_DEFAULT_PRIORITY = 5


@dataclass
class ClientSlot:
    client_id: str
    priority: int
    in_flight: int = 0
    total: int = 0
    last_seen: float = field(default_factory=time.monotonic)


class FairScheduler:
    """Weighted fair queueing: higher-priority clients get tokens first when
    contention exists. Without contention, all clients are served equally."""

    def __init__(self) -> None:
        self._clients: dict[str, ClientSlot] = {}

    def register(self, client_id: str) -> ClientSlot:
        cid = (client_id or "unknown").lower().strip()
        if cid not in self._clients:
            prio = _DEFAULT_PRIORITY
            for prefix, p in _CLIENT_PRIORITY.items():
                if cid.startswith(prefix):
                    prio = p
                    break
            self._clients[cid] = ClientSlot(client_id=cid, priority=prio)
        slot = self._clients[cid]
        slot.last_seen = time.monotonic()
        return slot

    def acquire(self, client_id: str) -> None:
        slot = self.register(client_id)
        slot.in_flight += 1
        slot.total += 1

    def release(self, client_id: str) -> None:
        slot = self._clients.get((client_id or "unknown").lower().strip())
        if slot:
            slot.in_flight = max(0, slot.in_flight - 1)

    def should_defer(self, client_id: str, service_budget: ServiceBudget) -> bool:
        """Return True if this client should wait because a higher-priority
        client is also contending for the same service.

        Only applies when the service is near capacity (>80% in-flight).
        """
        if service_budget._in_flight < service_budget._config.max_concurrent * 0.8:
            return False
        slot = self.register(client_id)
        for other in self._clients.values():
            if other.client_id != slot.client_id and other.in_flight > 0 and other.priority > slot.priority:
                return True
        return False

    def stats_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            cid: {
                "priority": s.priority,
                "in_flight": s.in_flight,
                "total": s.total,
                "idle_sec": round(now - s.last_seen, 1),
            }
            for cid, s in sorted(self._clients.items())
            if now - s.last_seen < 3600
        }


# ── RateLimitManager (singleton) ─────────────────────────────────────────────

class RateLimitManager:
    """Process-wide singleton managing ServiceBudget instances + FairScheduler."""

    def __init__(self) -> None:
        self._budgets: dict[str, ServiceBudget] = {}
        self._absorbers: dict[str, BurstAbsorber] = {}
        self._scheduler = FairScheduler()
        self._adjust_task: asyncio.Task | None = None

    @property
    def scheduler(self) -> FairScheduler:
        return self._scheduler

    def get_budget(self, service_name: str) -> ServiceBudget:
        if service_name not in self._budgets:
            config = _SERVICE_LIMITS.get(service_name, _DEFAULT_LIMITS)
            self._budgets[service_name] = ServiceBudget(service_name, config)
        return self._budgets[service_name]

    def get_absorber(self, service_name: str) -> BurstAbsorber:
        if service_name not in self._absorbers:
            self._absorbers[service_name] = BurstAbsorber()
        return self._absorbers[service_name]

    async def acquire(
        self,
        service_name: str,
        client_id: str = "",
    ) -> None:
        """Acquire local capacity, blocking (pacing) until available.

        Never rejects: there is no acquire timeout. Local rate limiting only
        throttles throughput; it must not turn into a client error. Callers that
        hit a genuine *upstream* limit handle it separately (wait + retry).
        """
        budget = self.get_budget(service_name)

        # Fair scheduling: low-priority clients yield briefly when near capacity,
        # then still proceed (we pace, we do not drop them).
        if client_id and self._scheduler.should_defer(client_id, budget):
            await asyncio.sleep(0.25)

        self._scheduler.acquire(client_id or "unknown")
        await budget.acquire()

    def release(
        self,
        service_name: str,
        *,
        client_id: str = "",
        is_error: bool = False,
        is_429: bool = False,
        retry_after: int | None = None,
    ) -> None:
        budget = self.get_budget(service_name)
        budget.release(is_error=is_error, is_429=is_429)

        self._scheduler.release(client_id or "unknown")

        if is_429 and retry_after:
            # Respect upstream Retry-After but cap it under the gateway's acquire
            # timeout so callers can wait the cooldown out instead of failing.
            budget.set_cooldown(min(float(retry_after), _COOLDOWN_MAX_SEC))
        elif is_429:
            budget.set_cooldown(_COOLDOWN_DEFAULT_SEC)

        absorber = self._absorbers.get(service_name)
        if absorber:
            absorber.notify_one()

    def ensure_all_configured(self) -> None:
        """Pre-create budgets for all services in _SERVICE_LIMITS so they
        appear in stats even before receiving their first request."""
        for svc_name in _SERVICE_LIMITS:
            self.get_budget(svc_name)

    def get_stats(self) -> dict[str, Any]:
        """Aggregate stats for all tracked services + clients."""
        return {
            "services": {
                name: budget.stats_snapshot()
                for name, budget in sorted(self._budgets.items())
            },
            "absorbers": {
                name: {"queue_depth": absorber.queue_depth}
                for name, absorber in sorted(self._absorbers.items())
                if absorber.queue_depth > 0
            },
            "clients": self._scheduler.stats_snapshot(),
        }

    def start_adaptive_loop(self) -> None:
        """Start background task that periodically adjusts RPM (Phase 2)."""
        if self._adjust_task is not None:
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(30)
                for budget in self._budgets.values():
                    budget.maybe_adjust()

        self._adjust_task = asyncio.create_task(_loop())

    def stop(self) -> None:
        if self._adjust_task:
            self._adjust_task.cancel()
            self._adjust_task = None


# ── Module-level singleton ───────────────────────────────────────────────────

_manager: RateLimitManager | None = None


def get_rate_limiter() -> RateLimitManager:
    global _manager
    if _manager is None:
        _manager = RateLimitManager()
    return _manager


def parse_retry_after(headers: httpx.Headers | dict) -> int | None:
    """Extract Retry-After from upstream response headers."""
    val = None
    if hasattr(headers, "get"):
        val = headers.get("retry-after") or headers.get("Retry-After")
    if val is None:
        return None
    try:
        return max(1, int(float(val)))
    except (ValueError, TypeError):
        return None
