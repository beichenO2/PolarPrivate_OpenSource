"""Pressure test: find real concurrency / RPM limits per API key.

Strategy:
  1. Ramp up concurrency: 2, 5, 8, 10, 12, 15, 18, 20, 25, 30
  2. Stop ramping when >50% of requests fail (429/timeout/error)
  3. Binary search between last-100%-ok and first-fail to find exact threshold
  4. RPM test: sequential requests until 429
  5. 15 min cooldown between rounds, 3 rounds per service

Usage:
    python tests/test_concurrency_limits.py [service_name] [--rounds N]
"""
import asyncio
import time
import json
import sys
import os

import httpx

PP_PORT = os.environ.get("POLARPRIVATE_PORT", "8005")
PP_BASE = f"http://127.0.0.1:{PP_PORT}"
ENDPOINT = f"{PP_BASE}/v1/chat/completions"

SERVICE_MODEL_MAP = {
    "llm.glm51.enterprise": "0000",
    "llm.aliyun.codingplan": "V0000",
    "llm.minimax": "0110",
}

COOLDOWN_MINUTES = 15
DEFAULT_ROUNDS = 3
REQUEST_TIMEOUT = 30.0


async def fire_one(client: httpx.AsyncClient, model: str, idx: int) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": f"Say just the number {idx}"}],
        "max_tokens": 5,
        "stream": False,
    }
    t0 = time.monotonic()
    try:
        resp = await client.post(
            ENDPOINT, json=body,
            headers={"X-Client-Id": "pressure-test"},
            timeout=REQUEST_TIMEOUT,
        )
        elapsed = time.monotonic() - t0
        status = resp.status_code
        retry_after = resp.headers.get("retry-after")

        if status == 200:
            kind = "ok"
        elif status == 429:
            kind = "429"
        elif status >= 500:
            kind = "server_error"
        else:
            kind = f"http_{status}"

        return {"idx": idx, "kind": kind, "status": status, "elapsed": round(elapsed, 2),
                "retry_after": retry_after}
    except httpx.TimeoutException:
        return {"idx": idx, "kind": "timeout", "status": "timeout",
                "elapsed": round(time.monotonic() - t0, 2)}
    except Exception as e:
        return {"idx": idx, "kind": "error", "status": "error",
                "elapsed": round(time.monotonic() - t0, 2), "error": str(e)}


async def burst_test(model: str, n: int) -> dict:
    """Fire n concurrent requests, return summary."""
    async with httpx.AsyncClient() as client:
        tasks = [fire_one(client, model, i) for i in range(n)]
        results = await asyncio.gather(*tasks)

    counts = {}
    for r in results:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1

    ok = counts.get("ok", 0)
    r429 = counts.get("429", 0)
    timeout = counts.get("timeout", 0)
    fail = n - ok

    avg_ok_time = 0
    ok_times = [r["elapsed"] for r in results if r["kind"] == "ok"]
    if ok_times:
        avg_ok_time = sum(ok_times) / len(ok_times)

    return {
        "n": n, "ok": ok, "429": r429, "timeout": timeout,
        "fail": fail, "avg_ok_time": round(avg_ok_time, 2),
        "counts": counts, "results": results,
    }


async def find_concurrency_limit(service: str, model: str) -> dict:
    print(f"\n{'='*60}")
    print(f"Concurrency test: {service} (model={model})")
    print(f"{'='*60}")

    ramp_levels = [2, 5, 8, 10, 12, 15, 18, 20, 25, 30]
    last_all_ok = 0
    first_fail = None

    for n in ramp_levels:
        print(f"\n  Burst n={n}...", end=" ", flush=True)
        result = await burst_test(model, n)

        ok = result["ok"]
        fail = result["fail"]
        print(f"ok={ok} fail={fail} ({result['counts']}) avg_ok={result['avg_ok_time']}s")

        if fail == 0:
            last_all_ok = n
        else:
            if first_fail is None:
                first_fail = n
            if fail > n * 0.5:
                print(f"  >50% failed at n={n}, stopping ramp.")
                break

        await asyncio.sleep(3)

    if first_fail is None:
        print(f"\n  All levels passed! Limit > {ramp_levels[-1]}")
        return {"service": service, "max_concurrent_ok": ramp_levels[-1],
                "confidence": "lower_bound", "last_all_ok": last_all_ok}

    lo, hi = last_all_ok, first_fail
    print(f"\n  Binary search between {lo} and {hi}...")

    while hi - lo > 1:
        mid = (lo + hi) // 2
        await asyncio.sleep(3)
        print(f"    Testing n={mid}...", end=" ", flush=True)
        result = await burst_test(model, mid)
        print(f"ok={result['ok']} fail={result['fail']}")

        if result["fail"] == 0:
            lo = mid
        else:
            hi = mid

    print(f"  Concurrency limit: {lo} (all ok) → {hi} (starts failing)")
    return {"service": service, "max_concurrent_ok": lo, "first_fail_at": hi,
            "confidence": "binary_search"}


