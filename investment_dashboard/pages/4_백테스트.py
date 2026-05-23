from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from src.backtest.backtest_engine import BacktestEngine
from src.data_providers.market_data_provider import MarketDataProvider
from src.ui_helpers import render_data_warning


def load_input_data(symbol: str, market: str, uploaded_file: Any) -> pd.DataFrame:
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    return MarketDataProvider().get_price_history(symbol, market, days=260)


def main() -> None:
    st.set_page_config(page_title="백테스트", layout="wide")
    st.title("백테스트")
    render_data_warning()
    col1, col2, col3 = st.columns(3)
    symbol = col1.text_input("종목코드", value="005930")
    market = col2.selectbox("시장", ["KR", "US"])
    strategy = col3.selectbox("전략", ["EMA20 상향 돌파 + 거래량 증가", "RSI 30 이하 반등", "신고가 돌파"])
    uploaded = st.file_uploader("CSV 업로드(date, open, high, low, close, volume)", type=["csv"])
    initial_cash = st.number_input("초기자금", min_value=100_000, value=10_000_000, step=100_000)
    fee_rate = st.number_input("수수료율", min_value=0.0, max_value=0.01, value=0.00015, step=0.00005, format="%.5f")
    slippage_rate = st.number_input("슬리피지율", min_value=0.0, max_value=0.02, value=0.0005, step=0.0001, format="%.5f")

    if st.button("실행"):
        try:
            df = load_input_data(symbol, market, uploaded)
            result = BacktestEngine().run(df, strategy=strategy, initial_cash=float(initial_cash), fee_rate=float(fee_rate), slippage_rate=float(slippage_rate))
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("총수익률", f"{result.total_return:.2f}%")
            c2.metric("승률", f"{result.win_rate:.2f}%")
            c3.metric("MDD", f"{result.mdd:.2f}%")
            c4.metric("평균 손익비", f"{result.avg_profit_loss_ratio:.2f}")
            c5.metric("거래 횟수", result.trade_count)
            c6.metric("최대 연속 손실", result.max_consecutive_losses)
            c7, c8, c9 = st.columns(3)
            c7.metric("총 수수료", f"{result.total_fees:,.0f}")
            c8.metric("슬리피지 비용", f"{result.total_slippage:,.0f}")
            c9.metric("평균 보유기간", f"{result.average_holding_days:.1f}일")
            st.plotly_chart(px.line(result.equity_curve, x="date", y="equity"), use_container_width=True)
            st.dataframe(result.trades, hide_index=True, use_container_width=True)
        except Exception as exc:
            st.error(f"백테스트 실패: {exc}")


main()
