from __future__ import annotations

import streamlit as st

from src.data_providers.base import DataMode
from src.data_providers.market_data_provider import MarketDataProvider


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
    st.markdown(f"`{badge}`")
    if level == "info":
        st.info(f"{badge}: {message} 실제 주문 기능은 포함되어 있지 않습니다.")
    else:
        st.warning(
            f"{badge}: {message} "
            "이 앱은 실제 주문을 하지 않으며 투자 판단용으로 사용하면 안 됩니다."
        )
