from __future__ import annotations

import streamlit as st
from sqlalchemy import delete, select

from src.database import get_session, init_db
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import WatchlistItem
from src.ui_helpers import build_market_data_provider, render_data_warning


def load_items() -> list[WatchlistItem]:
    with get_session() as session:
        return list(
            session.execute(
                select(WatchlistItem).order_by(WatchlistItem.created_at.desc())
            )
            .scalars()
            .all()
        )


def add_item(symbol: str, name: str, market: str, sector: str, memo: str) -> str:
    with get_session() as session:
        existing = session.execute(
            select(WatchlistItem).where(WatchlistItem.symbol == symbol)
        ).scalar_one_or_none()
        if existing:
            if existing.market == market:
                return "duplicate"
            existing.name = name
            existing.market = market
            existing.sector = sector
            existing.memo = memo
            return "updated"
        else:
            session.add(
                WatchlistItem(
                    symbol=symbol, name=name, market=market, sector=sector, memo=memo
                )
            )
            return "created"


def remove_item(symbol: str, market: str) -> None:
    with get_session() as session:
        session.execute(
            delete(WatchlistItem).where(
                WatchlistItem.symbol == symbol,
                WatchlistItem.market == market,
            )
        )


def build_watchlist_rows(
    items: list[WatchlistItem], provider: MarketDataProvider
) -> list[dict[str, object]]:
    rows = []
    for item in items:
        quote = provider.get_latest_quote(item.symbol, item.market)
        rows.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "market": item.market,
                "sector": item.sector,
                "memo": item.memo,
                "latest_price": quote.price,
                "change_pct": quote.change_pct,
                "data_source": quote.data_source,
                "provider": quote.provider,
                "quote_error": quote.error,
                "as_of": quote.as_of,
            }
        )
    return rows


def main() -> None:
    st.set_page_config(page_title="관심종목", layout="wide")
    init_db()
    st.title("관심종목 관리")
    provider = build_market_data_provider()
    render_data_warning(provider)

    with st.form("watchlist_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        symbol = col1.text_input(
            "종목코드", placeholder="KR은 6자리 코드 예: 005930 / US는 티커 예: AAPL"
        )
        name = col2.text_input("종목명", placeholder="삼성전자")
        market = col3.selectbox(
            "시장구분",
            ["KR", "US"],
            help="KR: 국내 종목 6자리 코드 / US: 미국 티커",
        )
        sector = st.text_input("섹터", placeholder="반도체")
        memo = st.text_area("메모", placeholder="관심 이유, 체크 포인트")
        submitted = st.form_submit_button("저장")
        if submitted:
            if not symbol or not name:
                st.error("종목코드와 종목명은 필수입니다.")
            else:
                result = add_item(
                    symbol.strip().upper(),
                    name.strip(),
                    market,
                    sector.strip(),
                    memo.strip(),
                )
                if result == "duplicate":
                    st.warning("이미 등록된 종목입니다.")
                else:
                    st.success("저장했습니다.")

    items = load_items()
    st.subheader("등록 목록")
    if not items:
        st.info("등록된 관심종목이 없습니다.")
        return
    rows = build_watchlist_rows(items, provider)
    st.dataframe(rows, hide_index=True, width="stretch")
    if any(row["quote_error"] for row in rows):
        st.warning(
            "일부 관심종목의 현재가 조회에 실패했습니다. quote_error를 확인하세요."
        )

    options = {f"{item.market}:{item.symbol}": item for item in items}
    target_key = st.selectbox("삭제할 종목", list(options))
    confirm_delete = st.checkbox("정말 삭제합니다")
    if st.button("삭제", type="secondary", disabled=not confirm_delete):
        target = options[target_key]
        remove_item(target.symbol, target.market)
        st.success("관심종목을 삭제했습니다.")
        st.rerun()


main()
