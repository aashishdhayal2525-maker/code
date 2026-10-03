"""Is the breakeven trigger a knife-edge? Sweep it, plus post-hoc combos
(not part of the pre-registered selection; reported as such)."""
import sys; sys.path.insert(0, ".")
from dataclasses import replace
import pandas as pd
from research.winrate import BASE, load, run_all
from swastika.backtest import CONTRACTS

data = {s: load(s) for s in CONTRACTS}
v = {}
for be in (0.25, 0.4, 0.5, 0.6, 0.75, 1.0):
    for lock in (0.0, 0.1, 0.2):
        if lock < be:
            v[f"BE {be}R lock {lock}R"] = replace(BASE, breakeven_r=be, lock_r=lock)
v["combo W8 + confirm 1 bar"] = replace(BASE, breakeven_r=0.5, lock_r=0.1, confirm_bars=1)
v["combo W8 + exit on inner line"] = replace(BASE, breakeven_r=0.5, lock_r=0.1, exit_fast=True)
r = run_all(v, data)
r.to_csv("research/winrate_sweep.csv", index=False)
pd.set_option("display.width", 300)
piv = r.pivot_table(index="variant", columns=["symbol", "period"], values=["win_%", "net_R"], sort=False)
print(piv.round(1).to_string())
