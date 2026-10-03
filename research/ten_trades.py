"""Target: at least 10 trades a month.

Pass rule (fixed before running), per metal on 2025: >= 10 trades/month,
win rate >= 55%, PF >= 1.5. Then 2026 must stay profitable with PF >= 1.3.
All variants keep the Day filter + profit lock (W8 rules)."""
import sys; sys.path.insert(0, ".")
from dataclasses import replace
import pandas as pd
from research.more_trades import W8, run
from swastika.indicator import Params

P = Params()
B45 = replace(P, st_fast_mult=4.0, st_slow_mult=5.0)
B34 = replace(P, st_fast_mult=3.0, st_slow_mult=4.0)
B23 = replace(P, st_fast_mult=2.0, st_slow_mult=3.0)
VARIANTS = {
    "U1 15m": (15, P, W8),
    "U2 15m + re-entry 20": (15, P, replace(W8, reentry_breakout=20)),
    "U3 15m + re-entry 40": (15, P, replace(W8, reentry_breakout=40)),
    "U4 15m band x4/x5 + re-entry 40": (15, B45, replace(W8, reentry_breakout=40)),
    "U5 30m band x3/x4": (30, B34, W8),
    "U6 30m band x3/x4 + re-entry 20": (30, B34, replace(W8, reentry_breakout=20)),
    "U7 1h band x2/x3": (60, B23, W8),
    "U8 1h band x2/x3 + re-entry 20": (60, B23, replace(W8, reentry_breakout=20)),
    "U9 5m": (5, P, W8),
    "U10 5m + re-entry 60": (5, P, replace(W8, reentry_breakout=60)),
}
if __name__ == "__main__":
    r, keep = run(VARIANTS)
    r.to_csv("research/ten_trades_results.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    cols = ["symbol", "variant", "period", "trades", "per_month", "win_%", "pf", "net_inr", "max_dd_inr", "reentries", "reentry_win_%"]
    print(r[cols].to_string(index=False))
    a = r[r.period == "ALL"].pivot(index="variant", columns="symbol", values=["per_month", "win_%", "pf", "net_inr"])
    print(a.to_string())
