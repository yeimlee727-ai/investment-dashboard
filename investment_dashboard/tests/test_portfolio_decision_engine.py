from __future__ import annotations

import math
import py_compile
from pathlib import Path

import numpy as np
import pandas as pd

from src.scoring.portfolio_decision_engine import PortfolioDecisionEngine


class FakeHistoryProvider:
    def __init__(self, histories: dict[tuple[str, str], pd.DataFrame]) -> None:
        self.histories = histories

    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = "5y"
    ) -> pd.DataFrame:
        return self.histories[(symbol, market)].copy()


def make_history(
    symbol: str = "AAA",
    market: str = "KR",
    days: int = 900,
    start: float = 100.0,
    end: float = 180.0,
    data_source: str = "YFINANCE",
) -> pd.DataFrame:
    close = np.linspace(start, end, days)
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=days),
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": np.linspace(1000, 1500, days),
            "value_traded": close * np.linspace(1000, 1500, days),
            "symbol": symbol,
            "market": market,
            "data_source": data_source,
            "provider": "FakeHistoryProvider",
        }
    )
    df.attrs["data_source"] = data_source
    df.attrs["provider"] = "FakeHistoryProvider"
    df.attrs["error"] = None
    return df


def make_position(
    symbol: str = "AAA",
    market: str = "KR",
    weight: float = 20.0,
    pnl_pct: float = 10.0,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "market": market,
        "name": symbol,
        "currency": "KRW" if market == "KR" else "USD",
        "market_value_krw": 1_000_000 * weight / 20,
        "cost_basis_krw": 900_000 * weight / 20,
        "total_pnl_krw": 100_000 * weight / 20,
        "position_weight_krw": weight,
        "total_pnl_pct": pnl_pct,
        "fx_error": None,
    }


def test_trend_classification_strong_uptrend() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})

    result = engine.analyze([make_position()], provider)

    assert result.positions.iloc[0]["trend_status"] in {
        "강한 상승 추세",
        "완만한 상승 추세",
    }


def test_scores_stay_between_zero_and_one_hundred() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})

    result = engine.analyze([make_position(weight=25)], provider)
    row = result.positions.iloc[0]

    assert 0 <= row["sell_review_score"] <= 100
    assert 0 <= row["additional_buy_score"] <= 100


def test_short_data_is_handled_safely() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history(days=40)})

    result = engine.analyze([make_position()], provider)
    row = result.positions.iloc[0]

    assert row["trend_status"] == "데이터 부족"
    assert row["reliability"] == "UNKNOWN"


def test_empty_price_data_is_handled_safely() -> None:
    engine = PortfolioDecisionEngine()
    empty = pd.DataFrame(
        columns=[
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "market",
            "data_source",
            "provider",
        ]
    )
    empty.attrs["data_source"] = "YFINANCE"
    empty.attrs["provider"] = "FakeHistoryProvider"
    provider = FakeHistoryProvider({("AAA", "KR"): empty})

    result = engine.analyze([make_position()], provider)
    row = result.positions.iloc[0]

    assert row["trend_status"] == "데이터 부족"
    assert row["reliability"] == "UNKNOWN"
    assert "분석" in row["reliability_reason"]


def test_less_than_three_year_external_data_is_medium_reliability() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history(days=500)})

    result = engine.analyze([make_position()], provider)

    assert result.positions.iloc[0]["reliability"] == "MEDIUM"


def test_sample_or_fallback_data_is_low_reliability() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider(
        {("AAA", "KR"): make_history(data_source="SAMPLE_FALLBACK")}
    )

    result = engine.analyze([make_position()], provider)

    assert result.positions.iloc[0]["reliability"] == "LOW"


def test_critical_disclosure_increases_sell_review_score() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})
    disclosures = pd.DataFrame(
        [
            {
                "stock_code": "AAA",
                "report_nm": "상장폐지 사유 발생",
                "risk_tag": "critical",
                "risk_score": 95,
                "rcept_dt": "20260520",
            }
        ]
    )

    result = engine.analyze([make_position()], provider, disclosures)

    assert result.positions.iloc[0]["sell_review_score"] >= 60


