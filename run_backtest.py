"""Backtest the reconstructed Swastika Signal on MCX Gold and Silver.

    python run_backtest.py            # uses data/*_nearmonth_1min_*.csv
"""
import glob
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from swastika.backtest import CONTRACTS, Costs, run, stats
from swastika.data import load_minutes, resample
from swastika.indicator import Params, compute, mtf_directions

OUT = Path("results")
TABLE_FRAMES = {"3m": 3, "5m": 5, "15m": 15, "30m": 30, "75m": 75, "Day": None}
STRATEGIES = {
    "reversal": "Buy/Sell labels, always in market (flip on every label)",
    "ema_filter": "Buy/Sell labels, only with the 200 EMA (flat otherwise)",
    "magical": "Magical Buy/Sell entries, exit on the opposite Buy/Sell label",
    "mtf_filter": "Buy/Sell labels, only when every table row agrees",
}


def build(symbol, minutes=60, p=Params(), with_mtf=True):
    m = load_minutes(sorted(glob.glob(f"data/{symbol}_nearmonth_1min_*.csv")))
    bars = compute(resample(m, minutes), p)
    mtf = mtf_directions(m, bars, TABLE_FRAMES, p) if with_mtf else None
    return m, bars, mtf


def bench(bars, contract):
    """Buy-and-hold 1 lot on the back-adjusted series (rolled for free)."""
    return round((bars["close"].iloc[-1] - bars["open"].iloc[0]) * contract.multiplier)


def plot_chart(bars, symbol, start, end, path):
    b = bars.loc[start:end]
    x = np.arange(len(b))
    fig, ax = plt.subplots(figsize=(15, 7))
    fig.patch.set_facecolor("#111"); ax.set_facecolor("#111")
    up = b["close"] >= b["open"]
    ax.vlines(x, b["low"], b["high"], color=np.where(up, "#26a69a", "#ef5350"), lw=0.8)
    ax.vlines(x, b[["open", "close"]].min(axis=1), b[["open", "close"]].max(axis=1),
              color=np.where(up, "#26a69a", "#ef5350"), lw=3)
    bd = b["band_dir"].to_numpy()
    ax.fill_between(x, b["st_fast"], b["st_slow"], where=bd == 1, color="#2e7d32", alpha=0.5, step="mid")
    ax.fill_between(x, b["st_fast"], b["st_slow"], where=bd == -1, color="#c62828", alpha=0.5, step="mid")
    ax.step(x, b["st_fast"], color="#2962ff", lw=1.2, where="mid")
    ax.step(x, b["st_slow"], color="#ff1744", lw=1.2, where="mid")
    ax.plot(x, b["cyan"], color="#00bcd4", lw=1.4)
    ax.plot(x, b["ema"], color="#e040fb", lw=1.4)
    for i, r in enumerate(b.itertuples()):
        if r.buy:
            ax.annotate("Buy", (i, r.low), xytext=(0, -22), textcoords="offset points", ha="center",
                        color="white", bbox=dict(fc="#2e7d32", ec="none"))
        if r.sell:
            ax.annotate("Sell", (i, r.high), xytext=(0, 18), textcoords="offset points", ha="center",
                        color="white", bbox=dict(fc="#e53935", ec="none"))
        if r.magic_buy:
            ax.annotate("Magical BUY", (i, r.low), xytext=(0, -44), textcoords="offset points",
                        ha="center", color="white", bbox=dict(fc="#00acc1", ec="none"))
        if r.magic_sell:
            ax.annotate("Magical SELL", (i, r.high), xytext=(0, 40), textcoords="offset points",
                        ha="center", color="white", bbox=dict(fc="#00acc1", ec="none"))
    ticks = np.linspace(0, len(b) - 1, 10).astype(int)
    ax.set_xticks(ticks, [b.index[t].strftime("%d %b") for t in ticks], color="#ccc")
    ax.tick_params(colors="#ccc"); ax.yaxis.tick_right()
    ax.set_title(f"{symbol} 1h (back-adjusted) - reconstructed Swastika Signal", color="#eee")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    rows, years, curves = [], [], {}
    for symbol, contract in CONTRACTS.items():
        m, bars, mtf = build(symbol)
        bars.join(mtf.add_prefix("tbl_")).to_csv(OUT / f"{symbol}_1h_signals.csv")
        plot_chart(bars, symbol, "2026-08-20", "2026-09-30", OUT / f"{symbol}_chart_recent.png")
        for strat in STRATEGIES:
            t = run(bars, strat, contract, mtf=mtf)
            t.to_csv(OUT / f"trades_{symbol}_{strat}.csv", index=False)
            rows.append({"symbol": symbol, "strategy": strat, **stats(t, contract),
                         "buy_hold_inr": bench(bars, contract)})
            curves[(symbol, strat)] = t.set_index("exit_time")["net_inr"].cumsum()
            for y, ty in t.groupby(t["exit_time"].dt.year):
                years.append({"symbol": symbol, "strategy": strat, "year": y, **stats(ty, contract)})

    summary = pd.DataFrame(rows)
    by_year = pd.DataFrame(years)
    summary.to_csv(OUT / "summary.csv", index=False)
    by_year.to_csv(OUT / "by_year.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    for ax, symbol in zip(axes, CONTRACTS):
        for strat in STRATEGIES:
            c = curves[(symbol, strat)]
            ax.plot(c.index, c.values / 1e5, label=strat)
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_title(f"{symbol} 1h - net P&L, 1 lot (Rs lakh)"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "equity_curves.png", dpi=110); plt.close(fig)

    # Robustness: timeframe and SuperTrend settings, no MTF table needed.
    sens = []
    for symbol, contract in CONTRACTS.items():
        m = load_minutes(sorted(glob.glob(f"data/{symbol}_nearmonth_1min_*.csv")))
        for tf in (15, 30, 60, 120, 240):
            b = compute(resample(m, tf))
            for strat in ("reversal", "magical"):
                s = stats(run(b, strat, contract), contract)
                sens.append({"symbol": symbol, "tf_min": tf, "atr": 10, "mult": 3.0,
                             "strategy": strat, **s})
        b60 = resample(m, 60)
        for atr_len in (10, 14, 20):
            for mult in (2.0, 2.5, 3.0, 3.5, 4.0):
                p = replace(Params(), st_atr_len=atr_len, st_slow_mult=mult,
                            st_fast_mult=mult - 1)
                b = compute(b60, p)
                s = stats(run(b, "reversal", contract), contract)
                sens.append({"symbol": symbol, "tf_min": 60, "atr": atr_len, "mult": mult,
                             "strategy": "reversal", **s})
    pd.DataFrame(sens).to_csv(OUT / "sensitivity.csv", index=False)

    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(summary.to_string(index=False))
    print(by_year[["symbol", "strategy", "year", "trades", "win_rate_%", "net_pnl_inr",
                   "profit_factor", "max_dd_inr"]].to_string(index=False))
    print(pd.DataFrame(sens)[["symbol", "tf_min", "atr", "mult", "strategy", "trades",
                              "win_rate_%", "net_pnl_inr", "profit_factor", "max_dd_inr",
                              "costs_inr"]].to_string(index=False))


if __name__ == "__main__":
    main()
