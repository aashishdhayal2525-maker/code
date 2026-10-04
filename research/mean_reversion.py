"""Option 2: an intraday mean-reversion strategy to complement the trend strategy.

Idea: fade stretches away from a mean and exit when price returns to it.
  signals  BB    close beyond SMA20 -/+ k * stdev20             (mean = SMA20)
           VWAP  close beyond session VWAP -/+ k * ATR14          (mean = VWAP)
           RSI2  RSI(2) < th (long) / > 100 - th (short)          (mean = SMA5)
  regime   none | "htf_split" (1h and 4h bands disagree) | 1h ADX < 20 | 1h ADX < 25
  exits    close back at the mean (fill next open), stop k * ATR (intrabar),
           time stop, and always flat at the session's last bar (no overnight risk)
Fills: signal on bar close, entry at next bar open; stops at stop price or the open
if gapped; 20 ticks slippage per side + 0.02% per round trip.

Selection protocol (fixed before running), on 2025 only:
  eligible = >= 5 trades/month, PF >= 1.3, net > 0
  rank = recovery factor (net / |max DD|) averaged with one-step grid neighbours.
2026, the Jul-Sep 2026 range and the combination with BS are only reported."""
import sys; sys.path.insert(0, ".")
import glob, itertools
import numpy as np, pandas as pd
from swastika.backtest import CONTRACTS
from swastika.data import load_minutes, resample
from swastika.engine import adx
from swastika.indicator import Params, atr, mtf_directions

SLIP, COST_PCT = 20, 0.0002
GRID = dict(
    tf=[5, 15],
    signal=["BB2.0", "BB2.5", "BB3.0", "VWAP1.5", "VWAP2", "VWAP3", "RSI5", "RSI10"],
    regime=["none", "htf_split", "adx1h<20", "adx1h<25"],
    stop_atr=[1.5, 2.5],
    max_bars=[12, 0],          # 0 = no time stop (still flat by session end)
)


def session_vwap(m):
    tp = (m.high + m.low + m.close) / 3
    day = m.index.normalize()
    pv = (tp * m.volume.clip(lower=1)).groupby(day).cumsum()
    v = m.volume.clip(lower=1).groupby(day).cumsum()
    return pv / v


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50).to_numpy()


def prep(sym):
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    vw = session_vwap(m)
    h1 = resample(m, 60)
    a1 = adx(*(h1[k].to_numpy(float) for k in ("high", "low", "close")))
    adx_s = pd.Series(a1, index=h1["close_time"].to_numpy()).sort_index()
    adx_s = adx_s[~adx_s.index.duplicated(keep="last")]
    out = {}
    for tf in GRID["tf"]:
        b = resample(m, tf)
        c = b.close.to_numpy(float)
        f = {"bars": b}
        f["atr"] = atr(b.high.to_numpy(float), b.low.to_numpy(float), c, 14)
        f["sma20"] = pd.Series(c).rolling(20).mean().to_numpy()
        f["sd20"] = pd.Series(c).rolling(20).std().to_numpy()
        f["sma5"] = pd.Series(c).rolling(5).mean().to_numpy()
        f["rsi2"] = rsi(c, 2)
        # VWAP as of the bar's last minute
        f["vwap"] = vw.reindex(b["close_time"] - pd.Timedelta(minutes=1), method="ffill").to_numpy()
        d = mtf_directions(m, b, {"60m": 60, "240m": 240}, Params())
        f["htf_split"] = (d["60m"].to_numpy() != d["240m"].to_numpy())
        f["adx1h"] = adx_s.reindex(b["close_time"].to_numpy(), method="ffill").to_numpy()
        day = b.index.normalize()
        f["eod"] = np.r_[day[1:] != day[:-1], True]
        out[tf] = f
    return out


def signals(f, sig):
    c = f["bars"].close.to_numpy(float)
    if sig.startswith("BB"):
        k = float(sig[2:])
        return c < f["sma20"] - k * f["sd20"], c > f["sma20"] + k * f["sd20"], f["sma20"]
    if sig.startswith("VWAP"):
        k = float(sig[4:])
        return c < f["vwap"] - k * f["atr"], c > f["vwap"] + k * f["atr"], f["vwap"]
    th = float(sig[3:])
    return f["rsi2"] < th, f["rsi2"] > 100 - th, f["sma5"]


def regime_ok(f, reg):
    n = len(f["bars"])
    if reg == "none":
        return np.ones(n, bool)
    if reg == "htf_split":
        return f["htf_split"]
    th = float(reg.split("<")[1])
    return np.nan_to_num(f["adx1h"], nan=99) < th


