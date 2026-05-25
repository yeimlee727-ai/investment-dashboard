from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from src.broker.base import OrderRequest
from src.broker.mock_broker import MockBroker
from src.database import init_db
from src.risk.risk_engine import RiskConfig, RiskEngine
from src.ui_helpers import (
    build_market_data_provider,
    get_fx_status_message,
    localize_columns,
    mock_delete_warning_message,
    render_data_warning,
)

POSITION_COLUMNS = [
    "market",
    "symbol",
    "currency",
    "quantity",
    "avg_price",
    "current_price",
    "market_value",
    "cost_basis",
    "unrealized_pnl",
    "unrealized_pnl_pct",
    "realized_pnl",
    "total_pnl",
    "total_pnl_pct",
    "fx_rate",
    "market_value_krw",
    "cost_basis_krw",
    "unrealized_pnl_krw",
    "realized_pnl_krw",
    "total_pnl_krw",
    "position_weight_krw",
    "fx_data_source",
    "fx_error",
    "quote_error",
    "updated_at",
]


def as_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def render_summary_cards(summary: dict[str, object]) -> None:
    rows = [
        [
            ("총 평가금액 KRW", f"{float(summary['total_market_value_krw']):,.0f}"),
            ("총 매입금액 KRW", f"{float(summary['total_cost_basis_krw']):,.0f}"),
            ("총 평가손익 KRW", f"{float(summary['total_unrealized_pnl_krw']):,.0f}"),
            ("총 평가손익률", f"{float(summary['total_unrealized_pnl_pct']):.2f}%"),
        ],
        [
            ("총 실현손익 KRW", f"{float(summary['total_realized_pnl_krw']):,.0f}"),
            ("총 손익 KRW", f"{float(summary['total_pnl_krw']):,.0f}"),
            ("보유 종목 수", f"{int(summary['position_count'])}"),
            ("현금 잔액", "추적 없음"),
        ],
        [
            ("상위 1개 비중 KRW", f"{float(summary['top1_weight_krw']):.2f}%"),
            ("최대 손실 종목", str(summary["max_loss_symbol"] or "-")),
            ("최대 수익 종목", str(summary["max_profit_symbol"] or "-")),
            ("현재가 오류", f"{int(summary['quote_error_count'])}건"),
        ],
        [
            (
                "USD/KRW 환율",
                (
                    f"{float(summary['fx_rate']):,.2f}"
                    if summary.get("fx_rate")
                    else "표시 불가"
                ),
            ),
            ("환율 출처", str(summary.get("fx_data_source") or "-")),
            ("환율 오류", f"{int(summary['fx_error_count'])}건"),
            ("원화 환산 기준", "참고용"),
        ],
    ]
    for row in rows:
        cols = st.columns(len(row))
        for col, (label, value) in zip(cols, row, strict=True):
            col.metric(label, value)


def render_fx_status(
    rate: float | None, data_source: str, as_of: object, error: str | None
) -> None:
    st.subheader("USD/KRW 환율 상태")
    cols = st.columns(4)
    cols[0].metric("USD/KRW 환율", f"{rate:,.2f}" if rate else "표시 불가")
    cols[1].metric("환율 출처", data_source or "-")
    cols[2].metric("기준 시각", str(as_of or "-"))
    cols[3].metric("환율 오류", "있음" if error else "없음")
    message = get_fx_status_message(rate, data_source, error)
    if error or rate is None:
        st.warning(message)
    else:
        st.info(message)


def render_risk_status(
    risk_engine: RiskEngine,
    risk_metrics: dict[str, float | int],
    current_daily_pnl: float,
) -> None:
    config = risk_engine.config
    st.subheader("모의매매 리스크 설정 / 현재 상태")
    cols = st.columns(4)
    cols[0].metric("1회 주문 한도", f"{config.max_order_amount:,.0f}")
    cols[1].metric("종목당 투자 한도", f"{config.max_symbol_exposure:,.0f}")
    cols[2].metric("일 손실 한도", f"{config.daily_loss_limit:,.0f}")
    cols[3].metric("비상정지", "ON" if config.emergency_stop else "OFF")
    cols = st.columns(4)
    cols[0].metric("현재 일 실현손익", f"{current_daily_pnl:,.0f}")
    cols[1].metric(
        "일 손실 한도 사용률", f"{risk_metrics['daily_loss_usage_pct']:.2f}%"
    )
    cols[2].metric("중복 진입 방지", "ON" if config.prevent_duplicate_entry else "OFF")
    cols[3].metric(
        "손실/수익 포지션",
        f"{risk_metrics['loss_position_count']} / {risk_metrics['profit_position_count']}",
    )


