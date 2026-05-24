from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.broker.base import OrderRequest
from src.broker.mock_broker import MockBroker
from src.models import RealizedPnlLog, VirtualOrder, VirtualPosition
from src.risk.risk_engine import RiskConfig, RiskEngine


class FakeProvider:
    def __init__(self, prices: dict[tuple[str, str], float] | None = None) -> None:
        self.prices = prices or {}

    def get_quote(self, symbol: str, market: str = "KR") -> dict[str, float | str]:
        key = (market, symbol)
        if key not in self.prices:
            raise RuntimeError("missing quote")
        return {"symbol": symbol, "market": market, "price": self.prices[key]}


def make_broker(provider: FakeProvider | None = None) -> MockBroker:
    risk = RiskEngine(
        RiskConfig(
            max_order_amount=10_000_000,
            max_symbol_exposure=10_000_000,
            daily_loss_limit=1_000_000,
        )
    )
    return MockBroker(risk_engine=risk, data_provider=provider or FakeProvider())


def test_buy_virtual_order_creates_position(isolated_session) -> None:
    broker = make_broker()

    result = broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )

    assert result.status == "filled"
    with isolated_session() as session:
        position = session.execute(select(VirtualPosition)).scalar_one()
        order = session.execute(select(VirtualOrder)).scalar_one()
        assert position.symbol == "005930"
        assert position.market == "KR"
        assert position.quantity == 10
        assert order.status == "filled"


def test_sell_virtual_order_records_realized_pnl_log(isolated_session) -> None:
    broker = make_broker()
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )

    result = broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="SELL", quantity=4, price=1200)
    )

    assert result.status == "filled"
    with isolated_session() as session:
        position = session.execute(select(VirtualPosition)).scalar_one()
        pnl_log = session.execute(select(RealizedPnlLog)).scalar_one()
        assert position.quantity == 6
        assert position.realized_pnl == 800
        assert pnl_log.quantity == 4
        assert pnl_log.realized_pnl == 800


def test_sell_without_enough_quantity_is_rejected(isolated_session) -> None:
    broker = make_broker()

    result = broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="SELL", quantity=1, price=1000)
    )

    assert result.status == "rejected"
    with isolated_session() as session:
        order = session.execute(select(VirtualOrder)).scalar_one()
        assert order.status == "rejected"


def test_invalid_order_inputs_are_rejected(isolated_session) -> None:
    broker = make_broker()
    requests = [
        OrderRequest("005930", "BUY", 0, 1000, "KR"),
        OrderRequest("005930", "BUY", 1, 0, "KR"),
        OrderRequest("005930", "BUY", 1, 1000, "JP"),
        OrderRequest("005930", "HOLD", 1, 1000, "KR"),
    ]

    results = [broker.place_order(request) for request in requests]

    assert [result.status for result in results] == ["rejected"] * 4
    with isolated_session() as session:
        assert len(session.execute(select(VirtualOrder)).scalars().all()) == 4


def test_market_specific_position_quotes_and_overrides(isolated_session) -> None:
    provider = FakeProvider({("KR", "005930"): 70_000, ("US", "AAPL"): 200})
    broker = make_broker(provider)
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=1, price=60_000)
    )
    broker.place_order(
        OrderRequest(symbol="AAPL", market="US", side="BUY", quantity=2, price=150)
    )

    positions = broker.get_positions(current_prices={"US:AAPL": 210})

    by_symbol = {position["symbol"]: position for position in positions}
    assert by_symbol["005930"]["current_price"] == 70_000
    assert by_symbol["AAPL"]["current_price"] == 210
    assert by_symbol["AAPL"]["market_value"] == 420
    assert by_symbol["AAPL"]["quote_error"] is None


def test_quote_failure_returns_none_and_quote_error(isolated_session) -> None:
    broker = make_broker(FakeProvider({}))
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=1, price=1000)
    )

    positions = broker.get_positions()

    assert positions[0]["current_price"] is None
    assert positions[0]["market_value"] is None
    assert str(positions[0]["quote_error"]).startswith("현재가 조회 실패")


def test_position_profit_report_fields_are_calculated(isolated_session) -> None:
    broker = make_broker(FakeProvider({("KR", "005930"): 1200}))
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )

    position = broker.get_positions()[0]

    assert position["cost_basis"] == 10_000
    assert position["market_value"] == 12_000
    assert position["unrealized_pnl"] == 2_000
    assert position["unrealized_pnl_pct"] == 20
    assert position["total_pnl"] == 2_000
    assert position["total_pnl_pct"] == 20
    assert position["position_weight"] == 100
    assert position["updated_at"] is not None


def test_portfolio_summary_excludes_quote_errors_from_market_value(
    isolated_session,
) -> None:
    broker = make_broker(FakeProvider({("KR", "005930"): 1200}))
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )
    broker.place_order(
        OrderRequest(symbol="000660", market="KR", side="BUY", quantity=5, price=1000)
    )

    summary = broker.get_portfolio_summary()

    assert summary["total_market_value"] == 12_000
    assert summary["total_cost_basis"] == 15_000
    assert summary["total_unrealized_pnl"] == 2_000
    assert summary["quote_error_count"] == 1


def test_order_and_realized_pnl_reports_include_required_columns(
    isolated_session,
) -> None:
    broker = make_broker()
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="SELL", quantity=4, price=1200)
    )

    order_log = broker.get_order_logs()[0]
    realized_log = broker.get_realized_pnl_logs()[0]

    assert {
        "created_at",
        "market",
        "symbol",
        "side",
        "quantity",
        "price",
        "status",
        "reason",
        "realized_pnl",
        "error_message",
    }.issubset(order_log)
    assert order_log["realized_pnl"] == 800
    assert {
        "realized_at",
        "market",
        "symbol",
        "quantity",
        "entry_price",
        "exit_price",
        "realized_pnl",
        "realized_pnl_pct",
        "holding_days",
        "reason",
    }.issubset(realized_log)
    assert realized_log["realized_pnl"] == 800


def test_daily_realized_pnl_uses_asia_seoul_day_boundary(isolated_session) -> None:
    broker = make_broker()
    seoul_today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    seoul_start = datetime.combine(seoul_today, time.min, tzinfo=ZoneInfo("Asia/Seoul"))
    utc_start = seoul_start.astimezone(timezone.utc).replace(tzinfo=None)

    with isolated_session() as session:
        session.add_all(
            [
                RealizedPnlLog(
                    symbol="005930",
                    market="KR",
                    quantity=1,
                    entry_price=100,
                    exit_price=90,
                    realized_pnl=-10,
                    created_at=utc_start + timedelta(minutes=1),
                ),
                RealizedPnlLog(
                    symbol="005930",
                    market="KR",
                    quantity=1,
                    entry_price=100,
                    exit_price=80,
                    realized_pnl=-20,
                    created_at=utc_start - timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    with isolated_session() as session:
        assert broker._get_daily_realized_pnl(session) == -10
