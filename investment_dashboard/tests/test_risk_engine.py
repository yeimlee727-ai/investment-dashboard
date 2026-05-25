from __future__ import annotations

from src.risk.risk_engine import RiskConfig, RiskEngine


def test_max_order_amount_blocks_order() -> None:
    decision = RiskEngine(RiskConfig(max_order_amount=100)).validate_order(
        "005930", "BUY", quantity=2, price=100
    )
    assert not decision.allowed
    assert "1회 주문 한도" in decision.reason


def test_max_symbol_exposure_blocks_buy() -> None:
    decision = RiskEngine(RiskConfig(max_symbol_exposure=100)).validate_order(
        "005930",
        "BUY",
        quantity=1,
        price=60,
        current_symbol_exposure=50,
    )
    assert not decision.allowed
    assert "종목당 투자 한도" in decision.reason


def test_daily_loss_limit_blocks_order() -> None:
    decision = RiskEngine(RiskConfig(daily_loss_limit=100)).validate_order(
        "005930", "SELL", quantity=1, price=10, current_daily_pnl=-100
    )
    assert not decision.allowed
    assert "일 손실 한도" in decision.reason


def test_duplicate_entry_blocks_buy() -> None:
    decision = RiskEngine().validate_order(
        "005930", "BUY", quantity=1, price=10, has_open_position=True
    )
    assert not decision.allowed
    assert "중복 진입" in decision.reason


def test_emergency_stop_blocks_all_orders() -> None:
    decision = RiskEngine(RiskConfig(emergency_stop=True)).validate_order(
        "005930", "SELL", quantity=1, price=10
    )
    assert not decision.allowed
    assert "비상정지" in decision.reason


def test_daily_loss_usage_pct() -> None:
    risk = RiskEngine(RiskConfig(daily_loss_limit=1000))
    assert risk.daily_loss_usage_pct(-250) == 25
    assert risk.daily_loss_usage_pct(100) == 0
    assert risk.daily_loss_usage_pct(-2000) == 100


def test_portfolio_risk_metrics() -> None:
    positions = [
        {
            "market_value": 700,
            "unrealized_pnl": 50,
        },
        {
            "market_value": 300,
            "unrealized_pnl": -20,
        },
        {
            "market_value": None,
            "unrealized_pnl": None,
        },
    ]

    metrics = RiskEngine(RiskConfig(daily_loss_limit=100)).portfolio_risk_metrics(
        positions,
        current_daily_pnl=-25,
    )

    assert metrics["top1_weight"] == 70
    assert metrics["top3_weight"] == 100
    assert metrics["loss_position_count"] == 1
    assert metrics["profit_position_count"] == 1
    assert metrics["unrealized_loss_total"] == -20
    assert metrics["unrealized_profit_total"] == 50
    assert metrics["daily_realized_pnl"] == -25
    assert metrics["daily_loss_usage_pct"] == 25


def test_portfolio_risk_metrics_use_krw_valuation_when_available() -> None:
    positions = [
        {
            "market_value": 100,
            "market_value_krw": 100,
            "unrealized_pnl": 10,
            "unrealized_pnl_krw": 10,
        },
        {
            "market_value": 1,
            "market_value_krw": 900,
            "unrealized_pnl": -1,
            "unrealized_pnl_krw": -100,
        },
    ]

    metrics = RiskEngine().portfolio_risk_metrics(positions)

    assert metrics["top1_weight"] == 90
    assert metrics["top3_weight"] == 100
    assert metrics["unrealized_loss_total"] == -100


def test_portfolio_risk_metrics_ignore_missing_fx_valuation_safely() -> None:
    positions = [
        {"market_value": 100, "market_value_krw": 100, "unrealized_pnl_krw": 10},
        {
            "market_value": 1,
            "market_value_krw": None,
            "unrealized_pnl_krw": None,
            "fx_error": "fx unavailable",
        },
    ]

    metrics = RiskEngine().portfolio_risk_metrics(positions)

    assert metrics["top1_weight"] == 100
    assert metrics["loss_position_count"] == 0
