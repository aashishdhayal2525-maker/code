"""Systematic multi-timeframe search for Silver and Gold.

Protocol (fixed before running):
  * Every config is simulated at 20 ticks slippage per side (pessimistic fills).
  * Selection uses 2025 ONLY. 2026 (Jan-Sep) is held out and only reported.
  * A config is eligible on 2025 if: >= 10 trades/month, win >= 70%, PF >= 1.5.
  * Rank eligible configs by recovery factor = net profit / |max drawdown|,
    averaged with its neighbours (configs differing in one setting) so a lone
    lucky spike can't win. The top config per metal is "the pick".
Higher-timeframe filters always use the real Swastika band (ATR 20, x5/x6)."""
import sys; sys.path.insert(0, ".")
import glob, itertools, os, time
from dataclasses import replace
from multiprocessing import Pool
import numpy as np, pandas as pd
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

GRID = dict(
    tf=[3, 5, 10, 15],
    mult=[4.0, 5.0, 6.0],                      # entry-chart outer band (inner = mult - 1), ATR 20
    filt=["D", "D+1h", "D+4h", "D+1h+4h", "1h", "1h+4h"],
    lock=[(0.3, 0.1), (0.3, 0.15), (0.4, 0.2), (0.5, 0.25)],
    reentry_h=[0, 5, 10],                      # re-entry breakout lookback in hours (0 = off)
    exit_htf=[False, True],                    # also exit when the 1h band flips against
)
COSTS = Costs(slip_ticks=20)
DATA = {}

def prep():
    for sym in CONTRACTS:
        m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
        for tf in GRID["tf"]:
            for mult in GRID["mult"]:
                p = replace(Params(), st_fast_mult=mult - 1, st_slow_mult=mult)
                bars = compute(resample(m, tf), p)
                d = mtf_directions(m, bars, {"60m": 60, "240m": 240, "Day": None}, Params())
                DATA[(sym, tf, mult)] = (m, bars, {k: d[k].to_numpy() for k in d})

def rules_for(cfg):
    tf, mult, filt, (trig, lk), reh, ex = cfg
    parts = filt.split("+")
    req = tuple({"1h": "60m", "4h": "240m"}[x] for x in parts if x != "D")
    return Rules(day_filter="D" in parts, require=req, breakeven_r=trig, lock_r=lk,
                 reentry_breakout=int(reh * 60 / tf) if reh else None,
                 exit_rows=("60m",) if ex else ())

def run_one(args):
    sym, cfg = args
    m, bars, rows = DATA[(sym, cfg[0], cfg[1])]
    tr = simulate(m, bars, rules_for(cfg), CONTRACTS[sym], costs=COSTS, day_dir=rows["Day"], rows=rows)
    out = {"symbol": sym, "tf": cfg[0], "mult": cfg[1], "filt": cfg[2], "lock": f"{cfg[3][1]}@{cfg[3][0]}",
           "reentry_h": cfg[4], "exit_htf": cfg[5]}
    for period, tt, mo in (("25", tr[tr.exit_time.dt.year == 2025], 12), ("26", tr[tr.exit_time.dt.year == 2026], 9),
                           ("all", tr, 21)):
        s = r_stats(tt) if len(tt) else {"trades": 0}
        out.update({f"tpm_{period}": round(s["trades"] / mo, 2), f"win_{period}": s.get("win_%", 0),
                    f"pf_{period}": s.get("pf", 0), f"net_{period}": s.get("net_inr", 0),
                    f"dd_{period}": s.get("max_dd_inr", 0)})
    return out

if __name__ == "__main__":
    t0 = time.time()
    prep()
    print("prepared", round(time.time() - t0), "s", flush=True)
    cfgs = list(itertools.product(*GRID.values()))
    jobs = [(sym, c) for sym in CONTRACTS for c in cfgs]
    print(len(jobs), "simulations", flush=True)
    res = []
    with Pool(4) as pool:
        for k, r in enumerate(pool.imap_unordered(run_one, jobs, chunksize=4), 1):
            res.append(r)
            if k % 250 == 0:
                print(k, "done", round(time.time() - t0), "s", flush=True)
    pd.DataFrame(res).to_csv("research/optimize_results.csv", index=False)
    print("finished", round(time.time() - t0), "s")
