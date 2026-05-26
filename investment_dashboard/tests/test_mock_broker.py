from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.broker.base import OrderRequest
from src.broker.mock_broker import MockBroker
from src.data_providers.base import FXRate
from src.data_providers.sample_provider import SampleDataProvider
from src.models import RealizedPnlLog, VirtualOrder, VirtualPosition
from src.risk.risk_engine import RiskConfig, RiskEngine


class FakeProvider:
    def __init__(
        self,
        prices: dict[tuple[str, str], float] | None = None,
        fx_rate: float | None = 1300.0,
        fx_error: str | None = None,
    ) -> None:
        self.prices = prices or {}
        self.fx_rate = fx_rate
        self.fx_error = fx_error

    def get_quote(self, symbol: str, market: str = "KR") -> dict[str, float | str]:
        key = (market, symbol)
        if key not in self.prices:
            raise RuntimeError("missing quote")
        return {"symbol": symbol, "market": market, "price": self.prices[key]}

    def get_fx_rate(self, pair: str = "USD/KRW") -> FXRate:
        return FXRate(
            pair=pair,
            rate=self.fx_rate,
            data_source="TEST_FX" if self.fx_rate is not None else "TEST_FX_ERROR",
            provider="FakeProvider",
            as_of="2026-01-02T00:00:00",
            error=self.fx_error,
        )


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
    assert by_symbol["AAPL"]["market_value_krw"] == 546_000


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
    assert position["fx_rate"] == 1
    assert position["market_value_krw"] == 12_000
    assert position["position_weight_krw"] == 100
    assert position["updated_at"] is not None


def test_us_position_uses_fx_for_krw_values(isolated_session) -> None:
    broker = make_broker(FakeProvider({("US", "GRAB"): 4.0}, fx_rate=1400.0))
    broker.place_order(
        OrderRequest(symbol="GRAB", market="US", side="BUY", quantity=100, price=3.0)
    )

    position = broker.get_positions()[0]

    assert position["currency"] == "USD"
    assert position["market_value"] == 400
    assert position["market_value_krw"] == 560_000
    assert position["cost_basis_krw"] == 420_000
    assert position["unrealized_pnl_krw"] == 140_000
    assert position["fx_data_source"] == "TEST_FX"
    assert position["fx_error"] is None


def test_us_position_without_fx_keeps_krw_values_empty(isolated_session) -> None:
    broker = make_broker(
        FakeProvider({("US", "GRAB"): 4.0}, fx_rate=None, fx_error="fx unavailable")
    )
    broker.place_order(
        OrderRequest(symbol="GRAB", market="US", side="BUY", quantity=100, price=3.0)
    )

    position = broker.get_positions()[0]

    assert position["market_value"] == 400
    assert position["market_value_krw"] is None
    assert position["total_pnl_krw"] is None
    assert position["fx_error"] == "fx unavailable"


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


def test_position_weight_krw_uses_fx_converted_total(isolated_session) -> None:
    broker = make_broker(
        FakeProvider({("KR", "005930"): 1000, ("US", "GRAB"): 10}, fx_rate=1000)
    )
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )
    broker.place_order(
        OrderRequest(symbol="GRAB", market="US", side="BUY", quantity=1, price=10)
    )

    positions = broker.get_positions()
    by_symbol = {position["symbol"]: position for position in positions}

    assert by_symbol["005930"]["market_value_krw"] == 10_000
    assert by_symbol["GRAB"]["market_value_krw"] == 10_000
    assert by_symbol["005930"]["position_weight_krw"] == 50
    assert by_symbol["GRAB"]["position_weight_krw"] == 50


def test_mixed_kr_us_portfolio_uses_krw_weight_for_grab(isolated_session) -> None:
    provider = FakeProvider(
        {
            ("KR", "360750"): 26_275,
            ("KR", "390390"): 48_589,
            ("KR", "453870"): 16_186.573770491803,
            ("US", "GRAB"): 3.51,
        },
        fx_rate=1500.0,
    )
    broker = make_broker(provider)
    orders = [
        OrderRequest("360750", "BUY", 31, 26_275, "KR"),
        OrderRequest("390390", "BUY", 16, 48_589, "KR"),
        OrderRequest("453870", "BUY", 61, 12_899, "KR"),
        OrderRequest("GRAB", "BUY", 30, 3.56, "US"),
    ]
    for request in orders:
        assert broker.place_order(request).status == "filled"

    positions = broker.get_positions()
    grab = {position["symbol"]: position for position in positions}["GRAB"]

    assert grab["current_price"] == 3.51
    assert grab["market_value"] == 105.3
    assert grab["market_value_krw"] == 157_950
    assert grab["position_weight_krw"] == 5.77
    assert grab["position_weight_krw"] < 10


def test_us_market_value_krw_does_not_apply_fx_twice(isolated_session) -> None:
    broker = make_broker(FakeProvider({("US", "GRAB"): 3.51}, fx_rate=1500.0))
    broker.place_order(
        OrderRequest(symbol="GRAB", market="US", side="BUY", quantity=30, price=3.56)
    )

    grab = broker.get_positions()[0]

    assert grab["market_value"] == 105.3
    assert grab["market_value_krw"] == 157_950
    assert grab["market_value_krw"] != 236_925_000


def test_sample_grab_quote_is_usd_scale() -> None:
    quote = SampleDataProvider().get_latest_quote("GRAB", "US")

    assert quote.currency == "USD"
    assert quote.price is not None
    assert 1.0 <= quote.price <= 10.0


