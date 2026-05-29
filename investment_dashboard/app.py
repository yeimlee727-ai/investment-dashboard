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
from src.reporting.report_exporter import (
    build_excel_report,
    build_html_report,
    build_report_from_provider,
    report_file_name,
)
from src.risk.rebalancing_engine import RebalancingEngine
from src.scanner.stock_scanner import StockScanner
from src.scoring.portfolio_decision_engine import PortfolioDecisionEngine
from src.scoring.scoring_engine import ScoringEngine
from src.ui_helpers import (
    apply_plotly_dark_theme,
    build_market_data_provider,
    format_display_dataframe,
    format_metric_number,
    format_reliability_label,
    get_data_mode_status,
    inject_global_css,
    localize_columns,
    render_alert,
    render_data_warning,
    render_metric_card,
    render_page_header,
    safe_krw,
    safe_percent,
    security_display_label,
)

STRATEGIES = ["EMA20 상향 돌파 + 거래량 증가", "RSI 30 이하 반등", "신고가 돌파"]
PAGE_GUIDE = [
    ("관심종목", "국내/미국 종목코드, 섹터, 메모를 관리합니다."),
    ("종목스캐너", "거래량, RSI, EMA, 신고가 근접 등 조건을 점검합니다."),
    ("DART공시", "공시 유형과 위험 신호를 확인합니다."),
    ("백테스트", "전략 성과를 리포트 형태로 검증합니다."),
    ("모의매매", "MockBroker 기반 가상 주문과 포지션을 확인합니다."),
    (
        "포트폴리오전략",
        "보유 가상 포지션의 추가매수 후보와 매도 검토 신호를 점검합니다.",
    ),
    (
        "리스크리밸런싱",
        "위험 기여도, 상관관계, 스트레스 테스트, 목표 비중을 점검합니다.",
    ),
]


def apply_theme() -> None:
    st.set_page_config(page_title="Investment Dashboard", layout="wide")
    inject_global_css()


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
    with cols[0]:
        render_metric_card(
            "현재 모드", badge, tone="info" if level == "info" else "warning"
        )
    with cols[1]:
        render_metric_card("Provider", provider.get_provider_name())
    with cols[2]:
        render_metric_card("마지막 데이터 출처", provider.last_data_source)
    if level == "info":
        render_alert(f"{badge}: {message}", "info")
    else:
        render_alert(f"{badge}: {message}", "warning")
    if provider.last_error:
        st.caption(f"최근 조회 메시지: {provider.last_error}")


def render_safety_status() -> None:
    st.subheader("시스템 안전 상태")
    cols = st.columns(5)
    metrics = [
        ("실제 주문 기능", "없음", "success"),
        ("TossBroker", "Placeholder", "neutral"),
        ("MockBroker", "가상 주문", "info"),
        ("실제 계좌 조회", "없음", "success"),
        ("API Key 화면 노출", "없음", "success"),
    ]
    for col, (label, value, tone) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value, tone=tone)
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
    metrics = [
        ("관심종목 수", summary["total"], "neutral"),
        ("KR 종목", summary["kr_count"], "neutral"),
        ("US 종목", summary["us_count"], "neutral"),
        ("조회 성공", summary["quote_success_count"], "success"),
        ("Fallback", summary["fallback_count"], "warning"),
        ("Quote error", summary["quote_error_count"], "danger"),
    ]
    for col, (label, value, tone) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value, tone=tone)


def build_scanner_summary_view(
    scored: pd.DataFrame, watchlist: list[WatchlistItem] | None = None
) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame()
    view = scored.sort_values("score", ascending=False).head(7).copy()
    name_lookup = {
        (str(item.market).upper(), str(item.symbol).upper()): item.name
        for item in watchlist or []
    }
    for optional in ["risk_tag", "risk_penalty", "data_source"]:
        if optional not in view.columns:
            view[optional] = ""

    def row_name(row: pd.Series) -> str:
        existing = str(row.get("name") or row.get("종목명") or "").strip()
        if existing:
            return existing
        key = (str(row.get("market", "")).upper(), str(row.get("symbol", "")).upper())
        return str(name_lookup.get(key, "") or "")

    view["display_label"] = view.apply(
        lambda row: security_display_label(row_name(row), row.get("symbol")),
        axis=1,
    )
    return view