async def rpm_test(model: str, max_requests: int = 60) -> dict:
    """Sequential requests to find RPM limit."""
    print(f"\n  RPM test (up to {max_requests} sequential requests)...")
    ok = 0
    r429 = 0
    errors = 0
    t0 = time.monotonic()

    async with httpx.AsyncClient() as client:
        for i in range(max_requests):
            result = await fire_one(client, model, i)
            if result["kind"] == "ok":
                ok += 1
            elif result["kind"] == "429":
                r429 += 1
                if r429 == 1:
                    elapsed_at_first_429 = time.monotonic() - t0
                    print(f"    First 429 at request #{i+1} (after {ok} ok, {elapsed_at_first_429:.1f}s)")
                if r429 >= 3:
                    print(f"    Stopping after {r429} 429s")
                    break
            else:
                errors += 1
                if errors >= 3:
                    print(f"    Stopping after {errors} errors")
                    break

    elapsed = time.monotonic() - t0
    effective_rpm = round(ok / elapsed * 60, 1) if elapsed > 0 else 0
    print(f"    Total: {ok} ok, {r429} 429, {errors} err in {elapsed:.1f}s → ~{effective_rpm} RPM")

    return {"ok": ok, "r429": r429, "errors": errors, "elapsed": round(elapsed, 1),
            "effective_rpm": effective_rpm}


async def main():
    services_to_test = list(SERVICE_MODEL_MAP.keys())
    rounds = DEFAULT_ROUNDS

    if len(sys.argv) > 1 and sys.argv[1] != "--rounds":
        target = sys.argv[1]
        if target in SERVICE_MODEL_MAP:
            services_to_test = [target]
        else:
            print(f"Unknown service: {target}")
            print(f"Available: {list(SERVICE_MODEL_MAP.keys())}")
            return

    for arg_i, arg in enumerate(sys.argv):
        if arg == "--rounds" and arg_i + 1 < len(sys.argv):
            rounds = int(sys.argv[arg_i + 1])

    print(f"Pressure test configuration:")
    print(f"  Services: {services_to_test}")
    print(f"  Rounds: {rounds}")
    print(f"  Cooldown: {COOLDOWN_MINUTES}min")
    print(f"  Target: {PP_BASE}")
    print(f"  Timeout per request: {REQUEST_TIMEOUT}s")

    all_results = {}

    for svc in services_to_test:
        model = SERVICE_MODEL_MAP[svc]
        svc_results = []

        for rd in range(1, rounds + 1):
            print(f"\n{'#'*60}")
            print(f"Round {rd}/{rounds} for {svc}")
            print(f"{'#'*60}")

            conc = await find_concurrency_limit(svc, model)
            rpm = await rpm_test(model)

            svc_results.append({
                "round": rd,
                "concurrency": conc,
                "rpm": rpm,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

            if rd < rounds:
                print(f"\n  Cooling down {COOLDOWN_MINUTES} minutes...")
                for m in range(COOLDOWN_MINUTES, 0, -1):
                    sys.stdout.write(f"\r    {m} min remaining...   ")
                    sys.stdout.flush()
                    await asyncio.sleep(60)
                print(f"\r    Cooldown complete.         ")

        all_results[svc] = svc_results

    print(f"\n{'='*60}")
    print("FINAL RESULTS SUMMARY")
    print(f"{'='*60}")
    for svc, rounds_data in all_results.items():
        conc_values = [r["concurrency"]["max_concurrent_ok"] for r in rounds_data]
        rpm_values = [r["rpm"]["effective_rpm"] for r in rounds_data]
        print(f"\n{svc}:")
        print(f"  Max concurrent ok (per round): {conc_values}")
        print(f"  Effective RPM (per round):     {rpm_values}")
        print(f"  → Recommended max_concurrent:  {min(conc_values)}")
        print(f"  → Recommended RPM:             {int(min(rpm_values) * 0.8)}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "pressure-test-results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
