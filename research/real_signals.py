"""Signals of the real Swastika Signal on SILVER1! 1h, read off the user's
TradingView screenshot (Jul-Sep 2026). Times are estimated from pixel
positions (~2.1 px per 1h bar, anchored on the crosshair at 16 Sep 13:00),
so treat them as +-3 bars."""
import pandas as pd

REAL = pd.DataFrame([
    ("2026-07-21 12:00", "buy"),
    ("2026-07-23 18:00", "sell"),
    ("2026-08-04 17:00", "buy"),
    ("2026-08-19 09:00", "sell"),   # drawn together with an orange "Fake SELL"
    ("2026-08-19 20:00", "buy"),
    ("2026-08-27 09:00", "sell"),
    ("2026-09-03 19:00", "buy"),
    ("2026-09-10 17:00", "sell"),
    ("2026-09-17 22:00", "buy"),
], columns=["time", "side"]).assign(time=lambda d: pd.to_datetime(d["time"]))
WINDOW = ("2026-07-20", "2026-09-23 23:59")
