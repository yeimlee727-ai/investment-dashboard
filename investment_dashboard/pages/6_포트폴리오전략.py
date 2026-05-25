from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from src.broker.mock_broker import MockBroker
from src.dart.dart_client import DartClient
from src.database import get_session, init_db
from src.models import WatchlistItem
from src.scoring.portfolio_decision_engine import (
    PortfolioDecisionEngine,
    PortfolioDecisionResult,
)
from src.ui_helpers import (
    apply_plotly_dark_theme,
    build_market_data_provider,
    format_display_dataframe,
    format_metric_number,
    format_reliability_label,
    inject_global_css,
    render_data_warning,
    render_metric_card,
    render_page_header,
)

SUMMARY_COLUMNS = [
    "symbol",
    "market",
    "name",
    "position_weight_krw",
    "total_pnl_pct",
    "trend_status",
    "return_3y",
    "mdd",
    "annualized_volatility",
    "rsi",
    "additional_buy_score",
    "additional_buy_opinion",
    "sell_review_score",
    "sell_review_opinion",
    "data_source",
    "reliability",
]

FLOW_COLUMNS = [
    "symbol",
    "market",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "return_3y",
    "cumulative_return",
    "drawdown_from_52w_high",
    "rebound_from_52w_low",
    "ma20_position",
    "ma60_position",
    "ma120_position",
    "ma240_position",
    "volume_ratio",
    "data_years",
    "reliability",
]


def load_watchlist_names() -> dict[tuple[str, str], str]:
    with get_session() as session:
        items = session.execute(select(WatchlistItem)).scalars().all()
        return {(item.market, item.symbol): item.name for item in items}


def enrich_position_names(
    positions: list[dict[str, object]], names: dict[tuple[str, str], str]
) -> list[dict[str, object]]:
    enriched = []
    for position in positions:
        row = dict(position)
        key = (str(row.get("market", "")), str(row.get("symbol", "")))
        row["name"] = names.get(key, str(row.get("symbol", "")))
        enriched.append(row)
    return enriched


@st.cache_data(ttl=900, show_spinner=False)
def run_analysis_cached(
    positions: list[dict[str, object]], data_mode: str
) -> PortfolioDecisionResult:
    provider = build_provider_for_cache(data_mode)
    disclosures = DartClient().search_disclosures(page_count=50)
    return PortfolioDecisionEngine().analyze(positions, provider, disclosures)


def build_provider_for_cache(data_mode: str):
    from src.data_providers.market_data_provider import MarketDataProvider

    return MarketDataProvider(mode=data_mode)  # type: ignore[arg-type]


def render_portfolio_summary(result: PortfolioDecisionResult) -> None:
    summary = result.portfolio_summary
    cols = st.columns(4)
    metrics = [
        (
            "총 평가금액 KRW",
            format_metric_number(summary.get("total_market_value_krw"), 0),
        ),
        (
            "총 매입금액 KRW",
            format_metric_number(summary.get("total_cost_basis_krw"), 0),
        ),
        ("총 손익 KRW", format_metric_number(summary.get("total_pnl_krw"), 0)),
        ("보유 종목 수", int(summary.get("position_count", 0))),
    ]
    for col, (label, value) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value)
    cols = st.columns(4)
    metrics = [
        ("상위 1개 비중", format_metric_number(summary.get("top1_weight"), 2, "%")),
        ("상위 3개 비중", format_metric_number(summary.get("top3_weight"), 2, "%")),
        ("데이터 신뢰도", format_reliability_label(summary.get("reliability"))),
        (
            "수익/손실 포지션",
            f"{summary.get('profit_position_count', 0)} / {summary.get('loss_position_count', 0)}",
        ),
    ]
    for col, (label, value) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value)
    cols = st.columns(4)
    metrics = [
        ("KR 비중", format_metric_number(summary.get("kr_weight"), 2, "%")),
        ("US 비중", format_metric_number(summary.get("us_weight"), 2, "%")),
        ("ETF 비중", format_metric_number(summary.get("etf_weight"), 2, "%")),
        ("개별주 비중", format_metric_number(summary.get("stock_weight"), 2, "%")),
    ]
    for col, (label, value) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value)
    st.caption(str(summary.get("concentration_comment", "")))


