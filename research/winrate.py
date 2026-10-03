"""Ways to raise win rate on top of V1 (real Buy/Sell + Day-row filter).

Pre-registered selection rule (decided before looking at results):
  pick on 2025 only: a variant must raise win % on BOTH metals while keeping
  net R at >= 75% of V1's. Then 2026 is the out-of-sample check.
R = distance from entry to the outer band at entry (the strategy's real stop)."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from swastika.backtest import CONTRACTS
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

BASE = Rules(day_filter=True)
VARIANTS = {
    "W0 V1 (Day filter)": BASE,
    # better entries
    "W1 confirm: 1 bar follow-through": replace(BASE, confirm_bars=1),
    "W2 confirm: 2 bars follow-through": replace(BASE, confirm_bars=2),
    "W3 pullback 1 ATR (10 bars)": replace(BASE, pullback_atr=1.0, pullback_bars=10),
    "W4 pullback 2 ATR (15 bars)": replace(BASE, pullback_atr=2.0, pullback_bars=15),
    "W5 + 75m row agrees": replace(BASE, require=("75m",)),
    "W6 + 200 EMA agrees": replace(BASE, ema_filter=True),
    # lock in winners
    "W7 breakeven+ at 1R": replace(BASE, breakeven_r=1.0, lock_r=0.1),
    "W8 breakeven+ at 0.5R": replace(BASE, breakeven_r=0.5, lock_r=0.1),
    "W9 50% off at 0.5R, then breakeven": replace(BASE, take_profit_r=0.5, breakeven_r=0.5, lock_r=0.0),
    "W10 50% off at 1R, then breakeven": replace(BASE, take_profit_r=1.0, breakeven_r=1.0),
    "W11 full exit at 1R": replace(BASE, take_profit_r=1.0, take_profit_frac=1.0),
    "W12 exit on inner line": replace(BASE, exit_fast=True),
}

def load(sym):
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    bars = compute(resample(m, 60), Params())
    t = mtf_directions(m, bars, {"75m": 75, "Day": None}, Params())
    return m, bars, t

def run_all(variants, data):
    out = []
    for sym, con in CONTRACTS.items():
        m, bars, t = data[sym]
        for name, rules in variants.items():
            tr = simulate(m, bars, rules, con, day_dir=t["Day"].to_numpy(),
                          rows={"75m": t["75m"].to_numpy()})
            for period, tt in (("ALL", tr), ("2025", tr[tr.exit_time.dt.year == 2025]),
                               ("2026", tr[tr.exit_time.dt.year == 2026])):
                out.append({"symbol": sym, "variant": name, "period": period, **r_stats(tt)})
    return pd.DataFrame(out)

if __name__ == "__main__":
    data = {s: load(s) for s in CONTRACTS}
    r = run_all(VARIANTS, data)
    r.to_csv("research/winrate_results.csv", index=False)
    piv = r.pivot_table(index="variant", columns=["symbol", "period"],
                        values=["win_%", "net_R", "pf"], sort=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 50)
    for metric in ("win_%", "net_R", "pf"):
        print("\n==", metric); print(piv[metric].to_string())
    print(r[r.period == "ALL"][["symbol", "variant", "trades", "max_dd_R", "worst_streak", "net_inr"]].to_string(index=False))
