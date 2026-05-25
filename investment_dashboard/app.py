from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from src.broker.mock_broker import MockBroker
from src.dart.dart_client import DartClient
from src.database import get_session, init_db
from src.data_providers.base import DataMode, Quote
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import WatchlistItem
from src.scanner.stock_scanner import StockScanner
from src.scoring.scoring_engine import ScoringEngine
from src.ui_helpers import (
    build_market_data_provider,
    get_data_mode_status,
    localize_columns,
    render_data_warning,
)

STRATEGIES = ["EMA20 상향 돌파 + 거래량 증가", "RSI 30 이하 반등", "신고가 돌파"]
PAGE_GUIDE = [
    ("관심종목", "국내/미국 종목코드, 섹터, 메모를 관리합니다."),
    ("종목스캐너", "거래량, RSI, EMA, 신고가 근접 등 조건을 점검합니다."),
    ("DART공시", "공시 유형과 위험 신호를 확인합니다."),
    ("백테스트", "전략 성과를 리포트 형태로 검증합니다."),
    ("모의매매", "MockBroker 기반 가상 주문과 포지션을 확인합니다."),
]


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


def quote_to_row(quote: Quote) -> dict[str, Any]:
    return {
        "symbol": quote.symbol,
        "market": quote.market,
        "price": quote.price,
        "change_pct": quote.change_pct,
        "volume": quote.volume,
        "data_source": quote.data_source,
        "provider": quote.provider,
        "quote_error": quote.error,
    }


def load_watchlist_quotes(
    items: list[tuple[str, str]], data_mode: DataMode
) -> pd.DataFrame:
    provider = MarketDataProvider(mode=data_mode)
    rows = []
    for symbol, market in items:
        try:
            rows.append(quote_to_row(provider.get_latest_quote(symbol, market)))
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "market": market,
                    "price": None,
                    "change_pct": None,
                    "volume": None,
                    "data_source": "ERROR",
                    "provider": provider.get_provider_name(),
                    "quote_error": str(exc),
                }
            )
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def load_scored_watchlist(
    items: list[tuple[str, str]], data_mode: DataMode
) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    provider = MarketDataProvider(mode=data_mode)
    frames = {
        f"{market}:{symbol}": provider.get_price_history(symbol, market, days=180)
        for symbol, market in items
    }
    scanned = StockScanner().scan(frames)
    disclosures = DartClient().search_disclosures(page_count=20)
    return ScoringEngine().score_dataframe(scanned, disclosures=disclosures)


def summarize_watchlist(
    watchlist: list[WatchlistItem], quotes: pd.DataFrame
) -> dict[str, int]:
    if quotes.empty:
        return {
            "total": len(watchlist),
            "kr_count": sum(1 for item in watchlist if item.market == "KR"),
            "us_count": sum(1 for item in watchlist if item.market == "US"),
            "quote_success_count": 0,
            "fallback_count": 0,
            "quote_error_count": 0,
        }
    return {
        "total": len(watchlist),
        "kr_count": int((quotes["market"] == "KR").sum()),
        "us_count": int((quotes["market"] == "US").sum()),
        "quote_success_count": int(quotes["price"].notna().sum()),
        "fallback_count": int(quotes["data_source"].eq("SAMPLE_FALLBACK").sum()),
        "quote_error_count": int(quotes["quote_error"].notna().sum()),
    }


def render_data_mode_section(provider: MarketDataProvider) -> None:
    badge, message, level = get_data_mode_status(
        provider.mode, provider.is_fallback_mode()
    )
    st.subheader("데이터 모드 상태")
    cols = st.columns(3)
    cols[0].metric("현재 모드", badge)
    cols[1].metric("Provider", provider.get_provider_name())
    cols[2].metric("마지막 데이터 출처", provider.last_data_source)
    if level == "info":
        st.info(f"{badge}: {message}")
    else:
        st.warning(f"{badge}: {message}")
    if provider.last_error:
        st.caption(f"최근 조회 메시지: {provider.last_error}")


def render_safety_status() -> None:
    st.subheader("시스템 안전 상태")
    cols = st.columns(5)
    cols[0].metric("실제 주문 기능", "없음")
    cols[1].metric("TossBroker", "Placeholder")
    cols[2].metric("MockBroker", "가상 주문")
    cols[3].metric("실제 계좌 조회", "없음")
    cols[4].metric("API Key 화면 노출", "없음")
    st.caption(
        "이 카드는 시스템 동작 상태를 설명합니다. 투자 판단이나 주문 신호를 의미하지 않습니다."
    )


