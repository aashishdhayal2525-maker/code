# Swastika Signal — reconstruction & backtest

A reconstruction of the closed-source "Swastika Signal" TradingView indicator,
built from how it draws on the chart, plus a backtest on MCX Gold and Silver.

| Path | What |
|---|---|
| `pine/swastika_signal_clone.pine` | TradingView indicator: band + Buy/Sell, cyan trail, 200 EMA, Magical labels, timeframe table, alerts |
| `pine/swastika_signal_strategy.pine` | Same logic as a `strategy()` for TradingView's Strategy Tester |
| `swastika/` | Python version of the indicator (`indicator.py`), data loading/back-adjust (`data.py`), backtester (`backtest.py`) |
| `run_backtest.py` | Runs everything and writes `results/` |
| `research/` | Calibration against the real signals, and the win-rate / drawdown experiments (`improve.py`, minute-level engine in `swastika/engine.py`) |
| `results/REPORT.md` | **Results and conclusions** |

## How the signals work

* **Band (red/green fill):** two SuperTrend lines on ATR 20, inner ×5 (blue) and
  outer ×6 (red). These settings match all 9 real signals on the user's screenshot
  (`research/calibrate.py`). **Buy/Sell** prints when price closes through the outer line
  and it flips sides.
* **Cyan line:** a wider ATR trailing stop (ATR 14 ×5, smoothed with a 5-EMA).
  It is a slower second trend vote.
* **Magenta line:** 200 EMA, the higher-level trend filter.
* **Magical BUY/SELL:** the first bar in each Buy/Sell leg where the band, the cyan
  line and the 200 EMA all agree. This one is a guess: the real label is rarer.
* **Table:** the band direction on 3m, 5m, 15m, 30m, 75m and Day.

## Run

```bash
pip install pandas numpy matplotlib
mkdir -p data   # put SILVER_nearmonth_1min_2025.csv etc. here
python run_backtest.py          # main backtest -> results/
python research/calibrate.py    # match settings to the real signals
python research/improve.py      # drawdown variants
python research/winrate.py      # win-rate variants (+ winrate_sweep.py, winrate_final.py)
```
