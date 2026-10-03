"""Final candidates in rupees (1 lot) with the size of wins and losses."""
import sys; sys.path.insert(0, ".")
from dataclasses import replace
import pandas as pd
from research.winrate import BASE, load
from swastika.backtest import CONTRACTS
from swastika.engine import simulate, r_stats

FINAL = {
    "V1 Day filter (current)": BASE,
    "W8 V1 + lock +0.1R once up 0.5R": replace(BASE, breakeven_r=0.5, lock_r=0.1),
    "W8 + 1-bar confirmation (post-hoc)": replace(BASE, breakeven_r=0.5, lock_r=0.1, confirm_bars=1),
}
rows = []
for sym, con in CONTRACTS.items():
    m, bars, t = load(sym)
    for name, rules in FINAL.items():
        tr = simulate(m, bars, rules, con, day_dir=t["Day"].to_numpy())
        tr.to_csv(f"results/trades_{sym}_{name.split()[0]}{'_confirm' if 'confirm' in name else ''}.csv", index=False)
        w, l = tr[tr.net_inr > 0], tr[tr.net_inr <= 0]
        for period, tt in (("ALL", tr), ("2025", tr[tr.exit_time.dt.year == 2025]), ("2026", tr[tr.exit_time.dt.year == 2026])):
            s = r_stats(tt)
            rows.append({"symbol": sym, "variant": name, "period": period, **s,
                         "avg_win_R": round(tt[tt.net_inr > 0].r_multiple.mean(), 2),
                         "avg_loss_R": round(tt[tt.net_inr <= 0].r_multiple.mean(), 2),
                         "small_wins_<0.2R": int(((tt.r_multiple > 0) & (tt.r_multiple < 0.2)).sum())})
r = pd.DataFrame(rows)
r.to_csv("results/winrate_final.csv", index=False)
pd.set_option("display.width", 300)
print(r.to_string(index=False))
