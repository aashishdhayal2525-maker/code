"""More trades without giving up the win rate.

Base = W8 (Day filter + lock +0.1R once up 0.5R). Ideas fixed up front:
  T1-T3  same rules on 15m / 30m charts (band ATR 20 x5/x6 unchanged)
  T4-T5  1h, re-enter the trend on a 10- or 20-bar breakout after an exit
  T6     1h, faster band x3/x4
  T7     30m + 20-bar re-entry
Pass rule (decided before running): on 2025, at least 1.5x W8's trades on
both metals, win rate >= 65%, PF >= 2; then 2026 is the check."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from swastika.backtest import CONTRACTS
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

W8 = Rules(day_filter=True, breakeven_r=0.5, lock_r=0.1)
FAST = replace(Params(), st_fast_mult=3.0, st_slow_mult=4.0)
VARIANTS = {  # name: (timeframe minutes, params, rules)
    "W8 1h (current)": (60, Params(), W8),
    "T1 W8 on 15m": (15, Params(), W8),
    "T2 W8 on 30m": (30, Params(), W8),
    "T3 W8 on 2h": (120, Params(), W8),
    "T4 1h + re-entry 10-bar breakout": (60, Params(), replace(W8, reentry_breakout=10)),
    "T5 1h + re-entry 20-bar breakout": (60, Params(), replace(W8, reentry_breakout=20)),
    "T6 1h faster band x3/x4": (60, FAST, W8),
    "T7 30m + re-entry 20-bar breakout": (30, Params(), replace(W8, reentry_breakout=20)),
}

def run(variants=VARIANTS, save=False):
    out, keep = [], {}
    for sym, con in CONTRACTS.items():
        m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
        cache = {}
        for name, (tf, p, rules) in variants.items():
            key = (tf, repr(p))
            if key not in cache:
                bars = compute(resample(m, tf), p)
                day = mtf_directions(m, bars, {"Day": None}, p)["Day"].to_numpy()
                cache[key] = (bars, day)
            bars, day = cache[key]
            tr = simulate(m, bars, rules, con, day_dir=day)
            keep[(sym, name)] = tr
            for period, tt in (("ALL", tr), ("2025", tr[tr.exit_time.dt.year == 2025]),
                               ("2026", tr[tr.exit_time.dt.year == 2026])):
                s = r_stats(tt)
                re = tt[tt.get("kind", pd.Series(dtype=str)) == "re-entry"] if len(tt) else tt
                out.append({"symbol": sym, "variant": name, "period": period, **s,
                            "per_month": round(s.get("trades", 0) / (21 if period == "ALL" else 12 if period == "2025" else 9), 1),
                            "reentries": len(re),
                            "reentry_win_%": round(100 * (re.net_inr > 0).mean(), 1) if len(re) else None})
    return pd.DataFrame(out), keep

if __name__ == "__main__":
    r, _ = run()
    r.to_csv("research/more_trades_results.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    cols = ["symbol", "variant", "period", "trades", "per_month", "win_%", "pf", "net_inr", "max_dd_inr",
            "net_R", "reentries", "reentry_win_%"]
    print(r[cols].to_string(index=False))
