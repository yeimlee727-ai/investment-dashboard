from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.backtest.backtest_engine import BacktestEngine, BacktestResult
from src.data_providers.base import DataMode
from src.data_providers.market_data_provider import MarketDataProvider
from src.ui_helpers import build_market_data_provider, render_data_warning


def load_input_data(
    symbol: str, market: str, uploaded_file: Any, data_mode: DataMode
) -> pd.DataFrame:
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    return MarketDataProvider(mode=data_mode).get_price_history(
        symbol, market, days=260
    )


STRATEGIES = ["EMA20 상향 돌파 + 거래량 증가", "RSI 30 이하 반등", "신고가 돌파"]


def result_summary(
    strategy: str, result: BacktestResult
) -> dict[str, float | int | str]:
    return {
        "strategy": strategy,
        "total_return": result.total_return,
        "annualized_return": result.annualized_return,
        "win_rate": result.win_rate,
        "mdd": result.mdd,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
        "avg_profit_loss_ratio": result.avg_profit_loss_ratio,
        "trade_count": result.trade_count,
        "max_consecutive_losses": result.max_consecutive_losses,
        "max_consecutive_wins": result.max_consecutive_wins,
        "total_fees": result.total_fees,
        "total_slippage": result.total_slippage,
        "average_holding_days": result.average_holding_days,
    }


def render_metric_grid(result: BacktestResult) -> None:
    rows = [
        [
            ("총수익률", f"{result.total_return:.2f}%"),
            ("연환산 수익률", f"{result.annualized_return:.2f}%"),
            ("승률", f"{result.win_rate:.2f}%"),
            ("MDD", f"{result.mdd:.2f}%"),
        ],
        [
            ("Sharpe ratio", f"{result.sharpe_ratio:.2f}"),
            ("Profit factor", f"{result.profit_factor:.2f}"),
            ("평균 손익비", f"{result.avg_profit_loss_ratio:.2f}"),
            ("거래 횟수", f"{result.trade_count}"),
        ],
        [
            ("최대 연속 손실", f"{result.max_consecutive_losses}"),
            ("최대 연속 수익", f"{result.max_consecutive_wins}"),
            ("총 수수료", f"{result.total_fees:,.0f}"),
            ("슬리피지 비용", f"{result.total_slippage:,.0f}"),
        ],
    ]
    for row in rows:
        cols = st.columns(len(row))
        for col, (label, value) in zip(cols, row, strict=True):
            col.metric(label, value)
    st.metric("평균 보유기간", f"{result.average_holding_days:.1f}일")


def render_equity_report(result: BacktestResult) -> None:
    equity = result.equity_curve.copy()
    if equity.empty:
        st.info("표시할 equity curve가 없습니다.")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=equity["date"],
            y=equity["equity_pct"],
            mode="lines",
            name="평가자산(초기자본=100)",
        )
    )
    if not result.trades.empty:
        entry_points = equity[equity["date"].isin(result.trades["entry_date"])]
        exit_points = equity[equity["date"].isin(result.trades["exit_date"])]
        fig.add_trace(
            go.Scatter(
                x=entry_points["date"],
                y=entry_points["equity_pct"],
                mode="markers",
                marker={"symbol": "triangle-up", "size": 10},
                name="진입",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=exit_points["date"],
                y=exit_points["equity_pct"],
                mode="markers",
                marker={"symbol": "triangle-down", "size": 10},
                name="청산",
            )
        )
    fig.update_layout(yaxis_title="초기자본 대비 평가자산")
    st.plotly_chart(fig, use_container_width=True)

    drawdown_fig = px.area(
        equity,
        x="date",
        y="drawdown_pct",
        title="Drawdown curve",
        labels={"drawdown_pct": "Drawdown (%)", "date": "date"},
    )
    st.plotly_chart(drawdown_fig, use_container_width=True)


def render_trade_log(result: BacktestResult) -> None:
    trade_columns = [
        "entry_date",
        "exit_date",
        "entry_price",
        "exit_price",
        "quantity",
        "gross_pnl",
        "net_pnl",
        "return_pct",
        "holding_days",
        "exit_reason",
        "fee",
        "slippage",
    ]
    trades = result.trades[[col for col in trade_columns if col in result.trades]]
    st.dataframe(trades, hide_index=True, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="백테스트", layout="wide")
    st.title("백테스트")
    provider = build_market_data_provider()
    render_data_warning(provider)
    col1, col2, col3 = st.columns(3)
    symbol = col1.text_input("종목코드", value="005930")
    market = col2.selectbox("시장", ["KR", "US"])
    strategy = col3.selectbox("전략", STRATEGIES)
    uploaded = st.file_uploader(
        "CSV 업로드(date, open, high, low, close, volume)", type=["csv"]
    )
    initial_cash = st.number_input(
        "초기자금", min_value=100_000, value=10_000_000, step=100_000
    )
    fee_rate = st.number_input(
        "수수료율",
        min_value=0.0,
        max_value=0.01,
        value=0.00015,
        step=0.00005,
        format="%.5f",
    )
    slippage_rate = st.number_input(
        "슬리피지율",
        min_value=0.0,
        max_value=0.02,
        value=0.0005,
        step=0.0001,
        format="%.5f",
    )
    position_size_pct = st.slider(
        "1회 진입 비중", min_value=0.05, max_value=1.0, value=0.2, step=0.05
    )
    stop_take_basis_label = st.radio(
        "손절/익절 판정 기준",
        ["종가 기준 백테스트", "장중 터치 기준 백테스트"],
        horizontal=True,
    )
    stop_take_basis = (
        "intraday" if stop_take_basis_label == "장중 터치 기준 백테스트" else "close"
    )
    if stop_take_basis == "intraday":
        st.caption(
            "장중 터치 기준에서 손절과 익절이 같은 봉에 동시에 발생하면 손절을 우선 처리합니다."
        )
    st.warning(
        "백테스트는 전략 검증 참고자료이며 미래 수익을 보장하지 않습니다. "
        "SAMPLE/FALLBACK 데이터, 단순 수수료/슬리피지 가정, 장중 체결 순서 차이로 실제 시장과 다를 수 있습니다."
    )

    if st.button("실행"):
        try:
            df = load_input_data(symbol, market, uploaded, provider.mode)
            if df.attrs.get("data_source") == "SAMPLE_FALLBACK":
                st.warning(
                    "FALLBACK MODE: 실제 데이터 조회 실패로 샘플 데이터 기반 백테스트를 실행합니다."
                )
            result = BacktestEngine().run(
                df,
                strategy=strategy,
                initial_cash=float(initial_cash),
                fee_rate=float(fee_rate),
                slippage_rate=float(slippage_rate),
                position_size_pct=float(position_size_pct),
                stop_take_basis=stop_take_basis,
            )
            st.info(result.mode_label)
            render_metric_grid(result)
            render_equity_report(result)
            st.subheader("진입/청산 로그")
            render_trade_log(result)

            st.subheader("전략별 결과 비교")
            comparison = []
            for strategy_name in STRATEGIES:
                comparison_result = BacktestEngine().run(
                    df,
                    strategy=strategy_name,
                    initial_cash=float(initial_cash),
                    fee_rate=float(fee_rate),
                    slippage_rate=float(slippage_rate),
                    position_size_pct=float(position_size_pct),
                    stop_take_basis=stop_take_basis,
                )
                comparison.append(result_summary(strategy_name, comparison_result))
            st.dataframe(
                pd.DataFrame(comparison),
                hide_index=True,
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"백테스트 실패: {exc}")


main()
