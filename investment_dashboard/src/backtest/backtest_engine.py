from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.indicators.technicals import add_technical_indicators


@dataclass
class BacktestResult:
    total_return: float
    win_rate: float
    mdd: float
    avg_profit_loss_ratio: float
    trade_count: int
    max_consecutive_losses: int
    total_fees: float
    total_slippage: float
    average_holding_days: float
    trades: pd.DataFrame
    equity_curve: pd.DataFrame


class BacktestEngine:
    def run(
        self,
        df: pd.DataFrame,
        strategy: str,
        initial_cash: float = 10_000_000,
        holding_days: int = 10,
        fee_rate: float = 0.00015,
        slippage_rate: float = 0.0005,
    ) -> BacktestResult:
        data = add_technical_indicators(df)
        cash = initial_cash
        equity_points: list[dict[str, float | str]] = []
        trades: list[dict[str, float | str]] = []
        in_position = False
        entry_price = 0.0
        entry_raw_price = 0.0
        entry_date = ""
        entry_index = 0
        entry_fee = 0.0
        entry_slippage = 0.0

        for i in range(61, len(data)):
            row = data.iloc[i]
            if not in_position and i > 61 and self._entry_signal(data, i - 1, strategy):
                in_position = True
                entry_raw_price = float(row["open"])
                entry_price = entry_raw_price * (1 + slippage_rate)
                entry_date = str(row["date"])
                entry_index = i
                entry_value = cash
                entry_fee = entry_value * fee_rate
                entry_slippage = (entry_price - entry_raw_price) / entry_price * entry_value if entry_price else 0.0
                if i == len(data) - 1:
                    raw_exit_price = float(row["close"])
                    exit_price = raw_exit_price * (1 - slippage_rate)
                    gross_return = exit_price / entry_price - 1
                    gross_exit_value = cash * (1 + gross_return)
                    exit_fee = gross_exit_value * fee_rate
                    exit_slippage = (raw_exit_price - exit_price) / raw_exit_price * gross_exit_value if raw_exit_price else 0.0
                    final_value = gross_exit_value - entry_fee - exit_fee
                    profit_rate = (final_value / cash - 1) * 100
                    cash = final_value
                    trades.append(
                        {
                            "entry_date": entry_date,
                            "exit_date": str(row["date"]),
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "profit_rate": profit_rate,
                            "holding_days": 0,
                            "fee": entry_fee + exit_fee,
                            "slippage_cost": entry_slippage + exit_slippage,
                            "exit_reason": "마지막 종가 강제청산",
                        }
                    )
                    in_position = False
            elif in_position:
                stop_loss = row["close"] <= entry_price * 0.93
                take_profit = row["close"] >= entry_price * 1.15
                timeout = i - entry_index >= holding_days
                is_last = i == len(data) - 1
                if stop_loss or take_profit or timeout or is_last:
                    raw_exit_price = float(row["close"])
                    exit_price = raw_exit_price * (1 - slippage_rate)
                    gross_return = exit_price / entry_price - 1
                    gross_exit_value = cash * (1 + gross_return)
                    exit_fee = gross_exit_value * fee_rate
                    exit_slippage = (raw_exit_price - exit_price) / raw_exit_price * gross_exit_value if raw_exit_price else 0.0
                    final_value = gross_exit_value - entry_fee - exit_fee
                    profit_rate = (final_value / cash - 1) * 100
                    cash = final_value
                    exit_reason = "손절" if stop_loss else "익절" if take_profit else "기간청산" if timeout else "마지막 종가 강제청산"
                    trades.append(
                        {
                            "entry_date": entry_date,
                            "exit_date": str(row["date"]),
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "profit_rate": profit_rate,
                            "holding_days": i - entry_index,
                            "fee": entry_fee + exit_fee,
                            "slippage_cost": entry_slippage + exit_slippage,
                            "exit_reason": exit_reason,
                        }
                    )
                    in_position = False
            mark_to_market = cash if not in_position else cash * (float(row["close"]) / entry_price)
            equity_points.append({"date": str(row["date"]), "equity": mark_to_market})

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_points)
        return self._summarize(initial_cash, trades_df, equity_df)

    def _entry_signal(self, data: pd.DataFrame, i: int, strategy: str) -> bool:
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        if strategy == "EMA20 상향 돌파 + 거래량 증가":
            volume_ok = row["volume"] > row["volume_ma20"] * 1.5 if row["volume_ma20"] else False
            return bool(prev["close"] <= prev["ema20"] and row["close"] > row["ema20"] and volume_ok)
        if strategy == "RSI 30 이하 반등":
            return bool(prev["rsi14"] <= 30 and row["rsi14"] > prev["rsi14"] and row["close"] > prev["close"])
        if strategy == "신고가 돌파":
            prior_high = data.iloc[:i]["high"].rolling(60).max().iloc[-1]
            return bool(row["close"] > prior_high)
        return False

    def _summarize(self, initial_cash: float, trades: pd.DataFrame, equity: pd.DataFrame) -> BacktestResult:
        if equity.empty:
            equity = pd.DataFrame([{"date": "", "equity": initial_cash}])
        total_return = (float(equity.iloc[-1]["equity"]) / initial_cash - 1) * 100
        if trades.empty:
            return BacktestResult(round(total_return, 2), 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, 0.0, trades, equity)
        wins = trades[trades["profit_rate"] > 0]
        losses = trades[trades["profit_rate"] <= 0]
        win_rate = len(wins) / len(trades) * 100
        gains = wins["profit_rate"].mean() if not wins.empty else 0
        loss_abs = abs(losses["profit_rate"].mean()) if not losses.empty else np.nan
        avg_pl = float(gains / loss_abs) if loss_abs and not np.isnan(loss_abs) else 0.0
        peak = equity["equity"].cummax()
        mdd = float(((equity["equity"] / peak) - 1).min() * 100)
        max_losses = self._max_consecutive_losses(trades["profit_rate"].tolist())
        total_fees = float(trades["fee"].sum()) if "fee" in trades else 0.0
        total_slippage = float(trades["slippage_cost"].sum()) if "slippage_cost" in trades else 0.0
        average_holding_days = float(trades["holding_days"].mean()) if "holding_days" in trades else 0.0
        return BacktestResult(
            round(total_return, 2),
            round(win_rate, 2),
            round(mdd, 2),
            round(avg_pl, 2),
            len(trades),
            max_losses,
            round(total_fees, 2),
            round(total_slippage, 2),
            round(average_holding_days, 1),
            trades,
            equity,
        )

    def _max_consecutive_losses(self, profit_rates: list[float]) -> int:
        best = current = 0
        for rate in profit_rates:
            if rate <= 0:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best
