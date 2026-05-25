from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from src.broker.mock_broker import MockBroker
from src.database import get_session, init_db
from src.models import WatchlistItem
from src.risk.rebalancing_engine import PROFILE_TARGETS, RebalancingEngine
from src.scoring.portfolio_decision_engine import PortfolioDecisionEngine
from src.ui_helpers import (
    apply_plotly_dark_theme,
    build_market_data_provider,
    format_display_dataframe,
    format_metric_number,
    format_reliability_label,
    get_allocation_notice,
    get_stress_test_notice,
    inject_global_css,
    render_data_warning,
    render_metric_card,
    render_page_header,
)

RISK_COLUMNS = [
    "symbol",
    "market",
    "name",
    "asset_class",
    "position_weight_krw",
    "individual_volatility",
    "risk_contribution",
    "risk_weight_gap",
    "risk_evaluation",
    "reliability",
    "data_source",
]

TARGET_COLUMNS = [
    "asset_class",
    "current_weight",
    "target_weight",
    "weight_gap",
    "tolerance_pct",
    "is_outside_band",
    "rebalance_opinion",
    "target_total_weight",
    "target_total_status",
]

ALLOCATION_COLUMNS = [
    "symbol",
    "market",
    "name",
    "asset_class",
    "current_weight",
    "target_weight",
    "shortage_weight",
    "candidate_amount",
    "adjusted_amount",
    "allocation_reason",
    "limit_reason",
]


def load_watchlist_names() -> dict[tuple[str, str], str]:
    with get_session() as session:
        items = session.execute(select(WatchlistItem)).scalars().all()
        return {(item.market, item.symbol): item.name for item in items}


def enrich_position_names(
    positions: list[dict[str, object]], names: dict[tuple[str, str], str]
) -> list[dict[str, object]]:
    rows = []
    for position in positions:
        row = dict(position)
        key = (str(row.get("market", "")), str(row.get("symbol", "")))
        row["name"] = names.get(key, str(row.get("symbol", "")))
        rows.append(row)
    return rows


def render_summary(result) -> None:
    summary = result.risk_summary
    cols = st.columns(6)
    metrics = [
        ("보유 종목 수", int(summary.get("position_count") or 0), "neutral"),
        (
            "총 평가금액 KRW",
            format_metric_number(summary.get("total_market_value_krw"), 0),
            "info",
        ),
        ("상위 위험 기여", str(summary.get("top_risk_symbol") or "-"), "warning"),
        (
            "평균 상관관계",
            format_metric_number(summary.get("average_correlation"), 3),
            "neutral",
        ),
        (
            "최악 스트레스 손실률",
            format_metric_number(summary.get("worst_stress_loss_pct"), 2, "%"),
            "danger",
        ),
        (
            "데이터 신뢰도",
            format_reliability_label(summary.get("data_reliability")),
            "neutral",
        ),
    ]
    for col, (label, value, tone) in zip(cols, metrics, strict=True):
        with col:
            render_metric_card(label, value, tone=tone)


def render_risk_contribution(frame: pd.DataFrame) -> None:
    st.subheader("리스크 기여도")
    if frame.empty:
        st.info("리스크 기여도를 계산할 수 있는 포지션/수익률 데이터가 없습니다.")
        return
    view = frame[[column for column in RISK_COLUMNS if column in frame.columns]]
    st.dataframe(format_display_dataframe(view), hide_index=True, width="stretch")
    chart = frame.dropna(subset=["risk_contribution"])
    if chart.empty:
        st.info("리스크 기여도 차트 데이터가 없습니다.")
        return
    chart = chart.copy()
    chart["ticker"] = chart["market"].astype(str) + ":" + chart["symbol"].astype(str)
    st.plotly_chart(
        apply_plotly_dark_theme(
            px.bar(
                chart.sort_values("risk_contribution"),
                x="risk_contribution",
                y="ticker",
                orientation="h",
                title="종목별 위험 기여도",
            )
        ),
        width="stretch",
    )