def render_watchlist_summary(
    summary: dict[str, int], watchlist: list[WatchlistItem]
) -> None:
    st.subheader("관심종목 요약")
    if not watchlist:
        st.info("관심종목이 없습니다. 관심종목 페이지에서 종목을 추가하세요.")
        return
    cols = st.columns(6)
    cols[0].metric("관심종목 수", summary["total"])
    cols[1].metric("KR 종목", summary["kr_count"])
    cols[2].metric("US 종목", summary["us_count"])
    cols[3].metric("조회 성공", summary["quote_success_count"])
    cols[4].metric("Fallback", summary["fallback_count"])
    cols[5].metric("Quote error", summary["quote_error_count"])


def render_scanner_summary(scored: pd.DataFrame) -> None:
    st.subheader("스캐너 상위 종목 요약")
    if scored.empty:
        st.info("스캐너 요약을 표시할 데이터가 없습니다.")
        return
    view = scored.sort_values("score", ascending=False).head(7).copy()
    for optional in ["risk_tag", "risk_penalty", "data_source"]:
        if optional not in view.columns:
            view[optional] = ""
    columns = [
        "symbol",
        "market",
        "score",
        "change_pct",
        "volume_ratio",
        "risk_tag",
        "risk_penalty",
        "data_source",
    ]
    st.dataframe(
        localize_columns(view[[col for col in columns if col in view.columns]]),
        hide_index=True,
        width="stretch",
    )
    fig = px.bar(
        view.sort_values("score"),
        x="score",
        y="symbol",
        orientation="h",
        title="상위 종목 점수",
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("점수는 스캐너 요약 지표이며 매수/매도 추천이 아닙니다.")


def render_dart_summary(disclosures: pd.DataFrame) -> None:
    st.subheader("DART 리스크 요약")
    source = str(disclosures.attrs.get("data_source", "UNKNOWN"))
    if disclosures.empty:
        if source == "DART_API_NO_DATA":
            st.info("조회된 공시 없음")
        else:
            st.info(f"표시할 공시 데이터가 없습니다. data_source={source}")
        return
    if "data_source" not in disclosures.columns:
        disclosures["data_source"] = source
    if disclosures["data_source"].isin(["SAMPLE_NO_API_KEY", "SAMPLE_FALLBACK"]).any():
        st.warning("샘플 또는 fallback 공시입니다. 실제 공시가 아닐 수 있습니다.")
    cols = st.columns(4)
    tag_counts = disclosures["risk_tag"].value_counts()
    cols[0].metric("critical", int(tag_counts.get("critical", 0)))
    cols[1].metric("risk", int(tag_counts.get("risk", 0)))
    cols[2].metric("caution", int(tag_counts.get("caution", 0)))
    cols[3].metric("positive", int(tag_counts.get("positive", 0)))
    high_risk = disclosures[disclosures["risk_tag"].isin(["critical", "risk"])].head(5)
    if high_risk.empty:
        st.info("최근 critical/risk 공시 요약이 없습니다.")
        return
    st.dataframe(
        localize_columns(
            high_risk[
                [
                    "corp_name",
                    "stock_code",
                    "report_nm",
                    "risk_tag",
                    "risk_score",
                    "data_source",
                ]
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def render_backtest_summary() -> None:
    st.subheader("백테스트 요약")
    latest = st.session_state.get("latest_backtest_result")
    if latest:
        cols = st.columns(4)
        cols[0].metric("총수익률", f"{latest.get('total_return', 0):.2f}%")
        cols[1].metric("MDD", f"{latest.get('mdd', 0):.2f}%")
        cols[2].metric("승률", f"{latest.get('win_rate', 0):.2f}%")
        cols[3].metric("Profit factor", f"{latest.get('profit_factor', 0):.2f}")
    else:
        st.info("최근 백테스트 결과가 없습니다. 백테스트 페이지에서 전략을 실행하세요.")
    st.write("사용 가능한 전략")
    st.dataframe(pd.DataFrame({"strategy": STRATEGIES}), hide_index=True)


def render_paper_trading_summary(provider: MarketDataProvider) -> None:
    st.subheader("모의매매 포트폴리오 요약")
    broker = MockBroker(data_provider=provider)
    try:
        summary = broker.get_portfolio_summary()
    except AttributeError:
        positions = broker.get_positions()
        summary = {
            "position_count": len(positions),
            "total_market_value_krw": sum(
                float(p["market_value_krw"])
                for p in positions
                if p.get("market_value_krw") is not None
            ),
            "total_cost_basis_krw": sum(
                float(p["cost_basis_krw"])
                for p in positions
                if p.get("cost_basis_krw") is not None
            ),
            "total_unrealized_pnl_krw": sum(
                float(p["unrealized_pnl_krw"])
                for p in positions
                if p.get("unrealized_pnl_krw") is not None
            ),
            "total_realized_pnl_krw": sum(
                float(p["realized_pnl_krw"])
                for p in positions
                if p.get("realized_pnl_krw") is not None
            ),
            "total_pnl_krw": sum(
                float(p["total_pnl_krw"])
                for p in positions
                if p.get("total_pnl_krw") is not None
            ),
            "top1_weight_krw": 0,
            "quote_error_count": sum(1 for p in positions if p.get("quote_error")),
            "fx_error_count": sum(1 for p in positions if p.get("fx_error")),
            "fx_rate": None,
        }
    if int(summary.get("position_count") or 0) == 0:
        st.info(
            "모의매매 포지션이 없습니다. 모의매매 페이지에서 가상 주문을 실행할 수 있습니다."
        )
        return
    cols = st.columns(8)
    cols[0].metric("보유 종목 수", int(summary.get("position_count") or 0))
    cols[1].metric(
        "총 평가금액 KRW",
        f"{float(summary.get('total_market_value_krw') or 0):,.0f}",
    )
    cols[2].metric(
        "총 매입금액 KRW",
        f"{float(summary.get('total_cost_basis_krw') or 0):,.0f}",
    )
    cols[3].metric(
        "총 손익 KRW",
        f"{float(summary.get('total_pnl_krw') or 0):,.0f}",
    )
    cols[4].metric(
        "상위 1개 비중 KRW",
        f"{float(summary.get('top1_weight_krw') or 0):.2f}%",
    )
    cols[5].metric("Quote error", int(summary.get("quote_error_count") or 0))
    cols[6].metric("FX error", int(summary.get("fx_error_count") or 0))
    cols[7].metric(
        "USD/KRW",
        f"{float(summary['fx_rate']):,.2f}" if summary.get("fx_rate") else "-",
    )
    if summary.get("fx_error_count"):
        st.warning("환율 조회 실패로 일부 US 포지션의 원화 환산 평가가 제한됩니다.")


def render_navigation_guide() -> None:
    st.subheader("페이지 이동 안내")
    st.caption("왼쪽 사이드바의 Pages 메뉴에서 각 기능 페이지로 이동할 수 있습니다.")
    st.dataframe(
        localize_columns(pd.DataFrame(PAGE_GUIDE, columns=["페이지", "설명"])),
        hide_index=True,
        width="stretch",
    )


def main() -> None:
    apply_theme()
    init_db()
    ensure_seed_watchlist()

    st.title("개인용 투자 대시보드")
    st.caption(
        "실제 주문 없이 데이터 조회, 스캐너, 공시, 백테스트, 모의매매 상태를 요약하는 MVP입니다."
    )
    provider = build_market_data_provider()
    render_data_warning(provider)

    watchlist = load_watchlist()
    watchlist_keys = [(item.symbol, item.market) for item in watchlist]
    quotes = load_watchlist_quotes(watchlist_keys, provider.mode)
    scored = load_scored_watchlist(watchlist_keys, provider.mode)
    disclosures = DartClient().search_disclosures(page_count=20)
    if provider.mode == "REAL_WITH_FALLBACK":
        sources: set[str] = set()
        for frame in [quotes, scored]:
            if not frame.empty and "data_source" in frame:
                sources.update(frame["data_source"].dropna().astype(str).tolist())
        provider.last_data_source = (
            "SAMPLE_FALLBACK" if "SAMPLE_FALLBACK" in sources else "REAL"
        )

    render_data_mode_section(provider)
    render_safety_status()

    render_watchlist_summary(summarize_watchlist(watchlist, quotes), watchlist)
    left, right = st.columns([1.5, 1])
    with left:
        render_scanner_summary(scored)
    with right:
        render_dart_summary(disclosures)

    left, right = st.columns(2)
    with left:
        render_backtest_summary()
    with right:
        render_paper_trading_summary(provider)

    render_navigation_guide()


if __name__ == "__main__":
    main()
