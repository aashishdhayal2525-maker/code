"""Silver Q1 vs BS head to head, and running both at once (1 lot each)."""
import sys; sys.path.insert(0, ".")
import glob
import numpy as np, pandas as pd
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

Q1 = Rules(day_filter=True, require=("60m",), breakeven_r=0.3, lock_r=0.15, reentry_breakout=120)
BS = Rules(day_filter=True, require=("240m",), breakeven_r=0.4, lock_r=0.2, reentry_breakout=120)
con = CONTRACTS["SILVER"]
m = load_minutes(sorted(glob.glob("data/SILVER_nearmonth_1min_*.csv")))
bars = compute(resample(m, 5), Params())
d = mtf_directions(m, bars, {"60m": 60, "240m": 240, "Day": None}, Params())
rows = {k: d[k].to_numpy() for k in d}
MONTHS = pd.period_range("2025-02", "2026-09", freq="M")

def monthly(t):
    return t.groupby(t.exit_time.dt.to_period("M")).net_inr.sum().reindex(MONTHS, fill_value=0)

def dd(series):
    eq = series.cumsum()
    return (eq - eq.cummax().clip(lower=0)).min()

out = []
for slip in (5, 20):
    tq = simulate(m, bars, Q1, con, costs=Costs(slip_ticks=slip), day_dir=rows["Day"], rows=rows)
    tb = simulate(m, bars, BS, con, costs=Costs(slip_ticks=slip), day_dir=rows["Day"], rows=rows)
    both = pd.concat([tq, tb]).sort_values("exit_time")
    for name, t in (("Q1", tq), ("BS", tb), ("Q1 + BS (1 lot each)", both)):
        s = r_stats(t)
        mo = monthly(t)
        out.append({"slip": slip, "setup": name, "trades": s["trades"], "per_month": round(s["trades"] / 21, 1),
                    "win_%": s["win_%"], "pf": s["pf"], "net_L": round(s["net_inr"] / 1e5, 1),
                    "max_dd_L": round(dd(t.net_inr) / 1e5, 1),
                    "net/dd": round(s["net_inr"] / -dd(t.net_inr), 1),
                    "profit_months": f"{(mo > 0).sum()}/{len(mo)}", "worst_month_L": round(mo.min() / 1e5, 2),
                    "2025_L": round(t[t.exit_time.dt.year == 2025].net_inr.sum() / 1e5, 1),
                    "2026_L": round(t[t.exit_time.dt.year == 2026].net_inr.sum() / 1e5, 1)})
    if slip == 20:
        # Overlap: share of BS entries within 1 hour of a Q1 entry in the same direction
        qe = tq[["entry_time", "side"]]
        near = [((abs(qe.entry_time - r.entry_time) <= pd.Timedelta("1h")) & (qe.side == r.side)).any()
                for r in tb.itertuples()]
        print(f"BS entries within 1h of a same-side Q1 entry: {np.mean(near):.0%}")
        print("monthly P&L correlation Q1 vs BS:", round(monthly(tq).corr(monthly(tb)), 2))
        pd.DataFrame({"Q1": monthly(tq), "BS": monthly(tb)}).div(1e5).round(2).to_csv("research/silver_q1_bs_monthly.csv")
r = pd.DataFrame(out)
r.to_csv("research/silver_q1_vs_bs.csv", index=False)
pd.set_option("display.width", 250)
print(r.to_string(index=False))