def render_scanner_summary(
    scored: pd.DataFrame, watchlist: list[WatchlistItem] | None = None
) -> None:
    st.subheader("스캐너 상위 종목 요약")
    if scored.empty:
        st.info("스캐너 요약을 표시할 데이터가 없습니다.")
        return
    view = build_scanner_summary_view(scored, watchlist)
    columns = [
        "display_label",
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
    hover_data: dict[str, bool | str] = {
        "display_label": False,
        "symbol": True,
        "market": True,
        "score": ":.2f",
    }
    if "change_pct" in view.columns:
        hover_data["change_pct"] = ":.2f"
    if "volume_ratio" in view.columns:
        hover_data["volume_ratio"] = ":.2f"
    fig = px.bar(
        view.sort_values("score"),
        x="score",
        y="display_label",
        orientation="h",
        title="상위 종목 점수",
        labels={"score": "점수", "display_label": "종목명"},
        hover_data=hover_data,
    )
    fig.update_layout(height=max(340, 52 * len(view) + 120))
    fig.update_yaxes(title_text="")
    st.plotly_chart(apply_plotly_dark_theme(fig), width="stretch")
    st.caption("점수는 스캐너 요약 지표이며 매수/매도 실행 지시가 아닙니다.")


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
        metrics = [
            ("총수익률", safe_percent(latest.get("total_return")), "positive"),
            ("MDD", safe_percent(latest.get("mdd")), "warning"),
            ("승률", safe_percent(latest.get("win_rate")), "info"),
            (
                "Profit factor",
                format_metric_number(latest.get("profit_factor"), 2),
                "neutral",
            ),
        ]
        for col, (label, value, tone) in zip(cols, metrics, strict=True):
            with col:
                render_metric_card(label, value, tone=tone)
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
    metrics = [
        ("보유 종목 수", int(summary.get("position_count") or 0), "neutral"),
        ("총 평가금액 KRW", safe_krw(summary.get("total_market_value_krw")), "info"),
        ("총 매입금액 KRW", safe_krw(summary.get("total_cost_basis_krw")), "neutral"),
        ("총 손익 KRW", safe_krw(summary.get("total_pnl_krw")), "positive"),
        ("상위 1개 비중 KRW", safe_percent(summary.get("top1_weight_krw")), "warning"),
        ("Quote error", int(summary.get("quote_error_count") or 0), "danger"),
        ("FX error", int(summary.get("fx_error_count") or 0), "danger"),
        (
            "USD/KRW",
            format_metric_number(summary.get("fx_rate"), 2, unavailable="-"),
            "neutral",
        ),
    ]
    for col, (label, value, tone) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value, tone=tone)
    if summary.get("fx_error_count"):
        st.warning("환율 조회 실패로 일부 US 포지션의 원화 환산 평가가 제한됩니다.")
    st.caption("통합 포트폴리오 비중은 원화 환산 평가금액 기준입니다.")


def render_home_portfolio_charts(provider: MarketDataProvider) -> None:
    st.subheader("포트폴리오 차트")
    broker = MockBroker(data_provider=provider)
    positions = pd.DataFrame(broker.get_positions())
    if positions.empty or "market_value_krw" not in positions.columns:
        st.info("표시할 모의매매 포트폴리오 차트 데이터가 없습니다.")
        return
    positions = positions.dropna(subset=["market_value_krw"]).copy()
    if positions.empty:
        st.warning("현재가 또는 환율 조회 실패로 포트폴리오 차트를 표시할 수 없습니다.")
        return
    positions["ticker"] = (
        positions["market"].astype(str) + ":" + positions["symbol"].astype(str)
    )
    st.caption(
        "포트폴리오 비중 차트는 원화 환산 평가금액 기준입니다. "
        "US 종목은 USD 현재가와 USD/KRW 환율을 함께 반영합니다."
    )
    weight_fig = px.pie(
        positions,
        names="ticker",
        values="market_value_krw",
        title="포트폴리오 비중(원화 기준)",
        hole=0.45,
    )
    st.plotly_chart(apply_plotly_dark_theme(weight_fig), width="stretch")
    if "total_pnl_krw" in positions.columns:
        pnl_fig = px.bar(
            positions.sort_values("total_pnl_krw"),
            x="ticker",
            y="total_pnl_krw",
            title="종목별 총손익(원화 기준)",
        )
        st.plotly_chart(apply_plotly_dark_theme(pnl_fig), width="stretch")