def render_position_charts(positions: pd.DataFrame) -> None:
    if positions.empty:
        st.info("표시할 가상 포지션이 없습니다.")
        return
    chart_data = positions.dropna(subset=["market_value_krw"]).copy()
    if chart_data.empty:
        st.warning("현재가 또는 환율 조회 실패로 원화 환산 차트를 표시할 수 없습니다.")
        return
    chart_data["ticker"] = chart_data["market"] + ":" + chart_data["symbol"]
    st.plotly_chart(
        px.bar(
            chart_data, x="ticker", y="market_value_krw", title="포지션별 평가금액 KRW"
        ),
        width="stretch",
    )
    st.plotly_chart(
        px.bar(chart_data, x="ticker", y="total_pnl_krw", title="포지션별 총손익 KRW"),
        width="stretch",
    )
    st.plotly_chart(
        px.pie(
            chart_data,
            names="ticker",
            values="market_value_krw",
            title="종목별 비중 KRW",
        ),
        width="stretch",
    )


def render_realized_charts(realized: pd.DataFrame) -> None:
    if realized.empty:
        st.info("표시할 실현손익 로그가 없습니다.")
        return
    data = realized.copy()
    data["realized_at"] = pd.to_datetime(data["realized_at"], errors="coerce")
    data = data.dropna(subset=["realized_at"])
    if data.empty:
        return
    daily = (
        data.assign(day=data["realized_at"].dt.date)
        .groupby("day", as_index=False)["realized_pnl"]
        .sum()
        .sort_values("day")
    )
    daily["cumulative_realized_pnl"] = daily["realized_pnl"].cumsum()
    st.plotly_chart(
        px.line(daily, x="day", y="realized_pnl", title="일별 실현손익"),
        width="stretch",
    )
    st.plotly_chart(
        px.line(
            daily,
            x="day",
            y="cumulative_realized_pnl",
            title="누적 실현손익",
        ),
        width="stretch",
    )
    by_symbol = data.groupby(["market", "symbol"], as_index=False)["realized_pnl"].sum()
    by_symbol["ticker"] = by_symbol["market"] + ":" + by_symbol["symbol"]
    st.dataframe(localize_columns(by_symbol), hide_index=True, width="stretch")


