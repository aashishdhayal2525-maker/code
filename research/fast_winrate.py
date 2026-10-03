"""High win rate AND >= 10 trades a month, on the 5m and 15m charts.

Pass rule (fixed before running), per metal and chart, on 2025:
  >= 10 trades/month (5m) or >= 5 (15m, so both metals together give 10),
  win >= 70% at 5 ticks slippage AND >= 65% at 20 ticks, PF >= 1.5.
Then 2026 must keep win >= 65% and PF >= 1.3 at 20 ticks."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import pandas as pd
from research.more_trades import W8
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

H1 = ("60m",)
VARIANTS = {
    "X0 W8 (current fast setup)": W8,
    "X1 + 1h band agrees": replace(W8, require=H1),
    "X2 + 1h agrees, lock 0.15R at 0.3R": replace(W8, require=H1, breakeven_r=0.3, lock_r=0.15),
    "X3 lock 0.1R at 0.3R": replace(W8, breakeven_r=0.3, lock_r=0.1),
    "X4 lock 0.25R at 0.5R": replace(W8, lock_r=0.25),
    "X5 + 1-bar confirm": replace(W8, confirm_bars=1),
    "X6 + 1h agrees + 1-bar confirm": replace(W8, require=H1, confirm_bars=1),
    "X7 50% off at 0.5R, lock 0.1R": replace(W8, take_profit_r=0.5),
    "X8 + 1h agrees + 50% off at 0.5R": replace(W8, require=H1, take_profit_r=0.5),
    "X9 + 1h and 30m agree": replace(W8, require=("60m", "30m")),
}

def main():
    out = []
    for sym, con in CONTRACTS.items():
        m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
        for tf in (5, 15):
            bars = compute(resample(m, tf), Params())
            t = mtf_directions(m, bars, {"60m": 60, "30m": 30, "Day": None}, Params())
            rows = {k: t[k].to_numpy() for k in ("60m", "30m")}
            for name, rules in VARIANTS.items():
                if tf == 15 and "30m" in rules.require:
                    pass
                for slip in (5, 20):
                    tr = simulate(m, bars, rules, con, costs=Costs(slip_ticks=slip),
                                  day_dir=t["Day"].to_numpy(), rows=rows)
                    for period, tt, months in (("ALL", tr, 21), ("2025", tr[tr.exit_time.dt.year == 2025], 12),
                                               ("2026", tr[tr.exit_time.dt.year == 2026], 9)):
                        s = r_stats(tt)
                        out.append({"symbol": sym, "tf": tf, "variant": name, "slip": slip, "period": period,
                                    "per_month": round(s["trades"] / months, 1), **s})
    r = pd.DataFrame(out)
    r.to_csv("research/fast_winrate_results.csv", index=False)
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    piv = r.pivot_table(index=["tf", "variant"], columns=["symbol", "slip", "period"],
                        values="win_%", sort=False)
    print("== WIN %\n", piv.to_string())
    piv = r[r.slip == 20].pivot_table(index=["tf", "variant"], columns=["symbol", "period"],
                                      values=["per_month", "pf"], sort=False)
    print("== trades/month and PF at 20 ticks\n", piv.to_string())
    a = r[(r.slip == 20) & (r.period == "ALL")][["symbol", "tf", "variant", "trades", "win_%", "pf", "net_inr", "max_dd_inr"]]
    print(a.to_string(index=False))

if __name__ == "__main__":
    main()
