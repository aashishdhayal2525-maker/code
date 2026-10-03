"""Why does the strategy work better on Silver than Gold?"""
import sys; sys.path.insert(0, ".")
import glob
import numpy as np, pandas as pd
from swastika.backtest import CONTRACTS, Costs
from swastika.data import load_minutes, resample
from swastika.indicator import Params, compute, atr

rows = []
for sym, con in CONTRACTS.items():
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    raw0, raw1 = m.raw_close.iloc[0], m.raw_close.iloc[-1]
    for tf in (5, 60):
        b = compute(resample(m, tf), Params())
        h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
        a = atr(h, l, c, 14)
        px = b.raw_close.to_numpy()
        # Trend efficiency over 1 day of bars: |net move| / path length (1 = straight line)
        n = int(round(870 / tf))  # ~14.5 h session
        d = np.abs(np.diff(c))
        er = np.abs(c[n:] - c[:-n]) / pd.Series(d).rolling(n).sum().to_numpy()[n - 1:]
        # How long band legs last, and share of legs that reverse within 10 bars (whipsaws)
        flips = np.flatnonzero((b.buy | b.sell).to_numpy())
        legs = np.diff(flips)
        # Band distance at signal (R) vs round-trip cost (0.02% + 2 x 20 ticks)
        sig = (b.buy | b.sell).to_numpy()
        r_pts = np.abs(c - b.st_slow.to_numpy())[sig]
        cost = (0.0002 * px + 2 * 20 * con.tick)[sig]
        rows.append({"metal": sym, "chart": f"{tf}m", "price_change_%": round(100 * (raw1 / raw0 - 1)),
                     "ATR_%_of_price": round(100 * np.nanmedian(a / px), 3),
                     "trend_efficiency": round(np.nanmedian(er), 3),
                     "signals_per_month": round(len(flips) / 21, 1),
                     "median_leg_bars": int(np.median(legs)),
                     "whipsaw_%": round(100 * (legs <= 10).mean(), 1),
                     "R_%_of_price": round(100 * np.median(r_pts / px[sig]), 3),
                     "cost_as_%_of_R": round(100 * np.median(cost / r_pts), 1)})
r = pd.DataFrame(rows)
r.to_csv("research/silver_vs_gold.csv", index=False)
print(r.to_string(index=False))

# Where the money came from: trades by size, 1h W8 and 5m Q1
for f in ("results/trades_SILVER_W8.csv", "results/trades_GOLD_W8.csv"):
    t = pd.read_csv(f)
    print(f, "top 3 trades share of profit:", round(t.net_inr.nlargest(3).sum() / t.net_inr.sum(), 2),
          "| avg win R", round(t[t.net_inr > 0].r_multiple.mean(), 2), "| avg loss R", round(t[t.net_inr <= 0].r_multiple.mean(), 2))
