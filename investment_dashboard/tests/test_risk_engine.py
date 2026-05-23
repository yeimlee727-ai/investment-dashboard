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
