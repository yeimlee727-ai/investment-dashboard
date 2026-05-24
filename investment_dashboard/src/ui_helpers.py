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
