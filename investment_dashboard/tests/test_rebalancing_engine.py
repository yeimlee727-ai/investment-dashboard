from __future__ import annotations

import math
import py_compile
from pathlib import Path

import numpy as np
import pandas as pd

from src.risk.rebalancing_engine import RebalancingEngine


class FakeHistoryProvider:
    def __init__(self, histories: dict[tuple[str, str], pd.DataFrame]) -> None:
        self.histories = histories

    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = "3y"
    ) -> pd.DataFrame:
        return self.histories.get((symbol, market), pd.DataFrame()).copy()


def make_history(
    symbol: str,
    market: str = "KR",
    days: int = 300,
    start: float = 100.0,
    end: float = 130.0,
    data_source: str = "YFINANCE",
) -> pd.DataFrame:
    close = np.linspace(start, end, days)
    frame = pd.DataFrame(
        {
            "date": pd.bdate_range("2025-01-02", periods=days),
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": np.linspace(1000, 1500, days),
            "symbol": symbol,
            "market": market,
            "data_source": data_source,
            "provider": "FakeHistoryProvider",
        }
    )
    frame.attrs["data_source"] = data_source
    frame.attrs["provider"] = "FakeHistoryProvider"
    return frame


def make_position(
    symbol: str = "360750",
    market: str = "KR",
    name: str = "TIGER 미국S&P500",
    value: float = 1_000_000,
    weight: float = 50.0,
    fx_error: str | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "market": market,
        "name": name,
        "market_value_krw": value,
        "position_weight_krw": weight,
        "total_pnl_pct": 5.0,
        "fx_error": fx_error,
    }


def decision_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "360750",
                "additional_buy_score": 70,
                "sell_review_score": 20,
                "reliability": "HIGH",
            },
            {
                "symbol": "GRAB",
                "additional_buy_score": 35,
                "sell_review_score": 75,
                "reliability": "LOW",
            },
        ]
    )


def test_risk_contribution_sums_reasonably() -> None:
    positions = [
        make_position("360750", name="TIGER 미국S&P500", value=1_000_000, weight=50),
        make_position("390390", name="KODEX 미국반도체", value=1_000_000, weight=50),
    ]
    provider = FakeHistoryProvider(
        {
            ("360750", "KR"): make_history("360750", end=130),
            ("390390", "KR"): make_history("390390", end=170),
        }
    )

    result = RebalancingEngine().analyze(positions, provider)
    total = pd.to_numeric(
        result.risk_contribution["risk_contribution"], errors="coerce"
    ).sum()

    assert 99 <= total <= 101


def test_single_position_is_safe() -> None:
    positions = [make_position()]
    provider = FakeHistoryProvider({("360750", "KR"): make_history("360750")})

    result = RebalancingEngine().analyze(positions, provider)

    assert result.risk_contribution.iloc[0]["risk_contribution"] == 100.0
    assert result.correlation_matrix.empty


def test_empty_returns_are_handled_safely() -> None:
    positions = [make_position()]
    provider = FakeHistoryProvider({("360750", "KR"): pd.DataFrame()})

    result = RebalancingEngine().analyze(positions, provider)

    assert result.risk_contribution.iloc[0]["risk_contribution"] is None
    assert result.risk_contribution.iloc[0]["risk_evaluation"] == "데이터 부족"


def test_correlation_matrix_removes_nan_or_inf() -> None:
    history = make_history("360750")
    history.loc[20, "close"] = np.nan
    other = make_history("390390")
    other.loc[30, "close"] = np.inf
    provider = FakeHistoryProvider({("360750", "KR"): history, ("390390", "KR"): other})
    positions = [
        make_position("360750", name="TIGER 미국S&P500", value=1_000_000, weight=50),
        make_position("390390", name="KODEX 미국반도체", value=1_000_000, weight=50),
    ]

    result = RebalancingEngine().analyze(positions, provider)

    for value in result.correlation_matrix.to_numpy().ravel():
        if isinstance(value, float):
            assert not math.isnan(value)
            assert not math.isinf(value)


