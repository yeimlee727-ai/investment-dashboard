from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from src.dart.dart_client import DartClient
from src.database import get_session, init_db
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import WatchlistItem
from src.scanner.stock_scanner import StockScanner
from src.scoring.scoring_engine import ScoringEngine
from src.data_providers.base import DataMode
from src.ui_helpers import build_market_data_provider, render_data_warning


def apply_theme() -> None:
    st.set_page_config(page_title="Investment Dashboard", layout="wide", page_icon="📈")
    st.markdown(
        """
        <style>
        .stApp { background: #0f1117; color: #f4f6fb; }
        [data-testid="stMetricValue"] { color: #f4f6fb; }
        .block-container { padding-top: 1.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def ensure_seed_watchlist() -> None:
    with get_session() as session:
        count = len(session.execute(select(WatchlistItem)).scalars().all())
        if count:
            return
        session.add_all(
            [
                WatchlistItem(
                    symbol="005930",
                    name="삼성전자",
                    market="KR",
                    sector="반도체",
                    memo="대표 대형주",
                ),
                WatchlistItem(
                    symbol="035420",
                    name="NAVER",
                    market="KR",
                    sector="인터넷",
                    memo="플랫폼",
                ),
                WatchlistItem(
                    symbol="AAPL",
                    name="Apple",
                    market="US",
                    sector="Technology",
                    memo="미국 관심종목",
                ),
                WatchlistItem(
                    symbol="NVDA",
                    name="NVIDIA",
                    market="US",
                    sector="Semiconductor",
                    memo="AI 반도체",
                ),
            ]
        )


def load_watchlist() -> list[WatchlistItem]:
    with get_session() as session:
        return list(
            session.execute(select(WatchlistItem).order_by(WatchlistItem.symbol))
            .scalars()
            .all()
        )


@st.cache_data(ttl=300)
def load_scored_watchlist(
    items: list[tuple[str, str]], data_mode: DataMode
) -> pd.DataFrame:
    provider = MarketDataProvider(mode=data_mode)
    frames = {
        f"{market}:{symbol}": provider.get_price_history(symbol, market, days=180)
        for symbol, market in items
    }
    scanned = StockScanner().scan(frames)
    disclosures = DartClient().search_disclosures(page_count=20)
    return ScoringEngine().score_dataframe(scanned, disclosures=disclosures)


def render_market_summary(scored: pd.DataFrame) -> None:
    col1, col2, col3, col4 = st.columns(4)
    if scored.empty:
        col1.metric("관심종목", 0)
        col2.metric("평균 점수", "-")
        col3.metric("거래량 급증", 0)
        col4.metric("신고가 근접", 0)
        return
    col1.metric("관심종목", len(scored))
    col2.metric("평균 점수", f"{scored['score'].mean():.1f}")
    col3.metric("거래량 급증", int(scored["volume_surge"].sum()))
    col4.metric("신고가 근접", int(scored["near_high"].sum()))


def main() -> None:
    apply_theme()
    init_db()
    ensure_seed_watchlist()

    st.title("개인용 투자 대시보드")
    st.caption(
        "실제 주문 없이 데이터 조회, 스캐너, 공시, 백테스트, 모의매매만 수행하는 MVP입니다."
    )
    provider = build_market_data_provider()

    watchlist = load_watchlist()
    watchlist_keys = [(item.symbol, item.market) for item in watchlist]
    scored = load_scored_watchlist(watchlist_keys, provider.mode)
    if provider.mode == "REAL_WITH_FALLBACK" and not scored.empty:
        data_sources = set(scored.get("data_source", pd.Series(dtype=str)).dropna())
        provider.last_data_source = (
            "SAMPLE_FALLBACK" if "SAMPLE_FALLBACK" in data_sources else "YFINANCE"
        )
    render_data_warning(provider)

    render_market_summary(scored)

    left, right = st.columns([2, 1])
    with left:
        st.subheader("관심종목 점수")
        if scored.empty:
            st.info("관심종목을 등록하면 점수가 표시됩니다.")
        else:
            st.dataframe(
                scored[
                    [
                        "symbol",
                        "score",
                        "change_rate",
                        "volume_ratio",
                        "rsi14",
                        "rs_score",
                        "near_high_rate",
                        "data_source",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
            fig = px.bar(
                scored.sort_values("score"),
                x="score",
                y="symbol",
                orientation="h",
                color="score",
                color_continuous_scale="Viridis",
            )
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("핫종목")
        if not scored.empty:
            hot = scored.sort_values(["score", "volume_ratio"], ascending=False).head(5)
            st.dataframe(
                hot[["symbol", "score", "volume_ratio", "rs_score"]],
                hide_index=True,
                use_container_width=True,
            )
        st.subheader("최근 공시")
        disclosures = DartClient().search_disclosures(page_count=5)
        st.dataframe(
            disclosures[
                [
                    "corp_name",
                    "stock_code",
                    "report_nm",
                    "disclosure_type",
                    "risk_tag",
                    "rcept_dt",
                ]
            ].head(5),
            hide_index=True,
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
