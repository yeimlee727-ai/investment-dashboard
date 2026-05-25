from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from src.database import get_session, init_db
from src.dart.dart_client import DartClient
from src.models import WatchlistItem
from src.scanner.stock_scanner import StockScanner
from src.scoring.scoring_engine import ScoringEngine
from src.ui_helpers import (
    apply_plotly_dark_theme,
    build_market_data_provider,
    inject_global_css,
    localize_columns,
    render_data_warning,
    render_metric_card,
    render_page_header,
)


def load_watchlist_pairs() -> list[tuple[str, str]]:
    with get_session() as session:
        items = session.execute(select(WatchlistItem)).scalars().all()
        return [(item.symbol, item.market) for item in items]


def main() -> None:
    st.set_page_config(page_title="종목스캐너", layout="wide")
    inject_global_css()
    init_db()
    render_page_header(
        "종목 스캐너",
        "관심종목의 거래량, 등락률, 기술지표, 공시 리스크를 한 화면에서 점검합니다.",
        badges=[
            ("SAMPLE/FALLBACK 표시 유지", "warning"),
            ("실행 지시 아님", "success"),
        ],
    )
    provider = build_market_data_provider()

    pairs = load_watchlist_pairs()
    if not pairs:
        st.info("먼저 관심종목을 등록하세요.")
        return
    frames = {
        f"{market}:{symbol}": provider.get_price_history(symbol, market, 180)
        for symbol, market in pairs
    }
    scanned = StockScanner().scan(frames)
    if provider.mode == "REAL_WITH_FALLBACK" and not scanned.empty:
        data_sources = set(scanned.get("data_source", pd.Series(dtype=str)).dropna())
        provider.last_data_source = (
            "SAMPLE_FALLBACK" if "SAMPLE_FALLBACK" in data_sources else "YFINANCE"
        )
    render_data_warning(provider)
    disclosures = DartClient().search_disclosures(page_count=20)
    scored = ScoringEngine().score_dataframe(scanned, disclosures=disclosures)
    summary_cols = st.columns(4)
    with summary_cols[0]:
        render_metric_card("스캔 종목 수", len(scored), tone="neutral")
    with summary_cols[1]:
        top_score = (
            scored["score"].max() if not scored.empty and "score" in scored else None
        )
        render_metric_card(
            "최고 점수", "-" if top_score is None else f"{top_score:.1f}", tone="info"
        )
    with summary_cols[2]:
        risk_count = (
            int(scored["risk_tag"].isin(["risk", "critical"]).sum())
            if not scored.empty and "risk_tag" in scored
            else 0
        )
        render_metric_card("risk/critical", risk_count, tone="warning")
    with summary_cols[3]:
        fallback_count = (
            int(scored["data_source"].astype(str).str.contains("FALLBACK|SAMPLE").sum())
            if not scored.empty and "data_source" in scored
            else 0
        )
        render_metric_card("샘플/Fallback", fallback_count, tone="warning")

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

    display_columns = [
        "symbol",
        "market",
        "score",
        "change_pct",
        "volume_ratio",
        "risk_tag",
        "risk_penalty",
        "data_source",
    ]
    display = view.sort_values("score", ascending=False)
    display = display[[col for col in display_columns if col in display.columns]]
    numeric_columns = ["score", "change_pct", "volume_ratio", "risk_penalty"]
    for column in numeric_columns:
        if column in display.columns:
            display[column] = display[column].round(2)
    st.dataframe(localize_columns(display), hide_index=True, width="stretch")
    if not display.empty and "score" in view.columns:
        chart = view.sort_values("score", ascending=False).head(10)
        fig = px.bar(
            chart, x="score", y="symbol", orientation="h", title="스캐너 상위 점수"
        )
        st.plotly_chart(apply_plotly_dark_theme(fig), width="stretch")
    if not view.empty:
        selected = st.selectbox("AI 코멘트 프롬프트 확인", view["symbol"].tolist())
        prompt = str(view.loc[view["symbol"] == selected, "comment_prompt"].iloc[0])
        st.text_area("프롬프트 문자열", prompt, height=150)


main()
