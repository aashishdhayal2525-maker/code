"""Post-hoc follow-up (chosen after seeing fast_winrate.py): can X2 reach
10+ trades a month with trend re-entries? Reported as post-hoc."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from research.fast_winrate import VARIANTS
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

X2 = VARIANTS["X2 + 1h agrees, lock 0.15R at 0.3R"]
V = {"X2": X2, "X2 + re-entry 60": replace(X2, reentry_breakout=60),
     "X2 + re-entry 120": replace(X2, reentry_breakout=120), "X2 + re-entry 36": replace(X2, reentry_breakout=36)}
out, monthly = [], {}
for sym, con in CONTRACTS.items():
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    bars = compute(resample(m, 5), Params())
    t = mtf_directions(m, bars, {"60m": 60, "Day": None}, Params())
    for name, rules in V.items():
        for slip in (5, 20):
            tr = simulate(m, bars, rules, con, costs=Costs(slip_ticks=slip), day_dir=t["Day"].to_numpy(),
                          rows={"60m": t["60m"].to_numpy()})
            mc = tr.groupby(tr.exit_time.dt.to_period("M")).size()
            mc = mc[mc.index >= pd.Period("2025-02")]
            for period, tt, months in (("ALL", tr, 21), ("2025", tr[tr.exit_time.dt.year == 2025], 12),
                                       ("2026", tr[tr.exit_time.dt.year == 2026], 9)):
                s = r_stats(tt)
                out.append({"symbol": sym, "variant": name, "slip": slip, "period": period,
                            "per_month": round(s["trades"] / months, 1), "min_month": int(mc.min()),
                            "months_ge10": f"{(mc >= 10).sum()}/{len(mc)}", **s})
r = pd.DataFrame(out)
r.to_csv("research/fast_winrate_followup.csv", index=False)
pd.set_option("display.width", 300)
print(r[["symbol", "variant", "slip", "period", "trades", "per_month", "min_month", "months_ge10", "win_%", "pf", "net_inr", "max_dd_inr"]].to_string(index=False))
