"""Diagnosis-driven test: Gold's costs are ~2x Silver's as a share of R on 5m,
so the +0.15R locked profit is mostly eaten by fills. Does a larger lock
(same cost share as Silver) rescue Gold Q1? Checked at 20 ticks."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

Q1 = Rules(day_filter=True, require=("60m",), breakeven_r=0.3, lock_r=0.15, reentry_breakout=120)
V = {f"lock {lk}R at {tr}R": replace(Q1, breakeven_r=tr, lock_r=lk)
     for tr, lk in ((0.3, 0.15), (0.4, 0.2), (0.5, 0.25), (0.6, 0.3), (0.8, 0.4))}
out = []
for sym in ("GOLD", "SILVER"):
    con = CONTRACTS[sym]
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    for tf in (5, 15):
        bars = compute(resample(m, tf), Params())
        t = mtf_directions(m, bars, {"60m": 60, "Day": None}, Params())
        for name, rules in V.items():
            tr = simulate(m, bars, rules, con, costs=Costs(slip_ticks=20), day_dir=t["Day"].to_numpy(),
                          rows={"60m": t["60m"].to_numpy()})
            for period, tt, mo in (("ALL", tr, 21), ("2025", tr[tr.exit_time.dt.year == 2025], 12),
                                   ("2026", tr[tr.exit_time.dt.year == 2026], 9)):
                s = r_stats(tt)
                out.append({"metal": sym, "chart": f"{tf}m", "lock": name, "period": period,
                            "per_month": round(s["trades"] / mo, 1), "win_%": s["win_%"], "pf": s["pf"],
                            "net_inr": s["net_inr"], "max_dd_inr": s["max_dd_inr"]})
r = pd.DataFrame(out)
r.to_csv("research/gold_lock.csv", index=False)
pd.set_option("display.width", 250)
print(r.pivot_table(index=["metal", "chart", "lock"], columns="period", values=["per_month", "win_%", "pf"], sort=False).to_string())
print(r[r.period == "ALL"][["metal", "chart", "lock", "net_inr", "max_dd_inr"]].to_string(index=False))
