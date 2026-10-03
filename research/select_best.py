"""Apply the selection protocol in optimize.py to its results.

Eligible on 2025: >= 10 trades/month, win >= 70%, PF >= 1.5 (20-tick fills).
Score = recovery factor (net / |max DD|) on 2025, averaged over the config
and its one-step neighbours. The pick is the top-scoring eligible config.
2026 is only read after the pick is made."""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd
from research.optimize import GRID

KEYS = ["tf", "mult", "filt", "lock", "reentry_h", "exit_htf"]
LOCKS = [f"{lk}@{tr}" for tr, lk in GRID["lock"]]
LEVELS = {"tf": GRID["tf"], "mult": GRID["mult"], "filt": GRID["filt"], "lock": LOCKS,
          "reentry_h": GRID["reentry_h"], "exit_htf": GRID["exit_htf"]}


def recovery(net, dd):
    return net / max(abs(dd), 1.0)


def score(df):
    df = df.copy()
    df["rf_25"] = [recovery(n, d) for n, d in zip(df.net_25, df.dd_25)]
    df["rf_26"] = [recovery(n, d) for n, d in zip(df.net_26, df.dd_26)]
    df["eligible"] = (df.tpm_25 >= 10) & (df.win_25 >= 70) & (df.pf_25 >= 1.5)
    idx = {tuple(r[k] for k in KEYS): r.rf_25 for r in df.itertuples()}
    smooth = []
    for r in df.itertuples():
        me = tuple(getattr(r, k) for k in KEYS)
        vals = [r.rf_25]
        for j, k in enumerate(KEYS):
            lv = LEVELS[k]
            pos = lv.index(me[j])
            for q in (pos - 1, pos + 1):
                if 0 <= q < len(lv):
                    nb = me[:j] + (lv[q],) + me[j + 1:]
                    if nb in idx:
                        vals.append(idx[nb])
        smooth.append(np.mean(vals))
    df["score_25"] = smooth
    return df


def main():
    r = pd.read_csv("research/optimize_results.csv")
    r["lock"] = r["lock"].astype(str)
    out = []
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    show = KEYS + ["tpm_25", "win_25", "pf_25", "net_25", "dd_25", "score_25",
                   "tpm_26", "win_26", "pf_26", "net_26", "dd_26"]
    for sym, df in r.groupby("symbol"):
        df = score(df)
        el = df[df.eligible].sort_values("score_25", ascending=False)
        print(f"\n===== {sym}: {len(df)} configs, {len(el)} eligible on 2025")
        print(el[show].head(15).to_string(index=False))
        top = el.head(20)
        print(f"top-20 (by 2025) that stayed good in 2026 (win>=65, PF>=1.3, tpm>=10): "
              f"{((top.win_26 >= 65) & (top.pf_26 >= 1.3) & (top.tpm_26 >= 10)).sum()}/20")
        print("rank correlation 2025 score vs 2026 recovery (eligible):",
              round(el[["score_25", "rf_26"]].corr(method="spearman").iloc[0, 1], 2))
        df["symbol"] = sym
        out.append(df)
    allr = pd.concat(out)
    allr.to_csv("research/optimize_scored.csv", index=False)

    # One config for both metals: eligible on both, rank by the weaker metal's score.
    piv = allr.pivot_table(index=KEYS, columns="symbol", values=["score_25", "eligible"], aggfunc="first")
    both = piv[(piv["eligible"]["SILVER"] == True) & (piv["eligible"]["GOLD"] == True)].copy()
    both["min_score"] = both["score_25"].min(axis=1)
    both = both.sort_values("min_score", ascending=False)
    print(f"\n===== configs eligible on BOTH metals: {len(both)}")
    print(both.head(10).to_string())


if __name__ == "__main__":
    main()
