"""Cost stress test for the high-frequency candidates: does the edge survive
worse fills? Slippage per side in ticks (1 tick = Rs1 on both metals' quote)."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from research.more_trades import W8
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

CANDS = {"U9 5m": (5, W8), "U10 5m + re-entry 60": (5, replace(W8, reentry_breakout=60)), "U1 15m": (15, W8)}
rows = []
for sym, con in CONTRACTS.items():
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    for name, (tf, rules) in CANDS.items():
        bars = compute(resample(m, tf), Params())
        day = mtf_directions(m, bars, {"Day": None}, Params())["Day"].to_numpy()
        for slip in (5, 10, 20, 40):
            tr = simulate(m, bars, rules, con, costs=Costs(slip_ticks=slip), day_dir=day)
            for period, tt in (("ALL", tr), ("2025", tr[tr.exit_time.dt.year == 2025]), ("2026", tr[tr.exit_time.dt.year == 2026])):
                s = r_stats(tt)
                rows.append({"symbol": sym, "variant": name, "slip_ticks": slip, "period": period,
                             "trades": s["trades"], "win_%": s["win_%"], "pf": s["pf"],
                             "net_inr": s["net_inr"], "max_dd_inr": s["max_dd_inr"]})
r = pd.DataFrame(rows)
r.to_csv("research/ten_trades_costs.csv", index=False)
pd.set_option("display.width", 250)
print(r[r.period == "ALL"].to_string(index=False))
print(r[(r.period != "ALL") & (r.slip_ticks.isin([5, 20]))].pivot_table(index=["symbol", "variant", "slip_ticks"], columns="period", values=["win_%", "pf"]).to_string())
