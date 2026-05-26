from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_providers.base import DataMode
from src.data_providers.market_data_provider import MarketDataProvider

KOREAN_COLUMN_LABELS = {
    "symbol": "종목코드",
    "name": "종목명",
    "market": "시장",
    "sector": "섹터",
    "memo": "메모",
    "latest_price": "최근가",
    "change_pct": "등락률(%)",
    "data_source": "데이터 출처",
    "provider": "데이터 제공자",
    "quote_error": "시세 오류",
    "as_of": "기준시각",
    "score": "점수",
    "volume_ratio": "거래량 비율",
    "risk_tag": "리스크 태그",
    "risk_penalty": "리스크 감점",
    "currency": "통화",
    "quantity": "수량",
    "avg_price": "평균단가",
    "current_price": "현재가",
    "market_value": "평가금액(원통화)",
    "market_value_krw": "평가금액(원화)",
    "cost_basis": "매입금액",
    "cost_basis_krw": "매입금액(원화)",
    "unrealized_pnl": "평가손익",
    "unrealized_pnl_krw": "평가손익(원화)",
    "unrealized_pnl_pct": "평가손익률(%)",
    "realized_pnl": "실현손익",
    "realized_pnl_krw": "실현손익(원화)",
    "realized_pnl_pct": "실현손익률(%)",
    "total_pnl": "총손익",
    "total_pnl_krw": "총손익(원화)",
    "total_pnl_pct": "총손익률(%)",
    "position_weight": "비중",
    "position_weight_krw": "비중(원화 기준)",
    "fx_rate": "적용 환율",
    "fx_data_source": "환율 출처",
    "fx_error": "환율 오류",
    "updated_at": "갱신시각",
    "created_at": "생성시각",
    "side": "구분",
    "price": "가격",
    "status": "상태",
    "reason": "사유",
    "error_message": "오류 메시지",
    "realized_at": "실현시각",
    "entry_price": "진입가",
    "exit_price": "청산가",
    "holding_days": "보유일수",
    "exit_reason": "청산사유",
    "ticker": "종목",
    "corp_name": "기업명",
    "stock_code": "종목코드",
    "report_nm": "공시명",
    "risk_score": "위험 점수",
    "trend_status": "추세 상태",
    "data_days": "데이터 일수",
    "data_years": "데이터 기간(년)",
    "reliability": "신뢰도",
    "reliability_reason": "신뢰도 사유",
    "return_1m": "1개월 수익률(%)",
    "return_3m": "3개월 수익률(%)",
    "return_6m": "6개월 수익률(%)",
    "return_1y": "1년 수익률(%)",
    "return_3y": "3년 수익률(%)",
    "cumulative_return": "누적 수익률(%)",
    "annualized_volatility": "연환산 변동성(%)",
    "mdd": "MDD(%)",
    "drawdown_from_52w_high": "52주 고점 대비(%)",
    "rebound_from_52w_low": "52주 저점 대비(%)",
    "ma20_position": "20일선 대비(%)",
    "ma60_position": "60일선 대비(%)",
    "ma120_position": "120일선 대비(%)",
    "ma240_position": "240일선 대비(%)",
    "rsi": "RSI",
    "additional_buy_score": "추가매수 점수",
    "additional_buy_opinion": "추가매수 의견",
    "sell_review_score": "매도검토 점수",
    "sell_review_opinion": "매도검토 의견",
    "decision_comment": "분석 코멘트",
    "upside": "상승 시나리오",
    "neutral": "중립 시나리오",
    "downside": "하락 시나리오",
    "asset_class": "자산군",
    "individual_volatility": "개별 변동성(%)",
    "risk_contribution": "위험 기여도(%)",
    "risk_weight_gap": "위험-비중 차이(%p)",
    "risk_evaluation": "위험 기여도 평가",
    "scenario": "시나리오",
    "stress_loss_krw": "가정 시나리오 기준 추정 손실(KRW)",
    "stress_loss_pct": "가정 시나리오 기준 추정 손실률(%)",
    "largest_loss_symbol": "최대 손실 기여 종목",
    "comment": "코멘트",
    "current_weight": "현재 비중(%)",
    "target_weight": "목표 비중(%)",
    "weight_gap": "비중 차이(%p)",
    "tolerance_pct": "허용 범위(%p)",
    "is_outside_band": "허용 범위 초과",
    "rebalance_opinion": "리밸런싱 검토 의견",
    "target_total_weight": "목표 비중 합계(%)",
    "target_total_status": "목표 비중 상태",
    "shortage_weight": "부족 비중(%p)",
    "candidate_amount": "후보 금액(KRW)",
    "adjusted_amount": "보정 후 금액(KRW)",
    "allocation_reason": "배분 사유",
    "limit_reason": "제한 사유",
    "페이지": "페이지",
    "설명": "설명",
}

