from __future__ import annotations

import streamlit as st

from src.data_providers.market_data_provider import MarketDataProvider


def render_data_warning(provider: MarketDataProvider | None = None) -> None:
    provider = provider or MarketDataProvider()
    if provider.is_sample_mode:
        st.markdown("`SAMPLE MODE`")
        st.warning(
            "SAMPLE MODE: 현재 가격/거래량 데이터는 실제 시세가 아닐 수 있습니다. "
            "이 앱은 실제 주문을 하지 않으며 투자 판단용으로 사용하면 안 됩니다."
        )
    else:
        st.info(
            "연결된 데이터 공급자를 사용 중입니다. 실제 주문 기능은 포함되어 있지 않습니다."
        )
