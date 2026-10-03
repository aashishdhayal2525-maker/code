# Swastika Signal — reconstruction & backtest

A reconstruction of the closed-source "Swastika Signal" TradingView indicator,
built from how it draws on the chart, plus a backtest on MCX Gold and Silver.

| Path | What |
|---|---|
| `pine/swastika_signal_clone.pine` | TradingView indicator: band + Buy/Sell, cyan trail, 200 EMA, Magical labels, timeframe table, alerts |
| `pine/swastika_signal_strategy.pine` | Same logic as a `strategy()` for TradingView's Strategy Tester |
| `swastika/` | Python version of the indicator (`indicator.py`), data loading/back-adjust (`data.py`), backtester (`backtest.py`) |
| `run_backtest.py` | Runs everything and writes `results/` |
| `results/REPORT.md` | **Results and conclusions** |

## How the signals work

* **Band (red/green fill):** two SuperTrend lines on ATR 10, inner ×2 (blue) and
  outer ×3 (red). **Buy/Sell** prints when price closes through the outer line
  and it flips sides.
* **Cyan line:** a wider ATR trailing stop (ATR 14 ×5, smoothed with a 5-EMA).
  It is a slower second trend vote.
* **Magenta line:** 200 EMA, the higher-level trend filter.
* **Magical BUY/SELL:** the first bar in each Buy/Sell leg where the band, the cyan
  line and the 200 EMA all agree.
* **Table:** the band direction on 3m, 5m, 15m, 30m, 75m and Day.

## Run

```bash
pip install pandas numpy matplotlib
mkdir -p data   # put SILVER_nearmonth_1min_2025.csv etc. here
python run_backtest.py
```
