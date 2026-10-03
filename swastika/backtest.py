"""Bar-by-bar backtest of the reconstructed signals.

Rules shared by every strategy:
  * Signals are read on the close of a bar and filled at the NEXT bar's
    open, so nothing trades on information it couldn't have had.
  * One position at a time, 1 lot.
  * Costs per round trip = cost_pct of notional (brokerage, exchange fees,
    CTT, stamp duty, GST) + slippage ticks on entry and on exit.
  * A position held across a contract roll pays one extra round trip.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Contract:
    name: str
    multiplier: float  # rupees per 1 point move, per lot
    tick: float


CONTRACTS = {
    "SILVER": Contract("SILVER", 30, 1.0),   # 30 kg lot, quoted per kg
    "GOLD": Contract("GOLD", 100, 1.0),      # 1 kg lot, quoted per 10 g
}


@dataclass
class Costs:
    cost_pct: float = 0.0002   # 0.02% of notional per round trip
    slip_ticks: float = 5.0    # per side


def _entries_exits(df: pd.DataFrame, strategy: str, mtf=None):
    """Return arrays: desired position after each bar's close (+1/-1/0)."""
    n = len(df)
    want = np.zeros(n, dtype=int)
    buy, sell = df["buy"].to_numpy(), df["sell"].to_numpy()
    mb, ms = df["magic_buy"].to_numpy(), df["magic_sell"].to_numpy()
    ema_dir = df["ema_dir"].to_numpy()
    agree_up = agree_dn = None
    if mtf is not None:
        agree_up = (mtf == 1).all(axis=1).to_numpy()
        agree_dn = (mtf == -1).all(axis=1).to_numpy()
    pos = 0
    for i in range(n):
        if strategy == "reversal":
            if buy[i]:
                pos = 1
            elif sell[i]:
                pos = -1
        elif strategy == "ema_filter":
            if buy[i]:
                pos = 1 if ema_dir[i] == 1 else 0
            elif sell[i]:
                pos = -1 if ema_dir[i] == -1 else 0
        elif strategy == "magical":
            if mb[i]:
                pos = 1
            elif ms[i]:
                pos = -1
            elif (pos == 1 and sell[i]) or (pos == -1 and buy[i]):
                pos = 0
        elif strategy == "mtf_filter":
            if buy[i]:
                pos = 1 if agree_up[i] else 0
            elif sell[i]:
                pos = -1 if agree_dn[i] else 0
        else:
            raise ValueError(strategy)
        want[i] = pos
    return want


def run(df: pd.DataFrame, strategy: str, contract: Contract, costs: Costs = Costs(), mtf=None):
    want = _entries_exits(df, strategy, mtf)
    o = df["open"].to_numpy(float)
    raw = df["raw_close"].to_numpy(float)
    roll = df["roll"].to_numpy(bool)
    idx = df.index
    trades = []
    pos, entry_px, entry_i, rolls = 0, 0.0, 0, 0
    slip = costs.slip_ticks * contract.tick

    def close(i_fill, px):
        notional = raw[min(i_fill, len(raw) - 1)]
        cost = (1 + rolls) * (costs.cost_pct * notional + 2 * slip)
        gross = pos * (px - entry_px)
        trades.append({
            "side": "LONG" if pos == 1 else "SHORT",
            "entry_time": idx[entry_i], "exit_time": idx[min(i_fill, len(idx) - 1)],
            "entry": entry_px, "exit": px, "bars": i_fill - entry_i,
            "rolls": rolls, "gross_pts": gross, "cost_pts": cost, "net_pts": gross - cost,
            "net_inr": (gross - cost) * contract.multiplier,
        })

    for i in range(1, len(df)):
        if pos != 0 and roll[i]:
            rolls += 1
        target = want[i - 1]  # decided on previous close, filled at this open
        if target != pos:
            if pos != 0:
                close(i, o[i])
            pos = target
            if pos != 0:
                entry_px, entry_i, rolls = o[i], i, 0
    if pos != 0:  # mark open trade to the last close
        i = len(df) - 1
        px = df["close"].iloc[-1]
        close(i, px)
    return pd.DataFrame(trades)


def stats(trades: pd.DataFrame, contract: Contract) -> dict:
    if trades.empty:
        return {"trades": 0}
    pnl = trades["net_inr"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    return {
        "trades": len(trades),
        "win_rate_%": round(100 * len(wins) / len(trades), 1),
        "net_pnl_inr": round(pnl.sum()),
        "gross_pnl_inr": round((trades["gross_pts"] * contract.multiplier).sum()),
        "costs_inr": round((trades["cost_pts"] * contract.multiplier).sum()),
        "profit_factor": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else np.inf,
        "avg_win_inr": round(wins.mean()) if len(wins) else 0,
        "avg_loss_inr": round(losses.mean()) if len(losses) else 0,
        "max_dd_inr": round(dd),
        "avg_bars_held": round(trades["bars"].mean(), 1),
        "long_pnl_inr": round(pnl[trades["side"] == "LONG"].sum()),
        "short_pnl_inr": round(pnl[trades["side"] == "SHORT"].sum()),
    }