def render_portfolio_decision_summary(provider: MarketDataProvider) -> None:
    st.subheader("포트폴리오 전략분석 요약")
    broker = MockBroker(data_provider=provider)
    positions = broker.get_positions()
    if not positions:
        st.info(
            "분석할 모의매매 포지션이 없습니다. 자세히 보기: 포트폴리오 전략분석 페이지"
        )
        return
    try:
        result = PortfolioDecisionEngine().analyze(positions, provider)
    except Exception as exc:
        st.warning(f"포트폴리오 전략분석 요약을 생성하지 못했습니다: {exc}")
        return
    frame = result.positions
    if frame.empty:
        st.info("포트폴리오 전략분석 결과가 없습니다.")
        return
    cols = st.columns(4)
    cols[0].metric(
        "상위 1개 비중",
        format_metric_number(result.portfolio_summary.get("top1_weight"), 2, "%"),
    )
    cols[1].metric(
        "상위 3개 비중",
        format_metric_number(result.portfolio_summary.get("top3_weight"), 2, "%"),
    )
    cols[2].metric(
        "데이터 신뢰도",
        format_reliability_label(result.portfolio_summary.get("reliability")),
    )
    cols[3].metric("분석 종목 수", len(frame))
    st.caption("자세히 보기: 포트폴리오 전략분석 페이지")
    display_columns = [
        "symbol",
        "market",
        "additional_buy_score",
        "additional_buy_opinion",
        "sell_review_score",
        "sell_review_opinion",
        "reliability",
    ]
    buy = frame.sort_values("additional_buy_score", ascending=False).head(3)
    sell = frame.sort_values("sell_review_score", ascending=False).head(3)
    st.write("추가매수 우선 후보")
    st.dataframe(
        format_display_dataframe(
            buy[[col for col in display_columns if col in buy.columns]]
        ),
        hide_index=True,
        width="stretch",
    )
    st.write("매도 검토 신호 상위")
    st.dataframe(
        format_display_dataframe(
            sell[[col for col in display_columns if col in sell.columns]]
        ),
        hide_index=True,
        width="stretch",
    )


