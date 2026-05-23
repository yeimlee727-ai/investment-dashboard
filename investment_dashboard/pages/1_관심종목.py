from __future__ import annotations

import streamlit as st
from sqlalchemy import delete, select

from src.database import get_session, init_db
from src.models import WatchlistItem
from src.ui_helpers import render_data_warning


def load_items() -> list[WatchlistItem]:
    with get_session() as session:
        return list(session.execute(select(WatchlistItem).order_by(WatchlistItem.created_at.desc())).scalars().all())


def add_item(symbol: str, name: str, market: str, sector: str, memo: str) -> None:
    with get_session() as session:
        existing = session.execute(select(WatchlistItem).where(WatchlistItem.symbol == symbol)).scalar_one_or_none()
        if existing:
            existing.name = name
            existing.market = market
            existing.sector = sector
            existing.memo = memo
        else:
            session.add(WatchlistItem(symbol=symbol, name=name, market=market, sector=sector, memo=memo))


def remove_item(symbol: str) -> None:
    with get_session() as session:
        session.execute(delete(WatchlistItem).where(WatchlistItem.symbol == symbol))


def main() -> None:
    st.set_page_config(page_title="관심종목", layout="wide")
    init_db()
    st.title("관심종목 관리")
    render_data_warning()

    with st.form("watchlist_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        symbol = col1.text_input("종목코드", placeholder="005930 또는 AAPL")
        name = col2.text_input("종목명", placeholder="삼성전자")
        market = col3.selectbox("시장구분", ["KR", "US"])
        sector = st.text_input("섹터", placeholder="반도체")
        memo = st.text_area("메모", placeholder="관심 이유, 체크 포인트")
        submitted = st.form_submit_button("저장")
        if submitted:
            if not symbol or not name:
                st.error("종목코드와 종목명은 필수입니다.")
            else:
                add_item(symbol.strip().upper(), name.strip(), market, sector.strip(), memo.strip())
                st.success("저장했습니다.")

    items = load_items()
    st.subheader("등록 목록")
    if not items:
        st.info("등록된 관심종목이 없습니다.")
        return
    st.dataframe(
        [{"symbol": i.symbol, "name": i.name, "market": i.market, "sector": i.sector, "memo": i.memo} for i in items],
        hide_index=True,
        use_container_width=True,
    )
    target = st.selectbox("삭제할 종목", [i.symbol for i in items])
    if st.button("삭제", type="secondary"):
        remove_item(target)
        st.success(f"{target} 삭제 완료")
        st.rerun()


main()