def test_low_reliability_penalizes_additional_buy_score() -> None:
    engine = PortfolioDecisionEngine()
    real_provider = FakeHistoryProvider({("AAA", "KR"): make_history()})
    sample_provider = FakeHistoryProvider(
        {("AAA", "KR"): make_history(data_source="SAMPLE_FALLBACK")}
    )

    real = engine.analyze([make_position()], real_provider).positions.iloc[0]
    sample = engine.analyze([make_position()], sample_provider).positions.iloc[0]

    assert sample["additional_buy_score"] < real["additional_buy_score"]


def test_high_position_weight_increases_sell_review_score() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})

    low = engine.analyze([make_position(weight=5)], provider).positions.iloc[0]
    high = engine.analyze([make_position(weight=60)], provider).positions.iloc[0]

    assert high["sell_review_score"] > low["sell_review_score"]


def test_krw_weight_affects_additional_buy_priority() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})

    low_weight = engine.analyze([make_position(weight=5)], provider).positions.iloc[0]
    high_weight = engine.analyze([make_position(weight=45)], provider).positions.iloc[0]

    assert low_weight["additional_buy_score"] > high_weight["additional_buy_score"]
    assert high_weight["additional_buy_score"] <= 70


def test_result_has_no_nan_or_inf_values() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})

    result = engine.analyze([make_position()], provider)

    for value in result.positions.iloc[0].to_dict().values():
        if isinstance(value, float):
            assert not math.isnan(value)
            assert not math.isinf(value)


def test_nan_or_inf_history_values_do_not_leak_to_result() -> None:
    engine = PortfolioDecisionEngine()
    history = make_history()
    history.loc[100, "close"] = np.nan
    history.loc[200, "high"] = np.inf
    history.loc[300, "volume"] = np.nan
    history.loc[len(history) - 1, "close"] = np.inf
    provider = FakeHistoryProvider({("AAA", "KR"): history})

    result = engine.analyze([make_position()], provider)

    for value in result.positions.iloc[0].to_dict().values():
        if isinstance(value, float):
            assert not math.isnan(value)
            assert not math.isinf(value)


def test_portfolio_summary_contains_krw_totals() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider({("AAA", "KR"): make_history()})

    result = engine.analyze([make_position(weight=20)], provider)

    assert result.portfolio_summary["total_market_value_krw"] == 1_000_000
    assert result.portfolio_summary["total_cost_basis_krw"] == 900_000
    assert result.portfolio_summary["total_pnl_krw"] == 100_000


def test_us_position_weight_uses_krw_converted_portfolio_weight() -> None:
    engine = PortfolioDecisionEngine()
    provider = FakeHistoryProvider(
        {
            ("360750", "KR"): make_history("360750"),
            ("390390", "KR"): make_history("390390"),
            ("453870", "KR"): make_history("453870"),
            ("GRAB", "US"): make_history("GRAB", market="US"),
        }
    )
    positions = [
        make_position("360750", "KR", weight=29.76),
        make_position("390390", "KR", weight=28.4),
        make_position("453870", "KR", weight=36.07),
        {
            "symbol": "GRAB",
            "market": "US",
            "name": "GRAB",
            "currency": "USD",
            "market_value_krw": 157_950,
            "cost_basis_krw": 160_200,
            "total_pnl_krw": -2_250,
            "position_weight_krw": 5.77,
            "total_pnl_pct": -1.4,
            "fx_error": None,
        },
    ]

    result = engine.analyze(positions, provider)
    grab = result.positions[result.positions["symbol"] == "GRAB"].iloc[0]

    assert grab["position_weight_krw"] == 5.77
    assert result.portfolio_summary["us_weight"] == 5.77
    assert result.portfolio_summary["us_weight"] < 10


def test_portfolio_strategy_page_compiles() -> None:
    page = Path("pages/6_포트폴리오전략.py")

    py_compile.compile(str(page), doraise=True)