def test_delete_position_removes_specific_market_symbol(isolated_session) -> None:
    broker = make_broker(FakeProvider({("KR", "005930"): 1000, ("US", "GRAB"): 4}))
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=1, price=1000)
    )
    broker.place_order(
        OrderRequest(symbol="GRAB", market="US", side="BUY", quantity=1, price=3)
    )

    result = broker.delete_position("GRAB", "US")
    positions = broker.get_positions()

    assert result["success"] is True
    assert result["deleted_positions"] == 1
    assert {position["symbol"] for position in positions} == {"005930"}


def test_delete_position_can_remove_related_logs(isolated_session) -> None:
    broker = make_broker(FakeProvider({("KR", "005930"): 1000}))
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="BUY", quantity=10, price=1000)
    )
    broker.place_order(
        OrderRequest(symbol="005930", market="KR", side="SELL", quantity=4, price=1200)
    )

    result = broker.delete_position(
        "005930", "KR", delete_orders=True, delete_realized_pnl=True
    )

    assert result["success"] is True
    assert result["deleted_positions"] == 1
    assert result["deleted_orders"] == 2
    assert result["deleted_realized_pnl"] == 1
    with isolated_session() as session:
        assert session.execute(select(VirtualOrder)).scalars().all() == []
        assert session.execute(select(RealizedPnlLog)).scalars().all() == []


def test_delete_missing_position_is_safe(isolated_session) -> None:
    broker = make_broker()

    result = broker.delete_position("NOPE", "US")

    assert result["success"] is False
    assert result["deleted_positions"] == 0
    assert "찾지 못했습니다" in str(result["message"])


def test_delete_position_rejects_invalid_market(isolated_session) -> None:
    broker = make_broker()

    result = broker.delete_position("005930", "JP")

    assert result["success"] is False
    assert result["deleted_positions"] == 0
    assert "올바르지" in str(result["message"])


def test_import_positions_upserts_without_order_logs(isolated_session) -> None:
    broker = make_broker(FakeProvider({("US", "GRAB"): 3.51}, fx_rate=1500.0))

    result = broker.import_positions(
        [
            {
                "symbol": "GRAB",
                "market": "US",
                "quantity": 30,
                "avg_price": 3.56,
            }
        ]
    )

    assert result["added"] == 1
    assert result["current_position_count"] == 1
    assert result["details"][0]["result"] == "신규 추가"
    assert result["details"][0]["new_quantity"] == 30
    position = broker.get_positions()[0]
    assert position["symbol"] == "GRAB"
    assert position["avg_price"] == 3.56
    assert position["market_value"] == 105.3
    assert position["market_value_krw"] == 157_950
    with isolated_session() as session:
        assert session.execute(select(VirtualOrder)).scalars().all() == []


def test_import_positions_updates_existing_market_symbol(isolated_session) -> None:
    broker = make_broker(FakeProvider({("KR", "005930"): 71_000}))
    broker.import_positions(
        [{"symbol": "005930", "market": "KR", "quantity": 1, "avg_price": 70_000}]
    )

    result = broker.import_positions(
        [{"symbol": "005930", "market": "KR", "quantity": 2, "avg_price": 69_000}]
    )

    assert result["updated"] == 1
    assert result["details"][0]["result"] == "업데이트"
    assert result["details"][0]["previous_quantity"] == 1
    assert result["details"][0]["new_quantity"] == 2
    position = broker.get_positions()[0]
    assert position["quantity"] == 2
    assert position["avg_price"] == 69_000


def test_import_positions_overwrite_existing_skips_new_symbols(
    isolated_session,
) -> None:
    broker = make_broker(FakeProvider({("KR", "005930"): 71_000}))
    broker.import_positions(
        [{"symbol": "005930", "market": "KR", "quantity": 1, "avg_price": 70_000}]
    )

    result = broker.import_positions(
        [
            {"symbol": "005930", "market": "KR", "quantity": 2, "avg_price": 69_000},
            {"symbol": "GRAB", "market": "US", "quantity": 30, "avg_price": 3.56},
        ],
        mode="overwrite_existing",
    )

    assert result["updated"] == 1
    assert result["skipped"] == 1
    assert {detail["result"] for detail in result["details"]} == {"업데이트", "건너뜀"}
    positions = broker.get_positions(current_prices={"KR:005930": 71_000})
    assert {position["symbol"] for position in positions} == {"005930"}


def test_import_positions_replace_clears_existing_positions(isolated_session) -> None:
    broker = make_broker(FakeProvider({("KR", "390390"): 48_589}))
    broker.import_positions(
        [{"symbol": "005930", "market": "KR", "quantity": 1, "avg_price": 70_000}]
    )

    result = broker.import_positions(
        [{"symbol": "390390", "market": "KR", "quantity": 16, "avg_price": 48_589}],
        mode="replace",
    )

    assert result["added"] == 1
    assert result["current_position_count"] == 1
    positions = broker.get_positions()
    assert {position["symbol"] for position in positions} == {"390390"}


def test_import_positions_reports_invalid_rows_without_order_logs(
    isolated_session,
) -> None:
    broker = make_broker()

    result = broker.import_positions(
        [{"symbol": "", "market": "KR", "quantity": 0, "avg_price": -1}]
    )

    assert result["failed"] == 1
    assert result["current_position_count"] == 0
    assert result["details"][0]["result"] == "오류 제외"
    with isolated_session() as session:
        assert session.execute(select(VirtualOrder)).scalars().all() == []


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
