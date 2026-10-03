"""Fit the cyan trail so Magical matches the real chart: one Magical SELL
around 13-15 Jul, none from 20 Jul to 23 Sep (a Magical SELL ~24 Sep is
after our data ends)."""
import sys; sys.path.insert(0, ".")
import itertools
from dataclasses import replace
import pandas as pd
from research.calibrate import b60
from swastika.indicator import Params, compute
rows = []
for L, k in itertools.product((14, 20, 30, 50), (5, 6, 7, 8, 9, 10, 12)):
    p = replace(Params(), st_atr_len=20, st_slow_mult=6, st_fast_mult=5, cyan_atr_len=L, cyan_mult=k)
    b = compute(b60, p)
    ms, mb = b.index[b.magic_sell], b.index[b.magic_buy]
    jul = [t for t in ms if pd.Timestamp("2026-07-09") <= t <= pd.Timestamp("2026-07-17")]
    inwin = [t for t in ms.union(mb) if pd.Timestamp("2026-07-20") <= t <= pd.Timestamp("2026-09-24")]
    rows.append((L, k, len(jul), str(jul[0])[:16] if jul else "", len(inwin),
                 b.magic_buy.sum() + b.magic_sell.sum()))
r = pd.DataFrame(rows, columns=["cyan_atr", "cyan_mult", "jul_magic", "when", "magic_in_window", "total_magic_21mo"])
print(r.to_string(index=False))
