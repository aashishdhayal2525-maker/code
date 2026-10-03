"""Reconstruction of the 'Swastika Signal' chart components.

The original is a closed, invite-only TradingView script, so this is a
reconstruction from how it draws on the chart, not its actual source:

  band     two SuperTrend lines (inner/blue x5, outer/red x6, ATR 20) with
           the gap between them filled green (uptrend) or red (downtrend).
           Buy / Sell prints when the slow line flips.
  cyan     a smoother, wider ATR trailing stop (UT-Bot style), drawn
           EMA-smoothed. Its side of price is a second trend vote.
  magenta  long EMA (200) as the higher-level trend filter.
  magical  first bar in each band trend where all three agree:
           band + cyan + EMA200. At most one per Buy/Sell leg.
           UNVERIFIED: the real Magical label is much rarer (none on 9
           consecutive legs in Jul-Sep 2026) and no cyan setting tested
           reproduces it. Treat this one as a guess.
  table    the band direction on other timeframes (see mtf_directions).

All functions follow TradingView's definitions (RMA-based ATR,
ta.supertrend ratchet rules) so values match a Pine port bar for bar.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Params:
    # Calibrated to the real indicator: with these, all 9 Buy/Sell labels on
    # the user's SILVER1! 1h screenshot (21 Jul - 17 Sep 2026) are matched
    # within ~2 bars and no extra labels appear. See research/calibrate.py.
    st_atr_len: int = 20
    st_fast_mult: float = 5.0
    st_slow_mult: float = 6.0
    cyan_atr_len: int = 14
    cyan_mult: float = 5.0
    cyan_smooth: int = 5
    ema_len: int = 200


def rma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = np.nanmean(x[:n])
    a = 1.0 / n
    for i in range(n, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def atr(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return rma(tr, n)


def ema(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def supertrend(h, l, c, atr_len, mult):
    """Returns (line, direction) with direction +1 = up, -1 = down."""
    a = atr(h, l, c, atr_len)
    hl2 = (h + l) / 2
    n = len(c)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    line = np.full(n, np.nan)
    d = np.zeros(n, dtype=int)
    for i in range(n):
        if np.isnan(a[i]):
            continue
        up, dn = hl2[i] - mult * a[i], hl2[i] + mult * a[i]
        if i == 0 or np.isnan(lower[i - 1]):
            lower[i], upper[i], d[i] = up, dn, -1
            line[i] = upper[i]
            continue
        lower[i] = up if (up > lower[i - 1] or c[i - 1] < lower[i - 1]) else lower[i - 1]
        upper[i] = dn if (dn < upper[i - 1] or c[i - 1] > upper[i - 1]) else upper[i - 1]
        if line[i - 1] == upper[i - 1]:
            d[i] = 1 if c[i] > upper[i] else -1
        else:
            d[i] = -1 if c[i] < lower[i] else 1
        line[i] = lower[i] if d[i] == 1 else upper[i]
    return line, d


def atr_trail(h, l, c, atr_len, mult):
    """UT-Bot style trailing stop on close. Returns (trail, direction)."""
    loss = mult * atr(h, l, c, atr_len)
    n = len(c)
    t = np.full(n, np.nan)
    d = np.zeros(n, dtype=int)
    for i in range(n):
        if np.isnan(loss[i]):
            continue
        p = t[i - 1] if i > 0 else np.nan
        if np.isnan(p):
            t[i] = c[i] - loss[i]
        elif c[i] > p and c[i - 1] > p:
            t[i] = max(p, c[i] - loss[i])
        elif c[i] < p and c[i - 1] < p:
            t[i] = min(p, c[i] + loss[i])
        elif c[i] > p:
            t[i] = c[i] - loss[i]
        else:
            t[i] = c[i] + loss[i]
        d[i] = 1 if c[i] > t[i] else -1
    return t, d


def compute(bars: pd.DataFrame, p: Params = Params()) -> pd.DataFrame:
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    out = bars.copy()
    out["st_fast"], out["dir_fast"] = supertrend(h, l, c, p.st_atr_len, p.st_fast_mult)
    out["st_slow"], out["band_dir"] = supertrend(h, l, c, p.st_atr_len, p.st_slow_mult)
    trail, out["cyan_dir"] = atr_trail(h, l, c, p.cyan_atr_len, p.cyan_mult)
    out["cyan"] = ema(trail, p.cyan_smooth)
    out["ema"] = ema(c, p.ema_len)
    out["ema_dir"] = np.where(np.isnan(out["ema"]), 0, np.where(c > out["ema"], 1, -1))

    bd = out["band_dir"]
    out["buy"] = (bd == 1) & (bd.shift() == -1)
    out["sell"] = (bd == -1) & (bd.shift() == 1)

    bull = (bd == 1) & (out["cyan_dir"] == 1) & (out["ema_dir"] == 1)
    bear = (bd == -1) & (out["cyan_dir"] == -1) & (out["ema_dir"] == -1)
    # One Magical label per band leg: the first bar of the leg where the
    # three votes line up. Without this it re-fires every time price
    # wobbles across the EMA.
    leg = (bd != bd.shift()).cumsum()
    first_bull = bull & (bull.astype(int).groupby(leg).cumsum() == 1)
    first_bear = bear & (bear.astype(int).groupby(leg).cumsum() == 1)
    out["magic_buy"] = first_bull
    out["magic_sell"] = first_bear
    return out


def mtf_directions(minute_df, base: pd.DataFrame, frames: dict, p: Params = Params()):
    """Band direction from each higher/lower timeframe, as known at the
    close of every base bar (no look-ahead: a bar is only used once it has
    finished)."""
    from .data import resample

    res = pd.DataFrame(index=base.index)
    for name, mins in frames.items():
        tf = resample(minute_df, mins)
        _, d = supertrend(*(tf[k].to_numpy(float) for k in ("high", "low", "close")),
                          p.st_atr_len, p.st_slow_mult)
        s = pd.Series(d, index=tf["close_time"].to_numpy()).sort_index()
        s = s[~s.index.duplicated(keep="last")]
        res[name] = s.reindex(base["close_time"].to_numpy(), method="ffill").to_numpy()
    return res.fillna(0).astype(int)
