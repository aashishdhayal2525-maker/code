"""Full-period results for the picks from select_best.py, at 5 and 20 ticks."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from research.optimize import rules_for
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

PICKS = {  # (tf, mult, filt, (trigger, lock), reentry_h, exit_htf)
    "SILVER pick": (5, 6.0, "D+4h", (0.4, 0.2), 10, False),
    "GOLD pick": (15, 4.0, "D+1h", (0.4, 0.2), 5, False),
}
out = []
for sym, con in CONTRACTS.items():
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    for name, cfg in PICKS.items():
        p = replace(Params(), st_fast_mult=cfg[1] - 1, st_slow_mult=cfg[1])
        bars = compute(resample(m, cfg[0]), p)
        d = mtf_directions(m, bars, {"60m": 60, "240m": 240, "Day": None}, Params())
        rows = {k: d[k].to_numpy() for k in d}
        for slip in (5, 20):
            tr = simulate(m, bars, rules_for(cfg), con, costs=Costs(slip_ticks=slip), day_dir=rows["Day"], rows=rows)
            tr.to_csv(f"research/best_{sym}_{name.split()[0]}_{slip}t.csv", index=False)
            mc = tr.groupby(tr.exit_time.dt.to_period("M")).agg(n=("net_inr", "size"), pnl=("net_inr", "sum"))
            mc = mc[mc.index >= pd.Period("2025-02")]
            for period, tt, mo in (("ALL", tr, 21), ("2025", tr[tr.exit_time.dt.year == 2025], 12),
                                   ("2026", tr[tr.exit_time.dt.year == 2026], 9)):
                s = r_stats(tt)
                out.append({"metal": sym, "config": name, "slip": slip, "period": period,
                            "per_month": round(s["trades"] / mo, 1), "win_%": s["win_%"], "pf": s["pf"],
                            "net_inr": s["net_inr"], "max_dd_inr": s["max_dd_inr"], "worst_streak": s["worst_streak"],
                            "months_ge10": f"{(mc.n >= 10).sum()}/{len(mc)}", "min_month": int(mc.n.min()),
                            "profit_months": f"{(mc.pnl > 0).sum()}/{len(mc)}", "worst_month": round(mc.pnl.min())})
r = pd.DataFrame(out)
r.to_csv("research/best_final.csv", index=False)
pd.set_option("display.width", 300)
print(r.to_string(index=False))
