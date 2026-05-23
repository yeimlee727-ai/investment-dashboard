from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from src.broker.base import OrderRequest
from src.broker.mock_broker import MockBroker
from src.database import get_session, init_db
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import VirtualOrder
from src.ui_helpers import render_data_warning


def load_orders() -> list[VirtualOrder]:
    with get_session() as session:
        return list(session.execute(select(VirtualOrder).order_by(VirtualOrder.created_at.desc())).scalars().all())


def main() -> None:
    st.set_page_config(page_title="모의매매", layout="wide")
    init_db()
    st.title("모의매매")
    provider = MarketDataProvider()
    render_data_warning(provider)
    st.caption("실제 주문은 전송하지 않습니다. 모든 주문은 SQLite에 가상 체결 로그로 저장됩니다.")

    broker = MockBroker(data_provider=provider)
    with st.form("virtual_order"):
        col1, col2, col3, col4 = st.columns(4)
        symbol = col1.text_input("종목코드", value="005930")
        side = col2.selectbox("구분", ["BUY", "SELL"])
        quantity = col3.number_input("수량", min_value=1, value=1)
        price = col4.number_input("가격", min_value=1.0, value=70000.0)
        reason = st.selectbox("사유", ["매수", "매도", "손절", "익절", "리밸런싱"])
        if st.form_submit_button("가상 주문"):
            try:
                result = broker.place_order(OrderRequest(symbol=symbol.strip().upper(), side=side, quantity=int(quantity), price=float(price), reason=reason))
                if result.status == "filled":
                    st.success(result.message)
                else:
                    st.error(result.message)
            except Exception as exc:
                st.error(f"주문 실패: {exc}")

    st.subheader("포지션")
    manual_symbol = st.text_input("평가 현재가 수동 입력 종목", value="005930")
    manual_price = st.number_input("평가 현재가 수동 입력", min_value=0.0, value=0.0)
    price_overrides = {manual_symbol.strip().upper(): float(manual_price)} if manual_price > 0 else {}
    positions = broker.get_positions(current_prices=price_overrides)
    st.dataframe(positions, hide_index=True, use_container_width=True)

    st.subheader("거래 로그")
    orders = load_orders()
    st.dataframe(
        [{"created_at": o.created_at, "symbol": o.symbol, "side": o.side, "quantity": o.quantity, "price": o.price, "reason": o.reason, "status": o.status} for o in orders],
        hide_index=True,
        use_container_width=True,
    )


main()