def test_stress_test_calculates_krw_loss_and_pct() -> None:
    positions = [make_position(value=2_000_000, weight=100)]
    provider = FakeHistoryProvider({("360750", "KR"): make_history("360750")})

    result = RebalancingEngine().analyze(positions, provider)
    row = result.stress_results[
        result.stress_results["scenario"] == "미국 기술주 조정"
    ].iloc[0]

    assert row["stress_loss_krw"] < 0
    assert row["stress_loss_pct"] < 0


def test_target_weight_gap_is_calculated() -> None:
    positions = [make_position(value=1_000_000, weight=100)]
    provider = FakeHistoryProvider({("360750", "KR"): make_history("360750")})

    result = RebalancingEngine().analyze(positions, provider)
    row = result.target_comparison[
        result.target_comparison["asset_class"] == "미국 코어 ETF"
    ].iloc[0]

    assert row["current_weight"] == 100.0
    assert row["weight_gap"] > 0
    assert row["is_outside_band"]


def test_allocation_total_does_not_exceed_input_amount() -> None:
    positions = [
        make_position("360750", name="TIGER 미국S&P500", value=500_000, weight=10),
        make_position("390390", name="KODEX 미국반도체", value=500_000, weight=10),
    ]
    provider = FakeHistoryProvider(
        {
            ("360750", "KR"): make_history("360750"),
            ("390390", "KR"): make_history("390390"),
        }
    )

    result = RebalancingEngine().analyze(
        positions,
        provider,
        additional_investment_krw=3_000_000,
        decision_frame=decision_frame(),
    )

    assert result.allocation_plan["adjusted_amount"].sum() <= 3_000_000


def test_individual_stock_cap_and_low_reliability_limit_allocation() -> None:
    positions = [
        make_position(
            "GRAB",
            market="US",
            name="GRAB",
            value=1_000_000,
            weight=12,
        )
    ]
    provider = FakeHistoryProvider(
        {("GRAB", "US"): make_history("GRAB", market="US", data_source="SAMPLE")}
    )

    result = RebalancingEngine().analyze(
        positions,
        provider,
        additional_investment_krw=3_000_000,
        decision_frame=decision_frame(),
    )
    row = result.allocation_plan[result.allocation_plan["symbol"] == "GRAB"].iloc[0]

    assert row["adjusted_amount"] == 0
    assert "데이터 신뢰도 낮음" in row["limit_reason"]


def test_high_risk_contribution_limits_allocation() -> None:
    positions = [
        make_position("360750", name="TIGER 미국S&P500", value=700_000, weight=20),
        make_position("390390", name="KODEX 미국반도체", value=300_000, weight=5),
    ]
    provider = FakeHistoryProvider(
        {
            ("360750", "KR"): make_history("360750", end=105),
            ("390390", "KR"): make_history("390390", end=300),
        }
    )

    result = RebalancingEngine().analyze(
        positions,
        provider,
        additional_investment_krw=3_000_000,
    )

    assert "risk_contribution" in result.risk_contribution.columns
    assert result.allocation_plan["adjusted_amount"].sum() <= 3_000_000


def test_us_fx_error_is_reported_safely() -> None:
    positions = [
        make_position(
            "GRAB",
            market="US",
            name="GRAB",
            value=None,  # type: ignore[arg-type]
            weight=None,  # type: ignore[arg-type]
            fx_error="fx failed",
        )
    ]
    provider = FakeHistoryProvider({("GRAB", "US"): make_history("GRAB", market="US")})

    result = RebalancingEngine().analyze(positions, provider)

    assert result.risk_summary["total_market_value_krw"] == 0
    assert result.allocation_plan.empty