def backtest(f, sig, reg, stop_k, max_bars, con):
    b = f["bars"]
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    raw = b.raw_close.to_numpy(float)
    lo_sig, hi_sig, mean = signals(f, sig)
    ok = regime_ok(f, reg)
    a, eod, idx = f["atr"], f["eod"], b.index
    trades = []
    pos, entry, stop, risk, held, t0 = 0, 0.0, 0.0, 0.0, 0, None
    pend, pend_exit = 0, False

    def close(px, i, why):
        nonlocal pos
        cost = COST_PCT * raw[i] + 2 * SLIP * con.tick
        pts = pos * (px - entry) - cost
        trades.append((t0, idx[i], pos, pts, pts / risk if risk else np.nan, why))
        pos = 0

    for i in range(len(b)):
        # fills at this bar's open
        if pend_exit and pos:
            close(o[i], i, "mean/time")
        pend_exit = False
        if pend and not pos:
            pos, entry, held, t0 = pend, o[i], 0, idx[i]
            stop = entry - pos * stop_k * a[i - 1]
            risk = abs(entry - stop)
        pend = 0
        if pos:
            held += 1
            if (pos == 1 and l[i] <= stop) or (pos == -1 and h[i] >= stop):
                close(min(o[i], stop) if pos == 1 else max(o[i], stop), i, "stop")
            elif eod[i]:
                close(c[i], i, "session end")
            elif (pos == 1 and c[i] >= mean[i]) or (pos == -1 and c[i] <= mean[i]) or (max_bars and held >= max_bars):
                pend_exit = True
        if not pos and not pend_exit and not eod[i] and ok[i] and not np.isnan(a[i]) and not np.isnan(mean[i]):
            if lo_sig[i]:
                pend = 1
            elif hi_sig[i]:
                pend = -1
    if pos:
        close(c[-1], len(b) - 1, "end")
    return pd.DataFrame(trades, columns=["entry_time", "exit_time", "side", "net_pts", "r_multiple", "reason"])


def stats(t, mult, months):
    if t.empty:
        return {"tpm": 0, "win": 0, "pf": 0, "net_L": 0, "dd_L": 0, "rf": 0}
    pnl = t.net_pts * mult
    eq = pnl.cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min()
    w, lo = pnl[pnl > 0].sum(), -pnl[pnl <= 0].sum()
    return {"tpm": round(len(t) / months, 1), "win": round(100 * (pnl > 0).mean(), 1),
            "pf": round(w / lo, 2) if lo > 0 else np.inf, "net_L": round(pnl.sum() / 1e5, 2),
            "dd_L": round(dd / 1e5, 2), "rf": round(pnl.sum() / max(-dd, 1), 2)}


WINDOWS = (("25", "2025-01-01", "2026-01-01", 12), ("26", "2026-01-01", "2027-01-01", 9),
           ("JulSep26", "2026-07-13", "2027-01-01", 2.4))


def run_grid(sym):
    con = CONTRACTS[sym]
    F = prep(sym)
    rows, keep = [], {}
    for cfg in itertools.product(*GRID.values()):
        tf, sig, reg, sk, mb = cfg
        t = backtest(F[tf], sig, reg, sk, mb, con)
        keep[cfg] = t
        r = dict(zip(GRID, cfg))
        for lab, lo, hi, mo in WINDOWS:
            w = t[(t.exit_time >= lo) & (t.exit_time < hi)]
            r.update({f"{k}_{lab}": v for k, v in stats(w, con.multiplier, mo).items()})
        rows.append(r)
    return pd.DataFrame(rows), keep


def smooth_rank(df):
    keys = list(GRID)
    idx = {tuple(r[k] for k in keys): r["rf_25"] for _, r in df.iterrows()}
    sc = []
    for _, r in df.iterrows():
        me = tuple(r[k] for k in keys)
        vals = [r["rf_25"]]
        for j, k in enumerate(keys):
            lv = GRID[k]
            p = lv.index(me[j])
            for q in (p - 1, p + 1):
                if 0 <= q < len(lv):
                    nb = me[:j] + (lv[q],) + me[j + 1:]
                    vals.append(idx.get(nb, 0))
        sc.append(np.mean(vals))
    df = df.copy()
    df["score_25"] = sc
    df["eligible"] = (df.tpm_25 >= 5) & (df.pf_25 >= 1.3) & (df.net_L_25 > 0)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 340); pd.set_option("display.max_columns", 40)
    for sym in ("SILVER", "GOLD"):
        df, keep = run_grid(sym)
        df = smooth_rank(df)
        df.to_csv(f"research/mean_reversion_{sym}.csv", index=False)
        el = df[df.eligible].sort_values("score_25", ascending=False)
        print(f"\n===== {sym}: {len(df)} configs, {len(el)} eligible on 2025")
        cols = list(GRID) + [c for c in df.columns if c.endswith(("_25", "_26", "_JulSep26"))]
        print(el[cols].head(12).to_string(index=False))
        top = el.head(20)
        print("top-20 still profitable in 2026 (PF>=1.2):", int((top.pf_26 >= 1.2).sum()), "/", len(top),
              "| in Jul-Sep 2026:", int((top.net_L_JulSep26 > 0).sum()), "/", len(top))
        print("all configs profitable in 2025:", int((df.net_L_25 > 0).sum()), "/", len(df),
              "| in 2026:", int((df.net_L_26 > 0).sum()), "/", len(df))
        if len(el):
            best = tuple(el.iloc[0][list(GRID)])
            keep[best].to_csv(f"research/mean_reversion_{sym}_pick_trades.csv", index=False)
