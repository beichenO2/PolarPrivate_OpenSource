"""Load-balance helper stays available; live codes are single-source."""

from __future__ import annotations

from app.core.model_routing import (
    get_load_balance_group,
    select_service_by_weight,
)


class TestGetLoadBalanceGroup:
    def test_live_models_are_single_source(self) -> None:
        assert get_load_balance_group("MiniMax-M3") is None
        assert get_load_balance_group("MiniMax-M3-Thinking") is None
        assert get_load_balance_group("deepseek-v4-pro") is None
        assert get_load_balance_group("qwen3-vl-flash") is None

    def test_retired_xfyun_has_no_group(self) -> None:
        assert get_load_balance_group("xopglm52") is None
        assert get_load_balance_group("GLM-5.1") is None

    def test_unknown_model_no_group(self) -> None:
        assert get_load_balance_group("nonexistent-model") is None


class TestSelectServiceByWeight:
    def test_single_service_always_selected(self) -> None:
        result = select_service_by_weight([{"service": "only-one", "weight": 1}])
        assert result == ("only-one", None)

    def test_equal_weights(self) -> None:
        services = [
            {"service": "a", "weight": 1},
            {"service": "b", "weight": 1},
        ]
        counts: dict[str, int] = {}
        for _ in range(1000):
            s, _model = select_service_by_weight(services)
            counts[s] = counts.get(s, 0) + 1
        assert 0.40 < counts["a"] / 1000 < 0.60
        assert 0.40 < counts["b"] / 1000 < 0.60