def render_decision_tables(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("분석할 가상 포지션이 없습니다.")
        return
    display = frame[[col for col in SUMMARY_COLUMNS if col in frame.columns]].copy()
    st.subheader("추가매수 우선순위")
    if "additional_buy_score" not in display.columns:
        st.info("추가매수 우선순위 계산 결과가 없습니다.")
    else:
        buy_view = display.sort_values("additional_buy_score", ascending=False).head(10)
        st.dataframe(
            format_display_dataframe(buy_view), hide_index=True, width="stretch"
        )
    st.subheader("매도 검토 신호")
    if "sell_review_score" not in display.columns:
        st.info("매도 검토 신호 계산 결과가 없습니다.")
    else:
        sell_view = display.sort_values("sell_review_score", ascending=False).head(10)
        st.dataframe(
            format_display_dataframe(sell_view), hide_index=True, width="stretch"
        )


def render_flow_analysis(frame: pd.DataFrame) -> None:
    st.subheader("종목별 3년 플로우 분석")
    if frame.empty:
        st.info("표시할 가격 흐름 분석이 없습니다.")
        return
    flow = frame[[col for col in FLOW_COLUMNS if col in frame.columns]].copy()
    st.dataframe(format_display_dataframe(flow), hide_index=True, width="stretch")


def render_charts(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("표시할 전략분석 차트 데이터가 없습니다.")
        return
    chart = frame.copy()
    chart["ticker"] = chart["market"] + ":" + chart["symbol"]
    if _has_numeric_data(chart, "additional_buy_score"):
        st.plotly_chart(
            apply_plotly_dark_theme(
                px.bar(
                    chart, x="ticker", y="additional_buy_score", title="추가매수 점수"
                )
            ),
            width="stretch",
        )
    if _has_numeric_data(chart, "sell_review_score"):
        st.plotly_chart(
            apply_plotly_dark_theme(
                px.bar(chart, x="ticker", y="sell_review_score", title="매도 검토 점수")
            ),
            width="stretch",
        )
    if _has_numeric_data(chart, "mdd"):
        st.plotly_chart(
            apply_plotly_dark_theme(
                px.bar(chart, x="ticker", y="mdd", title="종목별 MDD 비교")
            ),
            width="stretch",
        )
    if not {"additional_buy_score", "sell_review_score", "mdd"} & set(chart.columns):
        st.info("계산 가능한 전략분석 차트 지표가 없습니다.")
    weight_chart = (
        chart.dropna(subset=["position_weight_krw"])
        if "position_weight_krw" in chart.columns
        else pd.DataFrame()
    )
    if not weight_chart.empty:
        st.plotly_chart(
            apply_plotly_dark_theme(
                px.pie(
                    weight_chart,
                    names="ticker",
                    values="position_weight_krw",
                    title="포트폴리오 비중(원화 기준)",
                )
            ),
            width="stretch",
        )


def render_price_flow_chart(price_history: pd.DataFrame) -> None:
    st.subheader("종목별 3년 가격 흐름")
    if price_history.empty:
        st.info("표시할 3년 가격 흐름 데이터가 없습니다.")
        return
    chart = price_history.copy()
    if not _has_numeric_data(chart, "normalized_price"):
        st.info("가격 흐름 차트를 계산할 수 있는 데이터가 부족합니다.")
        return
    chart["ticker"] = chart["market"] + ":" + chart["symbol"]
    st.plotly_chart(
        apply_plotly_dark_theme(
            px.line(
                chart,
                x="date",
                y="normalized_price",
                color="ticker",
                title="3년 가격 흐름(시작점=100)",
            )
        ),
        width="stretch",
    )


def render_scenarios(result: PortfolioDecisionResult) -> None:
    st.subheader("종목별 시나리오 전망")
    if result.scenarios.empty:
        st.info("표시할 시나리오가 없습니다.")
        return
    st.dataframe(
        format_display_dataframe(result.scenarios), hide_index=True, width="stretch"
    )


def render_comments(result: PortfolioDecisionResult) -> None:
    st.subheader("리밸런싱 코멘트")
    for comment in result.rebalance_comments:
        st.info(comment)
    st.subheader("데이터 신뢰도 / 제한사항")
    st.warning(
        "이 페이지는 의사결정 보조 정보입니다. 직접적인 매수/매도 지시, "
        "성과 단정, 정확한 미래 예측을 제공하지 않습니다."
    )
    if (
        not result.positions.empty
        and result.positions["reliability"].isin(["LOW", "UNKNOWN"]).any()
    ):
        st.warning(
            "일부 종목은 SAMPLE/FALLBACK 또는 데이터 부족으로 신뢰도가 낮습니다."
        )


def _has_numeric_data(frame: pd.DataFrame, column: str) -> bool:
    if column not in frame.columns:
        return False
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.notna().any()


def main() -> None:
    st.set_page_config(page_title="포트폴리오 전략분석", layout="wide")
    inject_global_css()
    init_db()
    render_page_header(
        "포트폴리오 전략분석",
        "가상 포지션의 가격 흐름, 추세, 데이터 신뢰도, 검토 신호를 요약합니다.",
        badges=[("의사결정 보조 정보", "info"), ("실제 주문 없음", "success")],
    )
    provider = build_market_data_provider()
    render_data_warning(provider)
    st.warning(
        "실제 주문, 실제 체결, 실제 계좌 조회 없이 MockBroker 가상 포지션만 분석합니다."
    )

    broker = MockBroker(data_provider=provider)
    positions = broker.get_positions()
    if not positions:
        st.info(
            "분석할 모의매매 포지션이 없습니다. 모의매매 페이지에서 가상 포지션을 생성하세요."
        )
        return
    positions = enrich_position_names(positions, load_watchlist_names())
    with st.spinner("포트폴리오 가격 흐름과 리스크를 분석 중입니다."):
        result = run_analysis_cached(positions, provider.mode)

    render_portfolio_summary(result)
    render_decision_tables(result.positions)
    render_flow_analysis(result.positions)
    render_price_flow_chart(result.price_history)
    render_charts(result.positions)
    render_scenarios(result)
    render_comments(result)


main()