def render_rebalancing_summary(provider: MarketDataProvider) -> None:
    st.subheader("리스크·리밸런싱 요약")
    broker = MockBroker(data_provider=provider)
    positions = broker.get_positions()
    if not positions:
        st.info(
            "분석할 모의매매 포지션이 없습니다. 자세히 보기: 리스크·리밸런싱 분석 페이지"
        )
        return
    try:
        decision = PortfolioDecisionEngine().analyze(positions, provider)
        result = RebalancingEngine().analyze(
            positions,
            provider,
            additional_investment_krw=3_000_000,
            decision_frame=decision.positions,
        )
    except Exception as exc:
        st.warning(f"리스크·리밸런싱 요약을 생성하지 못했습니다: {exc}")
        return
    summary = result.risk_summary
    cols = st.columns(5)
    cols[0].metric("상위 위험 기여", str(summary.get("top_risk_symbol") or "-"))
    cols[1].metric(
        "평균 상관관계",
        format_metric_number(summary.get("average_correlation"), 3),
    )
    cols[2].metric(
        "최악 스트레스 손실률",
        format_metric_number(summary.get("worst_stress_loss_pct"), 2, "%"),
    )
    cols[3].metric("목표 범위 이탈", int(summary.get("overweight_count") or 0))
    cols[4].metric("신뢰도", format_reliability_label(summary.get("data_reliability")))
    allocation = result.allocation_plan
    if allocation.empty:
        st.info("추가 투자금 배분안 요약 데이터가 없습니다.")
    else:
        candidates = allocation[
            (pd.to_numeric(allocation["adjusted_amount"], errors="coerce") > 0)
            & (allocation["symbol"].astype(str) != "CASH")
        ].head(3)
        if candidates.empty:
            st.info("현재 기준 추가 배분 후보가 제한되어 있습니다.")
        else:
            st.write("추가 투자금 배분안 상위 후보")
            st.dataframe(
                format_display_dataframe(
                    candidates[
                        [
                            "symbol",
                            "market",
                            "asset_class",
                            "adjusted_amount",
                            "allocation_reason",
                            "limit_reason",
                        ]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
    st.caption("자세히 보기: 리스크·리밸런싱 분석 페이지")


def render_home_kpi_strip(provider: MarketDataProvider) -> None:
    broker = MockBroker(data_provider=provider)
    summary = broker.get_portfolio_summary()
    cols = st.columns(8)
    metrics = [
        ("총 평가금액", safe_krw(summary.get("total_market_value_krw")), "info"),
        ("총 매입금액", safe_krw(summary.get("total_cost_basis_krw")), "neutral"),
        ("총 손익", safe_krw(summary.get("total_pnl_krw")), "positive"),
        ("총 손익률", safe_percent(summary.get("total_pnl_pct")), "positive"),
        ("보유 종목 수", int(summary.get("position_count") or 0), "neutral"),
        ("상위 1개 비중", safe_percent(summary.get("top1_weight_krw")), "warning"),
        ("현재가 오류", int(summary.get("quote_error_count") or 0), "danger"),
        ("환율 오류", int(summary.get("fx_error_count") or 0), "danger"),
    ]
    for col, (label, value, tone) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value, tone=tone)


def render_report_download_section(provider: MarketDataProvider) -> None:
    st.subheader("리포트 다운로드")
    st.caption(
        "MockBroker 가상 포지션과 앱 내부 분석 결과를 기반으로 한 포트폴리오 점검 리포트입니다. "
        "투자 추천이나 실제 주문 실행 기능이 아닙니다."
    )
    if st.button("포트폴리오 점검 리포트 생성", type="secondary"):
        try:
            report = build_report_from_provider(provider)
            st.session_state["portfolio_report_excel"] = build_excel_report(report)
            st.session_state["portfolio_report_html"] = build_html_report(report)
            st.session_state["portfolio_report_generated_at"] = report.generated_at
            st.success("리포트 파일을 생성했습니다. 아래 다운로드 버튼을 사용하세요.")
        except Exception as exc:
            st.error(f"리포트 생성 중 오류가 발생했습니다: {exc}")
            return
    generated_at = st.session_state.get("portfolio_report_generated_at")
    excel_bytes = st.session_state.get("portfolio_report_excel")
    html_text = st.session_state.get("portfolio_report_html")
    if excel_bytes:
        st.download_button(
            "Excel 리포트 다운로드",
            data=excel_bytes,
            file_name=report_file_name("xlsx", str(generated_at)),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if html_text:
        st.download_button(
            "HTML 리포트 다운로드",
            data=str(html_text).encode("utf-8"),
            file_name=report_file_name("html", str(generated_at)),
            mime="text/html",
        )
        st.caption(
            "HTML 리포트는 브라우저에서 열어 인쇄 기능으로 PDF 저장할 수 있습니다."
        )


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

    provider = build_market_data_provider()
    badge, _, level = get_data_mode_status(provider.mode, provider.is_fallback_mode())
    render_page_header(
        "개인용 투자 대시보드",
        "실제 주문 없이 데이터 조회, 스캐너, 공시, 백테스트, 모의매매 상태를 한 화면에서 점검합니다.",
        badges=[
            (badge, "info" if level == "info" else "warning"),
            ("실제 주문 없음", "success"),
            ("MockBroker 가상 주문", "info"),
        ],
    )
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
    render_home_kpi_strip(provider)
    render_report_download_section(provider)

    render_watchlist_summary(summarize_watchlist(watchlist, quotes), watchlist)
    left, right = st.columns([1.5, 1])
    with left:
        render_scanner_summary(scored, watchlist)
    with right:
        render_dart_summary(disclosures)

    left, right = st.columns(2)
    with left:
        render_backtest_summary()
    with right:
        render_paper_trading_summary(provider)

    render_home_portfolio_charts(provider)
    render_portfolio_decision_summary(provider)
    render_rebalancing_summary(provider)
    render_navigation_guide()


if __name__ == "__main__":
    main()