RELIABILITY_LABELS = {
    "HIGH": "높음",
    "MEDIUM": "보통",
    "LOW": "낮음",
    "UNKNOWN": "알 수 없음",
}

TONE_COLORS = {
    "neutral": "#94a3b8",
    "info": "#38bdf8",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "positive": "#22c55e",
    "negative": "#ef4444",
}

PROHIBITED_DECISION_WORDS = [
    "매수 추천",
    "매도 추천",
    "지금 사야",
    "지금 팔아",
    "강력 매수",
    "수익 보장",
    "확정 전망",
]


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --bg: #080b12;
          --panel: #111827;
          --panel-soft: #151d2c;
          --border: rgba(148, 163, 184, 0.22);
          --text: #e5e7eb;
          --muted: #94a3b8;
          --accent: #38bdf8;
          --good: #22c55e;
          --bad: #ef4444;
          --warn: #f59e0b;
        }
        .stApp {
          background:
            radial-gradient(circle at top left, rgba(56, 189, 248, 0.10), transparent 34rem),
            linear-gradient(180deg, #080b12 0%, #0b1020 100%);
          color: var(--text);
        }
        section[data-testid="stSidebar"] {
          background: linear-gradient(180deg, #0b1020 0%, #111827 100%);
          border-right: 1px solid var(--border);
        }
        .block-container { padding-top: 1.25rem; padding-bottom: 3rem; }
        h1, h2, h3 { letter-spacing: 0; }
        div[data-testid="stMetric"] {
          background: linear-gradient(180deg, rgba(17, 24, 39, 0.96), rgba(15, 23, 42, 0.92));
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 0.9rem 1rem;
          box-shadow: 0 12px 30px rgba(0,0,0,0.22);
        }
        [data-testid="stMetricValue"] { color: #f8fafc; font-weight: 700; }
        [data-testid="stMetricLabel"] { color: var(--muted); }
        div[data-testid="stDataFrame"] {
          border: 1px solid var(--border);
          border-radius: 8px;
          overflow: hidden;
        }
        .premium-header, .premium-card, .premium-alert {
          background: linear-gradient(180deg, rgba(17, 24, 39, 0.94), rgba(15, 23, 42, 0.90));
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 1rem;
          box-shadow: 0 16px 40px rgba(0,0,0,0.24);
        }
        .premium-header { padding: 1.2rem 1.3rem; margin-bottom: 1rem; }
        .premium-eyebrow {
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 700;
          text-transform: uppercase;
          margin-bottom: 0.25rem;
        }
        .premium-title { font-size: 1.9rem; font-weight: 780; margin: 0; }
        .premium-desc { color: var(--muted); margin-top: 0.35rem; line-height: 1.5; }
        .chip-row { display: flex; gap: 0.45rem; flex-wrap: wrap; margin-top: 0.85rem; }
        .status-chip {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          border: 1px solid currentColor;
          border-radius: 999px;
          padding: 0.24rem 0.62rem;
          font-size: 0.78rem;
          font-weight: 700;
          background: rgba(15, 23, 42, 0.72);
        }
        .premium-alert {
          border-left: 4px solid var(--accent);
          color: #dbeafe;
          margin: 0.45rem 0;
        }
        .premium-alert.warning { border-left-color: var(--warn); color: #fde68a; }
        .premium-alert.danger { border-left-color: var(--bad); color: #fecaca; }
        .premium-alert.success { border-left-color: var(--good); color: #bbf7d0; }
        .metric-card-label { color: var(--muted); font-size: 0.78rem; font-weight: 700; }
        .metric-card-value { color: #f8fafc; font-size: 1.35rem; font-weight: 780; margin-top: 0.22rem; }
        .metric-card-delta { font-size: 0.82rem; margin-top: 0.2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def korean_column_name(column: str) -> str:
    return KOREAN_COLUMN_LABELS.get(column, column)


def _html_escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_status_chip(label: str, tone: str = "neutral") -> None:
    color = TONE_COLORS.get(tone, TONE_COLORS["neutral"])
    st.markdown(
        f'<span class="status-chip" style="color:{color}">{_html_escape(label)}</span>',
        unsafe_allow_html=True,
    )


def render_page_header(
    title: str,
    description: str,
    badges: list[tuple[str, str]] | None = None,
    eyebrow: str = "Investment Dashboard",
) -> None:
    chips = "".join(
        (
            f'<span class="status-chip" style="color:{TONE_COLORS.get(tone, TONE_COLORS["neutral"])}">'
            f"{_html_escape(label)}</span>"
        )
        for label, tone in (badges or [])
    )
    st.markdown(
        f"""
        <div class="premium-header">
          <div class="premium-eyebrow">{_html_escape(eyebrow)}</div>
          <div class="premium-title">{_html_escape(title)}</div>
          <div class="premium-desc">{_html_escape(description)}</div>
          <div class="chip-row">{chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(
    label: str,
    value: object,
    delta: object | None = None,
    tone: str = "neutral",
    help_text: str | None = None,
) -> None:
    color = TONE_COLORS.get(tone, TONE_COLORS["neutral"])
    delta_html = (
        f'<div class="metric-card-delta" style="color:{color}">{_html_escape(delta)}</div>'
        if delta is not None
        else ""
    )
    help_html = (
        f'<div class="premium-desc" style="font-size:0.78rem">{_html_escape(help_text)}</div>'
        if help_text
        else ""
    )
    st.markdown(
        f"""
        <div class="premium-card">
          <div class="metric-card-label">{_html_escape(label)}</div>
          <div class="metric-card-value">{_html_escape(value)}</div>
          {delta_html}
          {help_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_alert(message: str, tone: str = "info") -> None:
    st.markdown(
        f'<div class="premium-alert {tone}">{_html_escape(message)}</div>',
        unsafe_allow_html=True,
    )


def localize_columns(
    rows_or_frame: object,
) -> object:
    if hasattr(rows_or_frame, "rename"):
        return rows_or_frame.rename(columns=KOREAN_COLUMN_LABELS)  # type: ignore[no-any-return]
    if isinstance(rows_or_frame, list):
        return [
            {korean_column_name(str(key)): value for key, value in row.items()}
            for row in rows_or_frame
            if isinstance(row, dict)
        ]
    return rows_or_frame


def format_calculation_value(value: object) -> object:
    if value is None:
        return "계산 불가"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "계산 불가"
    if isinstance(value, str) and value.strip().lower() in {"nan", "inf", "-inf"}:
        return "계산 불가"
    return value


def safe_display_value(value: object, unavailable: str = "-") -> str:
    if value is None:
        return unavailable
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return unavailable
    text = str(value)
    if text.strip().lower() in {"nan", "inf", "-inf", "none"}:
        return unavailable
    return text


def safe_krw(value: object, unavailable: str = "-") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return unavailable
    if math.isnan(number) or math.isinf(number):
        return unavailable
    return f"{number:,.0f}원"


def safe_percent(value: object, decimals: int = 2, unavailable: str = "-") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return unavailable
    if math.isnan(number) or math.isinf(number):
        return unavailable
    return f"{number:,.{decimals}f}%"


def _format_table_value(column: str, value: object) -> object:
    value = format_calculation_value(value)
    if isinstance(value, str):
        return value
    if any(keyword in column for keyword in ["KRW", "금액", "손익", "수수료", "비용"]):
        return safe_krw(value, unavailable="계산 불가")
    if any(keyword in column for keyword in ["비중", "수익률", "등락률", "MDD", "(%)"]):
        return safe_percent(value, unavailable="계산 불가")
    if any(keyword in column for keyword in ["점수", "비율", "환율", "가격", "단가"]):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return value
        if math.isnan(number) or math.isinf(number):
            return "계산 불가"
        return f"{number:,.2f}"
    return value


def format_display_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    localized = localize_columns(frame.copy())
    if not isinstance(localized, pd.DataFrame):
        return frame
    formatted = localized.copy()
    for column in formatted.columns:
        formatted[column] = formatted[column].map(
            lambda value, col=str(column): _format_table_value(col, value)
        )
    return formatted


def format_reliability_label(value: object) -> str:
    level = str(value or "UNKNOWN").upper()
    return RELIABILITY_LABELS.get(level, "알 수 없음")


def contains_prohibited_decision_wording(text: str) -> bool:
    return any(word in text for word in PROHIBITED_DECISION_WORDS)


def format_metric_number(
    value: object,
    decimals: int = 0,
    suffix: str = "",
    unavailable: str = "계산 불가",
) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return unavailable
    if math.isnan(number) or math.isinf(number):
        return unavailable
    return f"{number:,.{decimals}f}{suffix}"


def apply_plotly_dark_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e5e7eb", "family": "Inter, Arial, sans-serif"},
        title={"font": {"size": 16}, "x": 0.02, "xanchor": "left"},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        margin={"l": 30, "r": 24, "t": 56, "b": 36},
        hovermode="closest",
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(148, 163, 184, 0.16)", zeroline=False)
    return fig


def mock_delete_warning_message() -> str:
    return (
        "이 삭제 기능은 MockBroker 기반 테스트 데이터 정리용입니다. "
        "실제 주문, 실제 체결, 실제 계좌와는 무관합니다."
    )


def portfolio_upload_notice_message() -> str:
    return (
        "업로드 기능은 파일 기반 MockBroker 가상 포지션 등록 기능입니다. "
        "실제 증권사 계좌를 조회하거나 실제 주문을 실행하지 않습니다."
    )


def get_rebalancing_band_label(is_outside_band: object) -> str:
    return "리밸런싱 검토" if bool(is_outside_band) else "유지 가능 구간"


def get_stress_test_notice() -> str:
    return (
        "스트레스 테스트는 고정 충격률을 적용한 가정 시나리오 기준 추정입니다. "
        "실제 미래 손실을 예측하거나 보장하지 않습니다."
    )


def get_allocation_notice() -> str:
    return (
        "추가 투자금 배분안은 목표 비중, 데이터 신뢰도, 위험 기여도를 함께 본 "
        "의사결정 보조 정보입니다. 최종 매매 판단은 별도 검토가 필요합니다."
    )


def get_data_mode_status(
    mode: DataMode,
    is_fallback: bool = False,
) -> tuple[str, str, str]:
    if mode == "REAL_WITH_FALLBACK" and is_fallback:
        return (
            "FALLBACK MODE",
            "외부 조회 실패로 샘플 데이터를 표시 중입니다.",
            "warning",
        )
    if mode == "REAL_WITH_FALLBACK":
        return (
            "REAL DATA MODE",
            "외부 조회 데이터를 사용 중입니다. 지연/오차 가능성이 있습니다.",
            "info",
        )
    return (
        "SAMPLE MODE",
        "실제 시세가 아닌 샘플 데이터입니다.",
        "warning",
    )


def format_profit_factor(value: float) -> str:
    if value >= 999:
        return "999+ (손실 거래 없음)"
    return f"{value:.2f}"


def format_avg_profit_loss_ratio(value: float, profit_factor: float) -> str:
    if profit_factor >= 999:
        return "N/A (손실 거래 없음)"
    return f"{value:.2f}"


def get_backtest_warning_messages(
    trade_count: int,
    profit_factor: float,
    avg_profit_loss_ratio: float,
    data_source: str | None = None,
) -> list[str]:
    messages = []
    if trade_count < 10:
        messages.append(
            "거래 횟수가 적어 통계적 신뢰도가 낮습니다. "
            "이 결과만으로 전략 성과를 판단하지 마세요."
        )
    if profit_factor >= 999:
        messages.append(
            "손실 거래가 없어 Profit factor가 과도하게 높게 보일 수 있습니다. "
            "표시는 999+로 제한합니다."
        )
    if profit_factor >= 999 or avg_profit_loss_ratio == 0:
        messages.append("N/A: 손실 거래가 없어 평균 손익비 계산이 제한됩니다.")
    if data_source in {"SAMPLE", "SAMPLE_FALLBACK"}:
        messages.append(
            "SAMPLE/FALLBACK 데이터 기반 결과는 실제 시장 성과와 다를 수 있습니다."
        )
    return messages


def get_fx_status_message(
    rate: float | None, data_source: str, error: str | None
) -> str:
    if rate is None:
        return "환율 조회 실패로 US 종목의 원화 환산 평가가 제한됩니다."
    if error:
        return (
            f"USD/KRW {rate:,.2f}을 사용합니다. "
            f"{data_source} 기준이며 외부 환율 조회 오류가 있었습니다: {error}"
        )
    return f"USD/KRW {rate:,.2f}을 사용합니다. 출처: {data_source}"


def select_data_mode() -> DataMode:
    st.sidebar.markdown("### 개인용 투자 대시보드")
    st.sidebar.caption("리서치, 모의매매, 리스크 점검을 위한 개발용 MVP")
    selected = st.sidebar.radio(
        "데이터 모드",
        ["SAMPLE", "REAL_WITH_FALLBACK"],
        index=0,
        help=(
            "SAMPLE은 생성된 샘플 데이터를 사용합니다. "
            "REAL_WITH_FALLBACK은 외부 시세 조회를 시도하고 실패하면 샘플 데이터를 표시합니다."
        ),
    )
    return selected  # type: ignore[return-value]


def build_market_data_provider() -> MarketDataProvider:
    return MarketDataProvider(mode=select_data_mode())


def render_data_warning(provider: MarketDataProvider | None = None) -> None:
    provider = provider or build_market_data_provider()
    badge, message, level = get_data_mode_status(
        provider.mode, provider.is_fallback_mode()
    )
    tone = "info" if level == "info" else "warning"
    render_status_chip(badge, tone)
    if level == "info":
        render_alert(
            f"{badge}: {message} 실제 주문 기능은 포함되어 있지 않습니다.", tone
        )
    else:
        render_alert(
            f"{badge}: {message} "
            "이 앱은 실제 주문을 하지 않으며 투자 판단용으로 사용하면 안 됩니다.",
            tone,
        )
