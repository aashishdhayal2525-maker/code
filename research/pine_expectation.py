"""What TradingView's Strategy Tester should roughly show for pine/silver_5m_q1_bs.pine.
Minute-level (= Bar Magnifier on) vs 5m-bar-level (= Bar Magnifier off, where the lock
stop can only trigger from the next bar)."""
import sys; sys.path.insert(0, ".")
import glob
import pandas as pd
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

P = {"Q1": Rules(day_filter=True, require=("60m",), breakeven_r=0.3, lock_r=0.15, reentry_breakout=120),
     "BS": Rules(day_filter=True, require=("240m",), breakeven_r=0.4, lock_r=0.2, reentry_breakout=120)}
con = CONTRACTS["SILVER"]
m = load_minutes(sorted(glob.glob("data/SILVER_nearmonth_1min_*.csv")))
bars = compute(resample(m, 5), Params())
d = mtf_directions(m, bars, {"60m": 60, "240m": 240, "Day": None}, Params())
rows = {k: d[k].to_numpy() for k in d}
out = []
for name, rules in P.items():
    for mode, px in (("minute fills (Bar Magnifier on)", m), ("5m bar fills (Bar Magnifier off)", bars)):
        t = simulate(px, bars, rules, con, costs=Costs(slip_ticks=5), day_dir=rows["Day"], rows=rows)
        s = r_stats(t)
        out.append({"preset": name, "mode": mode, "trades": s["trades"], "per_month": round(s["trades"] / 21, 1),
                    "win_%": s["win_%"], "pf": s["pf"], "net_L": round(s["net_inr"] / 1e5, 1),
                    "max_dd_L": round(s["max_dd_inr"] / 1e5, 1)})
r = pd.DataFrame(out)
r.to_csv("research/pine_expectation.csv", index=False)
print(r.to_string(index=False))