def render_correlation(result) -> None:
    st.subheader("상관관계 매트릭스")
    matrix = result.correlation_matrix
    summary = result.correlation_summary
    st.caption(str(summary.get("diversification_comment", "")))
    cols = st.columns(3)
    cols[0].metric(
        "평균 상관관계",
        format_metric_number(summary.get("average_correlation"), 3),
    )
    cols[1].metric("최고 상관 쌍", str(summary.get("highest_pair") or "-"))
    cols[2].metric("최저 상관 쌍", str(summary.get("lowest_pair") or "-"))
    if matrix.empty:
        st.info("상관관계는 최소 2개 종목의 유효 수익률 데이터가 필요합니다.")
        return
    st.dataframe(format_display_dataframe(matrix), width="stretch")
    numeric_matrix = matrix.apply(pd.to_numeric, errors="coerce")
    if numeric_matrix.dropna(how="all").empty:
        st.info("상관관계 heatmap을 그릴 수 있는 숫자 데이터가 없습니다.")
        return
    st.plotly_chart(
        apply_plotly_dark_theme(
            px.imshow(
                numeric_matrix,
                text_auto=True,
                zmin=-1,
                zmax=1,
                color_continuous_scale="RdBu",
                title="상관관계 heatmap",
            )
        ),
        width="stretch",
    )


def render_stress_tests(frame: pd.DataFrame, selected: list[str]) -> None:
    st.subheader("스트레스 테스트")
    st.caption(get_stress_test_notice())
    if frame.empty:
        st.info("스트레스 테스트를 계산할 포지션 평가금액이 없습니다.")
        return
    view = frame[frame["scenario"].isin(selected)] if selected else frame
    st.dataframe(format_display_dataframe(view), hide_index=True, width="stretch")
    if view.empty:
        st.info("선택한 스트레스 시나리오 결과가 없습니다.")
        return
    st.plotly_chart(
        apply_plotly_dark_theme(
            px.bar(
                view.sort_values("stress_loss_pct"),
                x="stress_loss_pct",
                y="scenario",
                orientation="h",
                title="가정 시나리오 기준 추정 손실률",
            )
        ),
        width="stretch",
    )


def render_target_comparison(frame: pd.DataFrame) -> None:
    st.subheader("목표 비중 / 현재 비중 비교")
    if frame.empty:
        st.info("목표 비중 비교 데이터를 생성할 수 없습니다.")
        return
    status = frame["target_total_status"].dropna().iloc[0]
    total = frame["target_total_weight"].dropna().iloc[0]
    if abs(float(total) - 100) > 0.01:
        st.warning(str(status))
    else:
        st.caption(str(status))
    view = frame[[column for column in TARGET_COLUMNS if column in frame.columns]]
    st.dataframe(format_display_dataframe(view), hide_index=True, width="stretch")
    chart = frame.melt(
        id_vars="asset_class",
        value_vars=["current_weight", "target_weight"],
        var_name="weight_type",
        value_name="weight",
    )
    st.plotly_chart(
        apply_plotly_dark_theme(
            px.bar(
                chart,
                x="asset_class",
                y="weight",
                color="weight_type",
                barmode="group",
                title="현재 비중 vs 목표 비중",
            )
        ),
        width="stretch",
    )


def render_allocation_plan(frame: pd.DataFrame) -> None:
    st.subheader("추가 투자금 배분안")
    st.caption(get_allocation_notice())
    if frame.empty:
        st.info("추가 투자금이 없거나 배분 검토에 필요한 포지션 데이터가 없습니다.")
        return
    view = frame[[column for column in ALLOCATION_COLUMNS if column in frame.columns]]
    st.dataframe(format_display_dataframe(view), hide_index=True, width="stretch")
    chart = frame[pd.to_numeric(frame["adjusted_amount"], errors="coerce") > 0]
    if chart.empty:
        st.info("보정 후 배분 금액 차트 데이터가 없습니다.")
        return
    st.plotly_chart(
        apply_plotly_dark_theme(
            px.bar(
                chart,
                x="symbol",
                y="adjusted_amount",
                color="asset_class",
                title="추가매수 검토 배분안",
            )
        ),
        width="stretch",
    )