def test_all_market_values_none_are_handled_safely() -> None:
    positions = [
        make_position(
            "GRAB",
            market="US",
            name="GRAB",
            value=None,  # type: ignore[arg-type]
            weight=100,
            fx_error="fx failed",
        )
    ]
    provider = FakeHistoryProvider({("GRAB", "US"): make_history("GRAB", market="US")})

    result = RebalancingEngine().analyze(positions, provider)

    assert result.risk_summary["total_market_value_krw"] == 0
    assert result.risk_contribution.iloc[0]["position_weight_krw"] is None
    assert result.risk_contribution.iloc[0]["risk_contribution"] is None


def test_target_weight_total_status_is_reported() -> None:
    positions = [make_position(value=1_000_000, weight=100)]
    provider = FakeHistoryProvider({("360750", "KR"): make_history("360750")})

    result = RebalancingEngine().analyze(
        positions,
        provider,
        target_weights={
            "미국 코어 ETF": 40.0,
            "미국 반도체/AI ETF": 0.0,
            "인도 ETF": 0.0,
            "개별 성장주": 0.0,
            "현금": 20.0,
        },
    )

    assert result.target_comparison.iloc[0]["target_total_weight"] == 60.0
    assert "100%" in result.target_comparison.iloc[0]["target_total_status"]


def test_zero_additional_investment_returns_empty_allocation() -> None:
    positions = [make_position(value=1_000_000, weight=100)]
    provider = FakeHistoryProvider({("360750", "KR"): make_history("360750")})

    result = RebalancingEngine().analyze(
        positions,
        provider,
        additional_investment_krw=0,
    )

    assert result.allocation_plan.empty


def test_all_restricted_positions_keep_cash_waiting() -> None:
    positions = [
        make_position(
            "GRAB",
            market="US",
            name="GRAB",
            value=1_000_000,
            weight=5,
            fx_error="fx failed",
        )
    ]
    provider = FakeHistoryProvider(
        {("GRAB", "US"): make_history("GRAB", market="US", data_source="SAMPLE")}
    )

    result = RebalancingEngine().analyze(
        positions,
        provider,
        target_weights={"개별 성장주": 10.0, "현금": 90.0},
        additional_investment_krw=500_000,
        decision_frame=decision_frame(),
    )

    cash = result.allocation_plan[result.allocation_plan["symbol"] == "CASH"].iloc[0]
    assert cash["adjusted_amount"] == 500_000
    assert result.allocation_plan["adjusted_amount"].sum() <= 500_000


def test_correlation_pairs_exclude_self_correlation() -> None:
    provider = FakeHistoryProvider(
        {
            ("360750", "KR"): make_history("360750", end=130),
            ("390390", "KR"): make_history("390390", end=170),
            ("453870", "KR"): make_history("453870", end=90),
        }
    )
    positions = [
        make_position("360750", name="TIGER 미국S&P500", value=1_000_000, weight=40),
        make_position("390390", name="KODEX 미국반도체", value=800_000, weight=35),
        make_position("453870", name="TIGER 인도니프티50", value=600_000, weight=25),
    ]

    result = RebalancingEngine().analyze(positions, provider)

    highest_pair = str(result.correlation_summary["highest_pair"])
    left, right = highest_pair.split(" / ")
    assert left != right


def test_result_has_no_nan_or_inf_values() -> None:
    positions = [make_position()]
    provider = FakeHistoryProvider({("360750", "KR"): make_history("360750")})

    result = RebalancingEngine().analyze(positions, provider)

    for frame in [
        result.risk_contribution,
        result.stress_results,
        result.target_comparison,
        result.allocation_plan,
    ]:
        for value in frame.to_numpy().ravel():
            if isinstance(value, float):
                assert not math.isnan(value)
                assert not math.isinf(value)


def test_rebalancing_page_compiles() -> None:
    page = Path("pages/7_리스크리밸런싱.py")

    py_compile.compile(str(page), doraise=True)
