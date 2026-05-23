from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from src.database import get_session, init_db
from src.data_providers.market_data_provider import MarketDataProvider
from src.dart.dart_client import DartClient
from src.models import WatchlistItem
from src.scanner.stock_scanner import StockScanner
from src.scoring.scoring_engine import ScoringEngine
from src.ui_helpers import render_data_warning


def load_watchlist_pairs() -> list[tuple[str, str]]:
    with get_session() as session:
        items = session.execute(select(WatchlistItem)).scalars().all()
        return [(item.symbol, item.market) for item in items]


def main() -> None:
    st.set_page_config(page_title="종목스캐너", layout="wide")
    init_db()
    st.title("종목 스캐너")
    provider = MarketDataProvider()
    render_data_warning(provider)

    pairs = load_watchlist_pairs()
    if not pairs:
        st.info("먼저 관심종목을 등록하세요.")
        return
    frames = {
        symbol: provider.get_price_history(symbol, market, 180)
        for symbol, market in pairs
    }
    scanned = StockScanner().scan(frames)
    disclosures = DartClient().search_disclosures(page_count=20)
    scored = ScoringEngine().score_dataframe(scanned, disclosures=disclosures)

    filters = st.multiselect(
        "조건 필터",
        ["거래량 급증", "RSI 과열", "RSI 침체", "EMA 돌파", "신고가 근접"],
        default=[],
    )
    view = scored.copy()
    mapping = {
        "거래량 급증": "volume_surge",
        "RSI 과열": "rsi_overbought",
        "RSI 침체": "rsi_oversold",
        "EMA 돌파": "ema_breakout",
        "신고가 근접": "near_high",
    }
    for label in filters:
        view = view[view[mapping[label]]]

    st.dataframe(
        view.sort_values("score", ascending=False),
        hide_index=True,
        use_container_width=True,
    )
    if not view.empty:
        selected = st.selectbox("AI 코멘트 프롬프트 확인", view["symbol"].tolist())
        prompt = str(view.loc[view["symbol"] == selected, "comment_prompt"].iloc[0])
        st.text_area("프롬프트 문자열", prompt, height=150)


main()
