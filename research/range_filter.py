"""Skip sideways markets? A trend-strength gate on top of Q1 and BS.

Gate = ADX(14) of a finished higher-timeframe bar >= threshold (daily or 4h),
known at the 5m bar's close (no look-ahead).
Pass rule (fixed before running), on 2025 at 20-tick fills: still >= 10 trades/month,
win >= 70%, PF >= 1.5, AND recovery factor (net / max DD) better than without the gate.
2026 and the Jul-Sep 2026 range are only reported."""
import sys; sys.path.insert(0, ".")
import glob
from dataclasses import replace
import numpy as np, pandas as pd
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.engine import Rules, adx, simulate, r_stats
from swastika.indicator import Params, compute, mtf_directions

BASE = {"Q1": Rules(day_filter=True, require=("60m",), breakeven_r=0.3, lock_r=0.15, reentry_breakout=120),
        "BS": Rules(day_filter=True, require=("240m",), breakeven_r=0.4, lock_r=0.2, reentry_breakout=120)}
con = CONTRACTS["SILVER"]
m = load_minutes(sorted(glob.glob("data/SILVER_nearmonth_1min_*.csv")))
bars = compute(resample(m, 5), Params())
d = mtf_directions(m, bars, {"60m": 60, "240m": 240, "Day": None}, Params())
rows = {k: d[k].to_numpy() for k in d}

def htf_adx(minutes):
    tf = resample(m, minutes)
    a = adx(*(tf[k].to_numpy(float) for k in ("high", "low", "close")))
    s = pd.Series(a, index=tf["close_time"].to_numpy()).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(bars["close_time"].to_numpy(), method="ffill").to_numpy()

adx_d, adx_4h = htf_adx(None), htf_adx(240)
for th in (15, 20, 25):
    rows[f"adxD>={th}"] = (np.nan_to_num(adx_d) >= th).astype(int)
    rows[f"adx4h>={th}"] = (np.nan_to_num(adx_4h) >= th).astype(int)

def stats(t, lo, hi, months):
    w = t[(t.exit_time >= lo) & (t.exit_time < hi)]
    s = r_stats(w)
    return {"tpm": round(s["trades"] / months, 1), "win": s["win_%"], "pf": s["pf"],
            "net_L": round(s["net_inr"] / 1e5, 1), "dd_L": round(s["max_dd_inr"] / 1e5, 1),
            "rf": round(s["net_inr"] / max(-s["max_dd_inr"], 1), 1)}

out = []
for name, base in BASE.items():
    for gate in [()] + [(g,) for g in rows if g.startswith("adx")]:
        t = simulate(m, bars, replace(base, gate=gate), con, costs=Costs(slip_ticks=20), day_dir=rows["Day"], rows=rows)
        r = {"preset": name, "gate": gate[0] if gate else "none"}
        for lab, lo, hi, mo in (("25", "2025-01-01", "2026-01-01", 12), ("26", "2026-01-01", "2027-01-01", 9),
                                ("JulSep26", "2026-07-13", "2027-01-01", 2.4)):
            r.update({f"{k}_{lab}": v for k, v in stats(t, lo, hi, mo).items()})
        out.append(r)
res = pd.DataFrame(out)
for name in BASE:
    b = res[(res.preset == name) & (res.gate == "none")].iloc[0]
    res.loc[res.preset == name, "pass_2025"] = ((res.tpm_25 >= 10) & (res.win_25 >= 70) & (res.pf_25 >= 1.5)
                                                & (res.rf_25 > b.rf_25))[res.preset == name]
res.to_csv("research/range_filter.csv", index=False)
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
print(res.to_string(index=False))
