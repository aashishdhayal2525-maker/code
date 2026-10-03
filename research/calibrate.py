"""Find band settings whose Buy/Sell labels line up with the real ones."""
import glob, itertools, sys
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from dataclasses import replace
from swastika.data import load_minutes, resample
from swastika.indicator import Params, compute
from research.real_signals import REAL, WINDOW

m = load_minutes(sorted(glob.glob("data/SILVER_nearmonth_1min_*.csv")))
b60 = resample(m, 60)

def score(bars, tol=8):
    w = bars.loc[WINDOW[0]:WINDOW[1]]
    mine = pd.concat([w.index[w.buy].to_series().map(lambda _: "buy"),
                      w.index[w.sell].to_series().map(lambda _: "sell")]).sort_index()
    pos = {t: i for i, t in enumerate(w.index)}
    hits, errs = 0, []
    for t, side in REAL.itertuples(index=False):
        i = w.index.searchsorted(t)
        cands = [pos[x] - i for x, s in mine.items() if s == side and abs(pos[x] - i) <= tol]
        if cands:
            hits += 1; errs.append(min(cands, key=abs))
    return hits, len(mine), errs

def main():
  rows = []
  for L, k, gap in itertools.product((10, 14, 20, 30, 50), (2, 2.5, 3, 3.5, 4, 5, 6), (1.0,)):
      p = replace(Params(), st_atr_len=L, st_slow_mult=k, st_fast_mult=max(k - gap, 0.5))
      h, n, e = score(compute(b60, p))
      rows.append((L, k, h, n, round(np.mean(np.abs(e)), 1) if e else None))
  r = pd.DataFrame(rows, columns=["atr", "mult", "matched_of_9", "my_signals", "avg_bar_err"])
  print(r.sort_values(["matched_of_9", "my_signals"], ascending=[False, True]).head(15).to_string(index=False))
  print(r[(r.atr == 10) & (r.mult == 3)].to_string(index=False))


if __name__ == "__main__":
    main()