def render_comments(comments: list[str]) -> None:
    st.subheader("제한사항 / 데이터 신뢰도 안내")
    st.warning(
        "이 화면은 의사결정 보조 정보입니다. 실제 주문, 실제 체결, 실제 계좌 조회를 수행하지 않습니다."
    )
    st.info(
        "스트레스 테스트는 가정 기반 점검이며 실제 미래 손실 예측이나 성과 단정이 아닙니다."
    )
    for comment in comments:
        st.caption(comment)


def build_custom_targets(profile: str) -> dict[str, float]:
    defaults = PROFILE_TARGETS[profile]
    with st.expander("목표 비중 수동 수정", expanded=False):
        st.caption(
            "합계가 100%와 다를 수 있으며, 리밸런싱 검토용 기준으로만 사용합니다."
        )
        st.caption(
            "기본 제한: 개별 성장주 10%, 반도체/AI 30%, 단일 종목 40% 상한을 점검합니다."
        )
        targets = {}
        for category, value in defaults.items():
            targets[category] = st.number_input(
                f"{category} 목표 비중(%)",
                min_value=0.0,
                max_value=100.0,
                value=float(value),
                step=1.0,
            )
        total = sum(targets.values())
        if abs(total - 100) > 0.01:
            st.warning(
                f"목표 비중 합계가 {total:.1f}%입니다. 필요하면 100%로 조정하세요."
            )
        return targets


def main() -> None:
    st.set_page_config(page_title="리스크·리밸런싱 분석", layout="wide")
    inject_global_css()
    init_db()
    render_page_header(
        "리스크·리밸런싱 분석",
        "위험 기여도, 상관관계, 스트레스 테스트, 목표 비중을 통합 점검합니다.",
        badges=[("가정 기반 리스크 점검", "warning"), ("실제 주문 없음", "success")],
    )
    provider = build_market_data_provider()
    render_data_warning(provider)
    st.warning(
        "MockBroker 가상 포지션만 분석합니다. 실제 주문 또는 실제 계좌 조회는 없습니다."
    )

    profile = st.sidebar.selectbox(
        "리스크 프로필",
        list(PROFILE_TARGETS.keys()),
        index=list(PROFILE_TARGETS.keys()).index("균형 성장"),
    )
    additional_amount = st.sidebar.number_input(
        "추가 투자금 KRW",
        min_value=0,
        value=3_000_000,
        step=100_000,
    )
    tolerance = st.sidebar.number_input(
        "허용 범위(%p)",
        min_value=0.0,
        max_value=30.0,
        value=5.0,
        step=0.5,
    )
    custom_targets = build_custom_targets(profile)

    broker = MockBroker(data_provider=provider)
    positions = broker.get_positions()
    if not positions:
        st.info(
            "분석할 모의매매 포지션이 없습니다. 모의매매 페이지에서 가상 포지션을 입력하세요."
        )
        return
    positions = enrich_position_names(positions, load_watchlist_names())
    decision = PortfolioDecisionEngine().analyze(positions, provider)
    result = RebalancingEngine().analyze(
        positions,
        provider,
        profile=profile,
        target_weights=custom_targets,
        tolerance_pct=tolerance,
        additional_investment_krw=float(additional_amount),
        decision_frame=decision.positions,
    )

    render_summary(result)
    selected_scenarios = st.multiselect(
        "표시할 스트레스 시나리오",
        (
            result.stress_results["scenario"].tolist()
            if not result.stress_results.empty
            else []
        ),
        default=(
            result.stress_results["scenario"].tolist()
            if not result.stress_results.empty
            else []
        ),
    )
    render_risk_contribution(result.risk_contribution)
    render_correlation(result)
    render_stress_tests(result.stress_results, selected_scenarios)
    render_target_comparison(result.target_comparison)
    render_allocation_plan(result.allocation_plan)
    render_comments(result.comments)


main()