def filter_orders(orders: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return orders
    market_options = ["전체"] + sorted(orders["market"].dropna().unique().tolist())
    symbol_options = ["전체"] + sorted(orders["symbol"].dropna().unique().tolist())
    side_options = ["전체"] + sorted(orders["side"].dropna().unique().tolist())
    status_options = ["전체"] + sorted(orders["status"].dropna().unique().tolist())
    cols = st.columns(5)
    market = cols[0].selectbox("로그 시장", market_options)
    symbol = cols[1].selectbox("로그 종목", symbol_options)
    side = cols[2].selectbox("로그 구분", side_options)
    status = cols[3].selectbox("로그 상태", status_options)
    start = cols[4].date_input("로그 시작일", value=date.today() - timedelta(days=30))
    end = st.date_input("로그 종료일", value=date.today())
    view = orders.copy()
    view["created_at"] = pd.to_datetime(view["created_at"], errors="coerce")
    if market != "전체":
        view = view[view["market"] == market]
    if symbol != "전체":
        view = view[view["symbol"] == symbol]
    if side != "전체":
        view = view[view["side"] == side]
    if status != "전체":
        view = view[view["status"] == status]
    view = view[
        view["created_at"].dt.date.between(start, end) | view["created_at"].isna()
    ]
    return view


def render_position_delete_ui(
    broker: MockBroker, positions: list[dict[str, object]]
) -> None:
    st.subheader("테스트 포지션 삭제")
    st.warning(mock_delete_warning_message())
    if not positions:
        st.info("삭제할 MockBroker 가상 포지션이 없습니다.")
        return
    options = {
        f"{position['market']} / {position['symbol']}": position
        for position in positions
        if position.get("market") and position.get("symbol")
    }
    target_key = st.selectbox("삭제할 포지션 선택", ["선택 안 함", *list(options)])
    delete_orders = st.checkbox("관련 가상 주문 로그도 함께 삭제")
    delete_realized = st.checkbox("관련 실현손익 로그도 함께 삭제")
    confirm = st.checkbox(
        "이 삭제는 실제 주문이 아니라 MockBroker 로컬 데이터 정리 기능임을 이해했습니다."
    )
    if st.button("선택 포지션 삭제", type="secondary"):
        if target_key == "선택 안 함":
            st.warning("삭제할 가상 포지션을 선택하세요.")
            return
        if not confirm:
            st.warning("삭제 확인 체크박스를 선택하세요.")
            return
        target = options[target_key]
        result = broker.delete_position(
            symbol=str(target["symbol"]),
            market=str(target["market"]),
            delete_orders=delete_orders,
            delete_realized_pnl=delete_realized,
        )
        if result["success"]:
            st.success(
                "테스트 포지션을 삭제했습니다. "
                f"포지션 {result['deleted_positions']}건, "
                f"가상 주문 로그 {result['deleted_orders']}건, "
                f"실현손익 로그 {result['deleted_realized_pnl']}건 정리."
            )
            st.rerun()
        else:
            st.error(str(result["message"]))


def main() -> None:
    st.set_page_config(page_title="모의매매", layout="wide")
    init_db()
    st.title("모의매매")
    provider = build_market_data_provider()
    render_data_warning(provider)
    st.warning(
        "이 화면은 MockBroker 기반 모의매매입니다. 실제 주문, 실제 체결, 실제 계좌 조회를 수행하지 않습니다."
    )
    st.caption(
        "현재가는 외부 조회 또는 샘플 데이터 기반이며 실제 체결가가 아닐 수 있습니다."
    )

    risk_engine = RiskEngine(RiskConfig())
    broker = MockBroker(risk_engine=risk_engine, data_provider=provider)

    use_manual_fx = st.checkbox("수동 USD/KRW 환율 사용")
    manual_fx_rate = None
    if use_manual_fx:
        manual_fx_rate = st.number_input(
            "USD/KRW 환율",
            min_value=1.0,
            value=1350.0,
            step=1.0,
            help="사용자가 입력한 모의 평가 기준이며 실제 환율을 보장하지 않습니다.",
        )
        render_fx_status(float(manual_fx_rate), "MANUAL", "사용자 입력", None)
        st.caption("수동 환율은 실제 환율이 아니라 사용자가 입력한 평가 기준입니다.")
    else:
        fx = provider.get_fx_rate("USD/KRW")
        render_fx_status(fx.rate, fx.data_source, fx.as_of, fx.error)

    with st.form("virtual_order"):
        col1, col2, col3, col4, col5 = st.columns(5)
        symbol = col1.text_input("종목코드", value="005930")
        market = col2.selectbox("시장구분", ["KR", "US"])
        side = col3.selectbox("가상 주문 구분", ["BUY", "SELL"])
        quantity = col4.number_input("가상 수량", min_value=1, value=1)
        price = col5.number_input("가상 가격", min_value=1.0, value=70000.0)
        reason = st.selectbox(
            "가상 주문 사유", ["모의매수", "모의매도", "손절", "익절", "리밸런싱"]
        )
        if st.form_submit_button("가상 주문"):
            result = broker.place_order(
                OrderRequest(
                    symbol=symbol.strip().upper(),
                    market=market,
                    side=side,
                    quantity=int(quantity),
                    price=float(price),
                    reason=reason,
                )
            )
            if result.status == "filled":
                st.success(f"가상 주문 처리 완료: {result.message}")
            else:
                st.error(f"가상 주문 거부: {result.message}")

    st.subheader("가상 포지션 평가")
    col_a, col_b, col_c = st.columns(3)
    manual_symbol = col_a.text_input("평가 현재가 수동 입력 종목", value="005930")
    manual_market = col_b.selectbox("평가 시장구분", ["KR", "US"])
    manual_price = col_c.number_input("평가 현재가 수동 입력", min_value=0.0, value=0.0)
    price_overrides = (
        {f"{manual_market}:{manual_symbol.strip().upper()}": float(manual_price)}
        if manual_price > 0
        else {}
    )
    positions = broker.get_positions(
        current_prices=price_overrides, manual_fx_rate=manual_fx_rate
    )
    positions_df = as_dataframe(positions)
    summary = broker.get_portfolio_summary(
        current_prices=price_overrides, manual_fx_rate=manual_fx_rate
    )
    render_summary_cards(summary)
    if summary.get("fx_error_count"):
        st.warning(
            "환율 조회 실패로 일부 US 종목의 원화 환산 평가가 제한됩니다. fx_error 컬럼을 확인하세요."
        )

    daily_pnl = broker.get_daily_realized_pnl()
    risk_metrics = risk_engine.portfolio_risk_metrics(positions, daily_pnl)
    render_risk_status(risk_engine, risk_metrics, daily_pnl)

    if not positions_df.empty:
        st.dataframe(
            localize_columns(
                positions_df[[col for col in POSITION_COLUMNS if col in positions_df]]
            ),
            hide_index=True,
            width="stretch",
        )
        if positions_df["quote_error"].dropna().astype(bool).any():
            st.warning(
                "일부 가상 포지션은 현재가 조회에 실패했습니다. quote_error 컬럼을 확인하세요."
            )
        if (
            "fx_error" in positions_df
            and positions_df["fx_error"].dropna().astype(bool).any()
        ):
            st.warning(
                "일부 US 가상 포지션은 환율 조회에 실패했습니다. fx_error 컬럼을 확인하세요."
            )
    else:
        st.info("보유 중인 가상 포지션이 없습니다.")
    render_position_delete_ui(broker, positions)
    render_position_charts(positions_df)

    st.subheader("가상 주문/체결 로그")
    orders_df = as_dataframe(broker.get_order_logs())
    filtered_orders = filter_orders(orders_df)
    if filtered_orders.empty:
        st.info("표시할 가상 주문 로그가 없습니다.")
    else:
        st.dataframe(
            localize_columns(filtered_orders), hide_index=True, width="stretch"
        )

    st.subheader("실현손익 리포트")
    realized_df = as_dataframe(broker.get_realized_pnl_logs())
    if realized_df.empty:
        st.info("실현손익 로그가 없습니다.")
    else:
        st.dataframe(localize_columns(realized_df), hide_index=True, width="stretch")
    render_realized_charts(realized_df)


main()
