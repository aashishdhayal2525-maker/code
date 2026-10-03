"""Load MCX near-month 1-minute CSVs, back-adjust contract rolls, resample."""
import re

import numpy as np
import pandas as pd

SESSION_OPEN_MIN = 9 * 60  # MCX opens 09:00 IST; intraday bars anchor here


def _contract_key(ticker: str) -> str:
    """Contract identity for roll detection.

    'SILVER-I.MX' is the exchange's continuous front-month symbol, which the
    vendor used for a few weeks in 2025. It is the same series, so it never
    counts as a roll on its own.
    """
    m = re.search(r"(\d{2}[A-Z]{3}\d{2})FUT", ticker)
    return m.group(1) if m else "CONT"


def load_minutes(paths) -> pd.DataFrame:
    frames = []
    for p in paths:
        d = pd.read_csv(p)
        # Rows are stamped at the last second of the minute (09:00:59 is the
        # 09:00 bar), so floor to the minute to get the bar's open time.
        ts = pd.to_datetime(d["Date"] + " " + d["Time"], format="%d-%m-%Y %H:%M:%S")
        d.index = ts.dt.floor("min")
        frames.append(d)
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.rename(columns=str.lower)[["ticker", "open", "high", "low", "close", "volume"]]
    return back_adjust(df)


def back_adjust(df: pd.DataFrame) -> pd.DataFrame:
    """Difference back-adjustment, like TradingView's B-ADJ.

    The latest contract keeps its real prices; every earlier bar is shifted by
    the price gap at each later roll, so indicators don't see fake jumps.
    """
    key = df["ticker"].map(_contract_key)
    # Ignore the continuous-symbol segments when deciding where rolls happen.
    key = key.where(key != "CONT").ffill().bfill()
    roll = key != key.shift()
    roll.iloc[0] = False
    gap = (df["open"] - df["close"].shift()).where(roll, 0.0)
    # Adjustment for a bar = sum of all roll gaps that happen after it.
    adj = gap[::-1].cumsum()[::-1].shift(-1).fillna(0.0)
    out = df.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = out[c] + adj
    out["roll"] = roll
    out["raw_close"] = df["close"]
    return out


def resample(df: pd.DataFrame, minutes: int | None) -> pd.DataFrame:
    """Session-anchored OHLCV bars. minutes=None gives daily bars.

    Bins are counted from 09:00 each day, matching how TradingView builds
    MCX bars (e.g. 75-minute bars at 09:00, 10:15, 11:30, ...).
    """
    day = df.index.normalize()
    if minutes is None:
        key = day
    else:
        mins = (df.index - day).total_seconds() // 60 - SESSION_OPEN_MIN
        key = day + pd.to_timedelta((mins // minutes) * minutes + SESSION_OPEN_MIN, unit="min")
    g = df.groupby(key)
    bars = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum(),
        "roll": g["roll"].any(),
        "raw_close": g["raw_close"].last(),
    })
    # Time the bar actually finished, used to align higher timeframes
    # without look-ahead.
    last_minute = pd.Series(df.index, index=df.index).groupby(key).last()
    bars["close_time"] = last_minute + pd.Timedelta(minutes=1)
    return bars
