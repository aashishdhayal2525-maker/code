"""Which rule reproduces the real Magical / Fake labels?
Real chart: Magical SELL ~14 Jul and ~24 Sep (just after our data ends),
none in between. One 'Fake SELL' on the 19 Aug Sell, which reversed 11 bars later."""
import sys; sys.path.insert(0, ".")
from dataclasses import replace
import pandas as pd
from research.calibrate import m, b60
from swastika.indicator import Params, compute, mtf_directions
from swastika.data import resample
p = replace(Params(), st_atr_len=20, st_slow_mult=6, st_fast_mult=5)
b = compute(b60, p)
frames = {"3m": 3, "5m": 5, "15m": 15, "30m": 30, "75m": 75, "Day": None}
t = mtf_directions(m, b, frames, p)
d = pd.DataFrame({"D_ema": 0}, index=b.index)
day = compute(resample(m, None), p)
d["D_ema"] = day.set_index("close_time")["ema_dir"].reindex(b.close_time, method="ffill").to_numpy() if False else 0
w = b.join(t).loc["2026-07-01":"2026-09-23"]
sig = w[w.buy | w.sell]
cols = ["close", "buy", "sell", "cyan_dir", "ema_dir"] + list(frames)
print(sig[cols].to_string())
