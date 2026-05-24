from __future__ import annotations

import pandas as pd

from src.scanner.stock_scanner import StockScanner
from src.scoring.scoring_engine import ScoringEngine


def make_price_frame(length: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=length, freq="B")
    close = pd.Series(range(100, 100 + length), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": [1000.0 + i * 10 for i in range(length)],
        }
    )


def test_scanner_required_columns_and_empty_result() -> None:
    scanned = StockScanner().scan({"US:AAPL": make_price_frame()})
    required = {
        "symbol",
        "market",
        "close",
        "change_pct",
        "volume_ratio",
        "rsi",
        "ema20",
        "ema60",
        "macd",
        "macd_hist",
        "return_20d",
        "return_60d",
    }
    assert required.issubset(scanned.columns)
    assert scanned.iloc[0]["symbol"] == "AAPL"
    assert scanned.iloc[0]["market"] == "US"
    assert StockScanner().scan({}).empty


def test_scoring_range_and_weight_sum_without_disclosures() -> None:
    scanned = StockScanner().scan({"KR:005930": make_price_frame()})
    scored = ScoringEngine().score_dataframe(scanned)
    assert round(sum(ScoringEngine.weights.values()), 10) == 1.0
    assert scored["score"].between(0, 100).all()


def test_disclosures_affect_event_score_and_risk_penalty() -> None:
    scanner = StockScanner()
    rows = scanner.scan(
        {
            "KR:GOOD": make_price_frame(),
            "KR:RISK": make_price_frame(),
            "KR:CRIT": make_price_frame(),
        }
    )
    disclosures = pd.DataFrame(
        [
            {
                "stock_code": "GOOD",
                "disclosure_type": "공급계약",
                "risk_tag": "positive",
                "risk_score": 15,
                "report_nm": "단일판매ㆍ공급계약체결",
                "rcept_dt": "20260501",
            },
            {
                "stock_code": "RISK",
                "disclosure_type": "소송",
                "risk_tag": "risk",
                "risk_score": 78,
                "report_nm": "소송 등의 제기",
                "rcept_dt": "20260501",
            },
            {
                "stock_code": "CRIT",
                "disclosure_type": "횡령배임",
                "risk_tag": "critical",
                "risk_score": 95,
                "report_nm": "횡령ㆍ배임 혐의 발생",
                "rcept_dt": "20260501",
            },
        ]
    )
    scored = ScoringEngine().score_dataframe(rows, disclosures=disclosures)
    good = scored.loc[scored["symbol"] == "GOOD"].iloc[0]
    risk = scored.loc[scored["symbol"] == "RISK"].iloc[0]
    critical = scored.loc[scored["symbol"] == "CRIT"].iloc[0]
    assert good["event_score"] > 50
    assert risk["event_score"] < 50
    assert risk["risk_penalty"] >= 20
    assert critical["event_score"] < risk["event_score"]
    assert critical["risk_penalty"] >= 50
    assert scored["score"].between(0, 100).all()


def test_disclosure_absence_keeps_default_scoring_safe() -> None:
    rows = StockScanner().scan({"KR:EMPTY": make_price_frame()})
    scored = ScoringEngine().score_dataframe(rows, disclosures=pd.DataFrame())
    assert scored["score"].between(0, 100).all()
    assert "risk_penalty" in scored.columns
