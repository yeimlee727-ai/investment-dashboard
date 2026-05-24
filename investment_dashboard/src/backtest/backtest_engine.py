from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.indicators.technicals import add_technical_indicators

TRADE_COLUMNS = [
    "entry_date",
    "exit_date",
    "entry_price",
    "exit_price",
    "quantity",
    "gross_pnl",
    "net_pnl",
    "return_pct",
    "profit_rate",
    "pnl",
    "holding_days",
    "exit_reason",
    "fee",
    "slippage",
    "slippage_cost",
]


@dataclass
class BacktestResult:
    total_return: float
    annualized_return: float
    win_rate: float
    mdd: float
    sharpe_ratio: float
    profit_factor: float
    avg_profit_loss_ratio: float
    trade_count: int
    max_consecutive_losses: int
    max_consecutive_wins: int
    total_fees: float
    total_slippage: float
    average_holding_days: float
    mode_label: str
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
        position_size_pct: float = 0.2,
        stop_take_basis: str = "close",
    ) -> BacktestResult:
        data = add_technical_indicators(df)
        cash = initial_cash
        quantity = 0.0
        equity_points: list[dict[str, float | str]] = []
        trades: list[dict[str, float | str]] = []
        in_position = False
        entry_price = 0.0
        entry_cost = 0.0
        entry_date = ""
        entry_index = 0
        entry_fee = 0.0
        entry_slippage = 0.0
        position_size_pct = max(0.0, min(1.0, position_size_pct))
        use_intraday_touch = stop_take_basis == "intraday"

        for i in range(61, len(data)):
            row = data.iloc[i]
            is_last_bar = i == len(data) - 1
            if (
                not in_position
                and not is_last_bar
                and i > 61
                and self._entry_signal(data, i - 1, strategy)
            ):
                equity_before_entry = cash
                entry_budget = equity_before_entry * position_size_pct
                if entry_budget <= 0:
                    equity_points.append({"date": str(row["date"]), "equity": cash})
                    continue
                in_position = True
                entry_raw_price = float(row["open"])
                entry_price = entry_raw_price * (1 + slippage_rate)
                quantity = entry_budget / entry_price if entry_price else 0.0
                entry_cost = quantity * entry_price
                entry_date = str(row["date"])
                entry_index = i
                entry_fee = entry_cost * fee_rate
                entry_slippage = (entry_price - entry_raw_price) * quantity
                cash -= entry_cost + entry_fee
            elif in_position:
                stop_loss = self._stop_hit(row, entry_price, use_intraday_touch)
                take_profit = self._take_profit_hit(
                    row, entry_price, use_intraday_touch
                )
                timeout = i - entry_index >= holding_days
                is_last = i == len(data) - 1
                if stop_loss or take_profit or timeout or is_last:
                    raw_exit_price = self._exit_raw_price(
                        row,
                        entry_price,
                        use_intraday_touch,
                        stop_loss,
                        take_profit,
                        is_last,
                    )
                    exit_price = raw_exit_price * (1 - slippage_rate)
                    exit_value = quantity * exit_price
                    exit_fee = exit_value * fee_rate
                    exit_slippage = (raw_exit_price - exit_price) * quantity
                    cash += exit_value - exit_fee
                    pnl = exit_value - exit_fee - entry_cost - entry_fee
                    profit_rate = (
                        (pnl / (entry_cost + entry_fee) * 100) if entry_cost else 0.0
                    )
                    exit_reason = (
                        "손절"
                        if stop_loss
                        else (
                            "익절"
                            if take_profit
                            else "기간청산" if timeout else "마지막 종가 강제청산"
                        )
                    )
                    trades.append(
                        {
                            "entry_date": entry_date,
                            "exit_date": str(row["date"]),
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "quantity": quantity,
                            "gross_pnl": exit_value - entry_cost,
                            "net_pnl": pnl,
                            "return_pct": profit_rate,
                            "profit_rate": profit_rate,
                            "pnl": pnl,
                            "holding_days": i - entry_index,
                            "fee": entry_fee + exit_fee,
                            "slippage": entry_slippage + exit_slippage,
                            "slippage_cost": entry_slippage + exit_slippage,
                            "exit_reason": exit_reason,
                        }
                    )
                    in_position = False
                    quantity = 0.0
            mark_to_market = (
                cash if not in_position else cash + quantity * float(row["close"])
            )
            equity_points.append(
                {
                    "date": str(row["date"]),
                    "equity": mark_to_market,
                    "equity_pct": (
                        mark_to_market / initial_cash * 100 if initial_cash else 0.0
                    ),
                }
            )

        trades_df = pd.DataFrame(trades, columns=TRADE_COLUMNS)
        equity_df = pd.DataFrame(equity_points)
        mode_label = (
            "장중 터치 기준 백테스트" if use_intraday_touch else "종가 기준 백테스트"
        )
        return self._summarize(initial_cash, trades_df, equity_df, mode_label)

    def _entry_signal(self, data: pd.DataFrame, i: int, strategy: str) -> bool:
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        if strategy == "EMA20 상향 돌파 + 거래량 증가":
            volume_ok = (
                row["volume"] > row["volume_ma20"] * 1.5
                if row["volume_ma20"]
                else False
            )
            return bool(
                prev["close"] <= prev["ema20"]
                and row["close"] > row["ema20"]
                and volume_ok
            )
        if strategy == "RSI 30 이하 반등":
            return bool(
                prev["rsi14"] <= 30
                and row["rsi14"] > prev["rsi14"]
                and row["close"] > prev["close"]
            )
        if strategy == "신고가 돌파":
            prior_high = data.iloc[:i]["high"].rolling(60).max().iloc[-1]
            return bool(row["close"] > prior_high)
        return False

    def _stop_hit(
        self, row: pd.Series, entry_price: float, use_intraday_touch: bool
    ) -> bool:
        stop_price = entry_price * 0.93
        return (
            bool(row["low"] <= stop_price)
            if use_intraday_touch
            else bool(row["close"] <= stop_price)
        )

    def _take_profit_hit(
        self, row: pd.Series, entry_price: float, use_intraday_touch: bool
    ) -> bool:
        take_price = entry_price * 1.15
        return (
            bool(row["high"] >= take_price)
            if use_intraday_touch
            else bool(row["close"] >= take_price)
        )

    def _exit_raw_price(
        self,
        row: pd.Series,
        entry_price: float,
        use_intraday_touch: bool,
        stop_loss: bool = False,
        take_profit: bool = False,
        force_close: bool = False,
    ) -> float:
        if force_close or not use_intraday_touch:
            return float(row["close"])
        if stop_loss:
            return entry_price * 0.93
        if take_profit:
            return entry_price * 1.15
        return float(row["close"])

    def _summarize(
        self,
        initial_cash: float,
        trades: pd.DataFrame,
        equity: pd.DataFrame,
        mode_label: str,
    ) -> BacktestResult:
        if equity.empty:
            equity = pd.DataFrame(
                [{"date": "", "equity": initial_cash, "equity_pct": 100.0}]
            )
        equity = self._attach_drawdown(equity, initial_cash)
        total_return = (float(equity.iloc[-1]["equity"]) / initial_cash - 1) * 100
        annualized_return = self._annualized_return(equity, initial_cash)
        sharpe_ratio = self._sharpe_ratio(equity)
        mdd = float(equity["drawdown_pct"].min()) if "drawdown_pct" in equity else 0.0
        if trades.empty:
            return BacktestResult(
                round(total_return, 2),
                round(annualized_return, 2),
                0.0,
                round(mdd, 2),
                round(sharpe_ratio, 2),
                0.0,
                0.0,
                0,
                0,
                0,
                0.0,
                0.0,
                0.0,
                mode_label,
                trades,
                equity,
            )
        wins = trades[trades["net_pnl"] > 0]
        losses = trades[trades["net_pnl"] <= 0]
        win_rate = len(wins) / len(trades) * 100
        gains = wins["return_pct"].mean() if not wins.empty else 0
        loss_abs = abs(losses["return_pct"].mean()) if not losses.empty else np.nan
        avg_pl = float(gains / loss_abs) if loss_abs and not np.isnan(loss_abs) else 0.0
        profit_factor = self._profit_factor(trades)
        max_losses = self._max_consecutive(trades["net_pnl"].tolist(), wins=False)
        max_wins = self._max_consecutive(trades["net_pnl"].tolist(), wins=True)
        total_fees = float(trades["fee"].sum()) if "fee" in trades else 0.0
        total_slippage = (
            float(trades["slippage"].sum()) if "slippage" in trades else 0.0
        )
        average_holding_days = (
            float(trades["holding_days"].mean()) if "holding_days" in trades else 0.0
        )
        return BacktestResult(
            round(total_return, 2),
            round(annualized_return, 2),
            round(win_rate, 2),
            round(mdd, 2),
            round(sharpe_ratio, 2),
            round(profit_factor, 2),
            round(avg_pl, 2),
            len(trades),
            max_losses,
            max_wins,
            round(total_fees, 2),
            round(total_slippage, 2),
            round(average_holding_days, 1),
            mode_label,
            trades,
            equity,
        )

    def _attach_drawdown(
        self, equity: pd.DataFrame, initial_cash: float
    ) -> pd.DataFrame:
        curve = equity.copy()
        curve["equity"] = pd.to_numeric(curve["equity"], errors="coerce").fillna(
            initial_cash
        )
        curve["equity_pct"] = (
            curve["equity"] / initial_cash * 100 if initial_cash else 0.0
        )
        peak = curve["equity"].cummax().replace(0, np.nan)
        curve["drawdown_pct"] = ((curve["equity"] / peak) - 1).fillna(0.0) * 100
        return curve

    def _annualized_return(self, equity: pd.DataFrame, initial_cash: float) -> float:
        if equity.empty or initial_cash <= 0:
            return 0.0
        final_equity = float(equity.iloc[-1]["equity"])
        if final_equity <= 0:
            return -100.0
        dates = pd.to_datetime(equity["date"], errors="coerce").dropna()
        if len(dates) >= 2:
            days = max((dates.iloc[-1] - dates.iloc[0]).days, 1)
        else:
            days = max(len(equity), 1)
        years = max(days / 365.25, 1 / 252)
        annualized = (final_equity / initial_cash) ** (1 / years) - 1
        return float(annualized * 100) if np.isfinite(annualized) else 0.0

    def _sharpe_ratio(self, equity: pd.DataFrame) -> float:
        if equity.empty or len(equity) < 2:
            return 0.0
        returns = equity["equity"].pct_change().replace([np.inf, -np.inf], np.nan)
        returns = returns.dropna()
        if returns.empty:
            return 0.0
        std = float(returns.std(ddof=0))
        if std == 0 or not np.isfinite(std):
            return 0.0
        sharpe = float(returns.mean()) / std * np.sqrt(252)
        return float(sharpe) if np.isfinite(sharpe) else 0.0

    def _profit_factor(self, trades: pd.DataFrame) -> float:
        if trades.empty or "gross_pnl" not in trades:
            return 0.0
        gross_profit = float(trades.loc[trades["gross_pnl"] > 0, "gross_pnl"].sum())
        gross_loss = abs(float(trades.loc[trades["gross_pnl"] < 0, "gross_pnl"].sum()))
        if gross_loss == 0:
            return 999.0 if gross_profit > 0 else 0.0
        value = gross_profit / gross_loss
        return float(value) if np.isfinite(value) else 0.0

    def _max_consecutive(self, pnls: list[float], wins: bool) -> int:
        best = current = 0
        for pnl in pnls:
            if (wins and pnl > 0) or (not wins and pnl <= 0):
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best
