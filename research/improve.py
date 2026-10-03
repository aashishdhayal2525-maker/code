"""Calibrated (real-matching) signals + candidate fixes for win rate / drawdown.
Variants are fixed up front; read 2025 as the design year and 2026 as the test."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from swastika.backtest import CONTRACTS, Costs, run, stats
from swastika.data import load_minutes, resample
from swastika.engine import Rules, Sizing, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

REAL = replace(Params(), st_atr_len=20, st_fast_mult=5.0, st_slow_mult=6.0)
VARIANTS = {
    "V0 real Buy/Sell, always in": Rules(),
    "V1 + Day-row filter": Rules(day_filter=True),
    "V2 + 3xATR stop": Rules(stop_atr=3),
    "V3 + band trailing stop (intrabar)": Rules(trail_band=True),
    "V4 + ADX>20": Rules(adx_min=20),
    "V5 + 50% off at 1.5R, then breakeven": Rules(stop_atr=3, take_profit_r=1.5, breakeven_r=1.5),
    "C1 Day + 3xATR + 50%@1.5R/BE + trail": Rules(day_filter=True, stop_atr=3, take_profit_r=1.5,
                                                  breakeven_r=1.5, trail_band=True),
    "C2 3xATR + 50%@1.5R/BE + trail": Rules(stop_atr=3, take_profit_r=1.5, breakeven_r=1.5, trail_band=True),
}
UNIT = {"SILVER": 1.0, "GOLD": 1.0}  # Silver Micro 1 kg = Rs1/pt; Gold 10 g (10 x Gold Petal) = Rs1/pt

out = []
for sym, con in CONTRACTS.items():
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    bars = compute(resample(m, 60), REAL)
    day = mtf_directions(m, bars, {"Day": None}, REAL)["Day"].to_numpy()
    old = stats(run(bars, "reversal", con), con)  # sanity: same signals via the bar engine
    print(sym, "bar-engine reversal:", old["trades"], old["net_pnl_inr"], old["win_rate_%"], old["max_dd_inr"])
    for name, rules in VARIANTS.items():
        for sz_name, sz in (("1 lot", Sizing()), ("risk Rs20k", Sizing("risk", 20_000, UNIT[sym]))):
            t = simulate(m, bars, rules, con, sizing=sz, day_dir=day)
            t.to_csv(f"research/out_{sym}_{name.split()[0]}_{sz_name.split()[0]}.csv", index=False)
            for period, tt in (("ALL", t), ("2025", t[t.exit_time.dt.year == 2025]),
                               ("2026", t[t.exit_time.dt.year == 2026])):
                out.append({"symbol": sym, "variant": name, "sizing": sz_name, "period": period, **r_stats(tt)})
r = pd.DataFrame(out)
r.to_csv("research/improve_results.csv", index=False)
pd.set_option("display.width", 250)
for sz in ("1 lot", "risk Rs20k"):
    print("\n=====", sz)
    print(r[r.sizing == sz].drop(columns="sizing").to_string(index=False))
