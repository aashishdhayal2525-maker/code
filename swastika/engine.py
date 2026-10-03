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
    take_profit_frac: float = 0.5        # ...this fraction of the position (1.0 = full exit)
    breakeven_r: float | None = None     # after +k R move the stop to entry + lock_r * R
    lock_r: float = 0.0
    trail_band: bool = False         # stop follows the outer band line each hour
    exit_fast: bool = False          # exit when the inner (x5) line flips against the trade
    day_filter: bool = False         # only trade with the Day table row
    require: tuple = ()              # extra timeframe rows that must agree, e.g. ("75m",)
    ema_filter: bool = False         # only trade on the 200 EMA's side
    adx_min: float | None = None     # skip entries when ADX(14) is below this
    long_only: bool = False
    confirm_bars: int = 0            # wait k bars; enter only if the band held and price followed through
    pullback_atr: float | None = None    # instead of buying the open, wait for a dip of k * ATR...
    pullback_bars: int = 10              # ...for at most this many bars, else skip the signal
    reentry_breakout: int | None = None  # while flat and band + filters still agree, re-enter
                                         # when a bar closes beyond the last N bars' high/low


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
             costs: Costs = Costs(), sizing: Sizing = Sizing(), day_dir=None, atr_bars=None,
             rows: dict | None = None):
    """rows: extra timeframe directions aligned to bars, e.g. {"75m": array}."""
    from .indicator import atr as atr_fn
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    a = atr_bars if atr_bars is not None else atr_fn(h, l, c, 14)
    adx_v = adx(h, l, c) if rules.adx_min else None
    buy, sell = bars["buy"].to_numpy(), bars["sell"].to_numpy()
    band = bars["st_slow"].to_numpy(float)
    band_dir = bars["band_dir"].to_numpy()
    fast_dir = bars["dir_fast"].to_numpy()
    ema_dir = bars["ema_dir"].to_numpy()
    raw = bars["raw_close"].to_numpy(float)
    rows = rows or {}

    # Map each minute to the 1h bar it belongs to.
    bar_of = np.searchsorted(bars.index.to_numpy(), minutes.index.to_numpy(), side="right") - 1
    mo, mh, ml = (minutes[k].to_numpy(float) for k in ("open", "high", "low"))
    mroll = minutes["roll"].to_numpy(bool)
    mt = minutes.index
    slip = costs.slip_ticks * contract.tick
    mult_unit = contract.multiplier if sizing.mode == "lot" else sizing.unit_mult

    trades = []
    st = dict(pos=0, qty=0.0, open_qty=0.0, entry=0.0, stop=0.0, tp=None, r_pts=0.0,
              realized=0.0, cost_pts=0.0, entry_t=None, rolls=0, tp_done=False, be_done=False)
    pend = None  # waiting entry: dict(side, sig, due, limit, expiry)

    def finish(t, reason, k):
        total_cost = st["cost_pts"] + st["rolls"] * st["qty"] * (costs.cost_pct * raw[k] + 2 * slip)
        net_pts = st["realized"] - total_cost
        trades.append({
            "side": "LONG" if st["pos"] == 1 else "SHORT", "entry_time": st["entry_t"], "exit_time": t,
            "entry": st["entry"], "qty": st["qty"], "risk_pts": st["r_pts"], "reason": reason,
            "kind": st.get("kind", "signal"),
            "gross_inr": st["realized"] * mult_unit, "net_inr": net_pts * mult_unit,
            "r_multiple": net_pts / (st["r_pts"] * st["qty"]) if st["r_pts"] > 0 else np.nan,
        })
        st["pos"] = 0

    def bank(px, q, t, reason, k):
        st["realized"] += st["pos"] * (px - st["entry"]) * q
        st["cost_pts"] += q * (costs.cost_pct * raw[k] + 2 * slip) / 2  # exit half of round trip
        st["open_qty"] -= q
        if st["open_qty"] <= 1e-9:
            finish(t, reason, k)

    def allowed(side, k):
        if rules.long_only and side == -1:
            return False
        if rules.day_filter and day_dir is not None and day_dir[k] != side:
            return False
        if any(rows[name][k] != side for name in rules.require):
            return False
        if rules.ema_filter and ema_dir[k] != side:
            return False
        if rules.adx_min and not (adx_v[k] >= rules.adx_min):
            return False
        return not np.isnan(a[k])

    def enter(px, side, k, t, kind="signal"):
        stop = px - side * rules.stop_atr * a[k] if rules.stop_atr else band[k]
        r_pts = abs(px - stop)
        if r_pts <= 0 or (side == 1 and stop >= px) or (side == -1 and stop <= px):
            return
        if sizing.mode == "lot":
            q = 1.0
        else:
            q = float(min(sizing.max_units, np.floor(sizing.risk_inr / (r_pts * sizing.unit_mult))))
        if q < 1:
            return
        st.update(pos=side, qty=q, open_qty=q, entry=px, stop=stop, r_pts=r_pts, kind=kind,
                  tp=px + side * rules.take_profit_r * r_pts if rules.take_profit_r else None,
                  realized=0.0, rolls=0, entry_t=t, tp_done=False, be_done=False,
                  cost_pts=q * (costs.cost_pct * raw[k] + 2 * slip) / 2)

    prev_bar = -1
    for i in range(len(mt)):
        j = bar_of[i]
        if st["pos"] != 0 and mroll[i]:
            st["rolls"] += 1
        new_bar = j != prev_bar
        prev_bar = j
        if new_bar and j >= 1:
            s = j - 1  # last finished bar
            pos = st["pos"]
            if pos != 0 and rules.exit_on_flip and ((pos == 1 and sell[s]) or (pos == -1 and buy[s])):
                bank(mo[i], st["open_qty"], mt[i], "flip", s)
            elif pos != 0 and rules.exit_fast and fast_dir[s] == -pos:
                bank(mo[i], st["open_qty"], mt[i], "inner line", s)
            if st["pos"] != 0 and rules.trail_band and band_dir[s] == st["pos"]:
                st["stop"] = max(st["stop"], band[s]) if st["pos"] == 1 else min(st["stop"], band[s])
            # Cancel a waiting entry once the band turns against it.
            if pend is not None and band_dir[s] != pend["side"]:
                pend = None
            if st["pos"] == 0 and (buy[s] or sell[s]):
                side = 1 if buy[s] else -1
                if allowed(side, s):
                    pend = dict(side=side, sig=s, due=s + rules.confirm_bars,
                                limit=(c[s] - side * rules.pullback_atr * a[s]) if rules.pullback_atr else None,
                                expiry=s + rules.pullback_bars)
            if pend is not None and st["pos"] == 0 and pend["limit"] is None and s >= pend["due"]:
                follow = rules.confirm_bars == 0 or (c[s] - c[pend["sig"]]) * pend["side"] > 0
                if follow:
                    enter(mo[i], pend["side"], s, mt[i])
                pend = None
            if pend is not None and pend["limit"] is not None and s > pend["expiry"]:
                pend = None
            # Trend re-entry: flat, no signal waiting, band still on one side.
            nb = rules.reentry_breakout
            if nb and st["pos"] == 0 and pend is None and s >= nb and band_dir[s] != 0:
                side = int(band_dir[s])
                brk = c[s] > h[s - nb:s].max() if side == 1 else c[s] < l[s - nb:s].min()
                if brk and allowed(side, s):
                    enter(mo[i], side, s, mt[i], kind="re-entry")
        # Pullback limit order, filled intrabar.
        if pend is not None and st["pos"] == 0 and pend["limit"] is not None:
            lim, side = pend["limit"], pend["side"]
            if (side == 1 and ml[i] <= lim) or (side == -1 and mh[i] >= lim):
                px = min(mo[i], lim) if side == 1 else max(mo[i], lim)
                enter(px, side, j - 1, mt[i])
                pend = None
        if st["pos"] == 0:
            continue
        pos, entry, r_pts = st["pos"], st["entry"], st["r_pts"]
        # Intrabar checks. The band-only stop (no stop_atr, no trail) is not a
        # resting order: that strategy exits only on the closing flip.
        if rules.stop_atr is not None or rules.trail_band or st["be_done"]:
            stop = st["stop"]
            if (ml[i] <= stop) if pos == 1 else (mh[i] >= stop):
                px = min(mo[i], stop) if pos == 1 else max(mo[i], stop)
                bank(px, st["open_qty"], mt[i], "stop", j)
                continue
        if st["tp"] is not None and not st["tp_done"]:
            tp = st["tp"]
            if (mh[i] >= tp) if pos == 1 else (ml[i] <= tp):
                st["tp_done"] = True
                bank(tp, min(st["open_qty"], st["qty"] * rules.take_profit_frac), mt[i], "target", j)
                if st["pos"] == 0:
                    continue
        if rules.breakeven_r and not st["be_done"]:
            fav = (mh[i] - entry) if pos == 1 else (entry - ml[i])
            if fav >= rules.breakeven_r * r_pts:
                lock = entry + pos * rules.lock_r * r_pts
                st["stop"] = max(st["stop"], lock) if pos == 1 else min(st["stop"], lock)
                st["be_done"] = True
    if st["pos"] != 0:
        bank(minutes["close"].iloc[-1], st["open_qty"], mt[-1], "end", len(bars) - 1)
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
