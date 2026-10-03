"""Minute-level execution engine for testing exits and position sizing.

Signals come from finished 1h bars. Orders from a bar's signal fill at the
first minute of the next bar. Stops and targets are checked on every
1-minute bar after entry: a stop fills at its price, or at the minute's open
if price gapped through it. If a stop and a target are both hit in the same
minute, the stop is assumed first.

Every trade records its initial risk R (entry to initial stop, in points),
so results can be read size-free in R multiples.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import Contract, Costs


@dataclass
class Rules:
    stop_atr: float | None = None    # initial stop at entry -/+ k * ATR(signal bar); None = band only
    exit_on_flip: bool = True        # close on the opposite Buy/Sell label
    take_profit_r: float | None = None   # scale out at +k R
    take_profit_frac: float = 0.5        # ...this fraction of the position
    breakeven_r: float | None = None     # after +k R move the stop to entry
    trail_band: bool = False         # stop follows the outer band line each hour
    day_filter: bool = False         # only trade with the Day table row
    adx_min: float | None = None     # skip entries when ADX(14) is below this
    long_only: bool = False


@dataclass
class Sizing:
    mode: str = "lot"           # "lot" = 1 standard lot; "risk" = fixed rupee risk per trade
    risk_inr: float = 20_000    # rupees lost at the initial stop, for mode="risk"
    unit_mult: float = 1.0      # rupees per point for one smallest tradable unit
    max_units: int = 10_000


def adx(h, l, c, n=14):
    from .indicator import rma
    up, dn = np.diff(h, prepend=np.nan), -np.diff(l, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    atr_, p, m = rma(tr, n), rma(pdm, n), rma(ndm, n)
    pdi, ndi = 100 * p / atr_, 100 * m / atr_
    dx = 100 * np.abs(pdi - ndi) / np.where(pdi + ndi == 0, np.nan, pdi + ndi)
    return rma(np.nan_to_num(dx), n)


def simulate(minutes: pd.DataFrame, bars: pd.DataFrame, rules: Rules, contract: Contract,
             costs: Costs = Costs(), sizing: Sizing = Sizing(), day_dir=None, atr_bars=None):
    from .indicator import atr as atr_fn
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    a = atr_bars if atr_bars is not None else atr_fn(h, l, c, 14)
    adx_v = adx(h, l, c) if rules.adx_min else None
    buy, sell = bars["buy"].to_numpy(), bars["sell"].to_numpy()
    band = bars["st_slow"].to_numpy(float)
    band_dir = bars["band_dir"].to_numpy()
    raw = bars["raw_close"].to_numpy(float)

    # Map each minute to the 1h bar it belongs to.
    bar_of = np.searchsorted(bars.index.to_numpy(), minutes.index.to_numpy(), side="right") - 1
    mo, mh, ml = (minutes[k].to_numpy(float) for k in ("open", "high", "low"))
    mroll = minutes["roll"].to_numpy(bool)
    mt = minutes.index
    slip = costs.slip_ticks * contract.tick

    trades = []
    pos = 0              # +1 / -1
    qty = 0.0            # units held (lots for "lot" sizing, units for "risk")
    open_qty = 0.0
    entry = stop = tp = r_pts = 0.0
    realized = 0.0       # points * qty already banked from scale-outs
    cost_pts = 0.0
    entry_t = None
    rolls = 0
    tp_done = be_done = False

    def bank(px, q, t, reason):
        nonlocal realized, cost_pts, open_qty
        realized += pos * (px - entry) * q
        cost_pts += q * (costs.cost_pct * raw[bar_of_i] + 2 * slip) / 2  # exit half of round trip
        open_qty -= q
        if open_qty <= 1e-9:
            finish(t, reason)

    def finish(t, reason):
        nonlocal pos
        total_cost = cost_pts + rolls * qty * (costs.cost_pct * raw[bar_of_i] + 2 * slip)
        net_pts = realized - total_cost
        trades.append({
            "side": "LONG" if pos == 1 else "SHORT", "entry_time": entry_t, "exit_time": t,
            "entry": entry, "qty": qty, "risk_pts": r_pts, "reason": reason,
            "gross_inr": realized * mult_unit, "net_inr": net_pts * mult_unit,
            "r_multiple": net_pts / (r_pts * qty) if r_pts > 0 else np.nan,
        })
        pos = 0

    mult_unit = contract.multiplier if sizing.mode == "lot" else sizing.unit_mult
    prev_bar = -1
    bar_of_i = 0
    for i in range(len(mt)):
        j = bar_of[i]
        bar_of_i = j
        if pos != 0 and mroll[i]:
            rolls += 1
        new_bar = j != prev_bar
        prev_bar = j
        if new_bar and j >= 1:
            s = j - 1  # last finished bar
            # 1) exit on opposite label
            if pos != 0 and rules.exit_on_flip and ((pos == 1 and sell[s]) or (pos == -1 and buy[s])):
                bank(mo[i], open_qty, mt[i], "flip")
            # 2) trail stop with the band
            if pos != 0 and rules.trail_band and band_dir[s] == pos:
                stop = max(stop, band[s]) if pos == 1 else min(stop, band[s])
            # 3) new entry
            if pos == 0 and (buy[s] or sell[s]):
                side = 1 if buy[s] else -1
                ok = True
                if rules.long_only and side == -1:
                    ok = False
                if rules.day_filter and day_dir is not None and day_dir[s] != side:
                    ok = False
                if rules.adx_min and not (adx_v[s] >= rules.adx_min):
                    ok = False
                if ok and not np.isnan(a[s]):
                    entry = mo[i]
                    band_stop = band[s]
                    if rules.stop_atr:
                        stop = entry - side * rules.stop_atr * a[s]
                    else:
                        stop = band_stop
                    r_pts = abs(entry - stop)
                    if sizing.mode == "lot":
                        q = 1.0
                    else:
                        q = float(min(sizing.max_units, np.floor(sizing.risk_inr / (r_pts * sizing.unit_mult))))
                    if q >= 1 and r_pts > 0:
                        pos, qty, open_qty = side, q, q
                        tp = entry + side * rules.take_profit_r * r_pts if rules.take_profit_r else None
                        realized, rolls, entry_t = 0.0, 0, mt[i]
                        cost_pts = q * (costs.cost_pct * raw[s] + 2 * slip) / 2  # entry half
                        tp_done = be_done = False
        if pos == 0:
            continue
        # Intrabar checks. The band-only stop (no stop_atr, no trail) is not a
        # resting order: that strategy exits only on the closing flip.
        has_stop = rules.stop_atr is not None or rules.trail_band or be_done
        if has_stop:
            hit = (ml[i] <= stop) if pos == 1 else (mh[i] >= stop)
            if hit:
                px = min(mo[i], stop) if pos == 1 else max(mo[i], stop)
                bank(px, open_qty, mt[i], "stop")
                continue
        if tp is not None and not tp_done:
            hit = (mh[i] >= tp) if pos == 1 else (ml[i] <= tp)
            if hit:
                q = qty * rules.take_profit_frac
                tp_done = True
                bank(tp, q, mt[i], "target")
                if pos == 0:
                    continue
        if rules.breakeven_r and not be_done:
            fav = (mh[i] - entry) if pos == 1 else (entry - ml[i])
            if fav >= rules.breakeven_r * r_pts:
                stop = max(stop, entry) if pos == 1 else min(stop, entry)
                be_done = True
    if pos != 0:
        bank(minutes["close"].iloc[-1], open_qty, mt[-1], "end")
    return pd.DataFrame(trades)


def r_stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    pnl = t["net_inr"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min()
    r = t["r_multiple"]
    req = r.cumsum()
    rdd = (req - req.cummax().clip(lower=0)).min()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    # Longest run of consecutive losers.
    streak = run = 0
    for x in pnl:
        run = run + 1 if x <= 0 else 0
        streak = max(streak, run)
    return {
        "trades": len(t),
        "win_%": round(100 * len(wins) / len(t), 1),
        "net_inr": round(pnl.sum()),
        "pf": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else np.inf,
        "max_dd_inr": round(dd),
        "net_R": round(r.sum(), 1),
        "avg_R": round(r.mean(), 2),
        "max_dd_R": round(rdd, 1),
        "worst_streak": streak,
    }
