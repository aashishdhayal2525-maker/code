"""Monthly backtest workbook: results/Swastika_Monthly_Backtest.xlsx

Trades are simulated by swastika/engine.py (1 lot, costs included) and
written as values. Every monthly and summary number is an Excel formula
over the Trades sheet, so changing the lot size recalculates everything."""
import sys; sys.path.insert(0, ".")
from dataclasses import replace

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from research.winrate import BASE, load
from swastika.backtest import CONTRACTS
from swastika.data import load_minutes, resample
from swastika.engine import Rules, simulate
from swastika.indicator import Params, compute, mtf_directions
import glob

STRATS = [  # code, name, rules
    ("V0", "Real Buy/Sell, always in", Rules()),
    ("V1", "Day filter", BASE),
    ("W8", "Day filter + profit lock", replace(BASE, breakeven_r=0.5, lock_r=0.1)),
    ("W8C", "Day + lock + 1-bar confirm", replace(BASE, breakeven_r=0.5, lock_r=0.1, confirm_bars=1)),
    ("T6", "W8, faster band x3/x4 (1h)", replace(BASE, breakeven_r=0.5, lock_r=0.1)),
    ("T7", "W8 on 30m + trend re-entry", replace(BASE, breakeven_r=0.5, lock_r=0.1, reentry_breakout=20)),
    ("U1", "W8 on 15m chart", replace(BASE, breakeven_r=0.5, lock_r=0.1)),
    ("U9", "W8 on 5m chart", replace(BASE, breakeven_r=0.5, lock_r=0.1)),
    ("Q1", "5m: 1h filter, lock 0.15R@0.3R, re-entry 120", replace(BASE, require=("60m",), breakeven_r=0.3, lock_r=0.15,
                                                                   reentry_breakout=120)),
    ("Q2", "Q1 with a bigger lock 0.2R@0.4R (Gold setting)", replace(BASE, require=("60m",), breakeven_r=0.4, lock_r=0.2,
                                                                       reentry_breakout=120)),
    ("BS", "BEST Silver: 5m, Day+4h, lock 0.2R@0.4R, re-entry 10h", replace(BASE, require=("240m",), breakeven_r=0.4,
                                                                             lock_r=0.2, reentry_breakout=120)),
    ("BG", "BEST Gold: 15m x3/x4, Day+1h, lock 0.2R@0.4R, re-entry 5h", replace(BASE, require=("60m",), breakeven_r=0.4,
                                                                                 lock_r=0.2, reentry_breakout=20)),
]
FAST = replace(Params(), st_fast_mult=3.0, st_slow_mult=4.0)
FAST45 = FAST  # x3/x4 band, used by BG
SETUP = {"T6": (60, FAST), "T7": (30, Params()), "U1": (15, Params()), "U9": (5, Params()), "Q1": (5, Params()), "Q2": (5, Params()),
         "BS": (5, Params()), "BG": (15, FAST45)}  # code -> (bar minutes, band params); default 1h, real band
SYMS = list(CONTRACTS)
MONTHS = pd.date_range("2025-01-01", "2026-09-01", freq="MS")

# ── simulate ──────────────────────────────────────────────────────────────
rows = []
for sym, con in CONTRACTS.items():
    m = load_minutes(sorted(glob.glob(f"data/{sym}_nearmonth_1min_*.csv")))
    cache = {}
    for code, _, rules in STRATS:
        tf, prm = SETUP.get(code, (60, Params()))
        if (tf, repr(prm)) not in cache:
            bars = compute(resample(m, tf), prm)
            d = mtf_directions(m, bars, {"60m": 60, "240m": 240, "Day": None}, Params())
            cache[(tf, repr(prm))] = (bars, d["Day"].to_numpy(),
                                      {"60m": d["60m"].to_numpy(), "240m": d["240m"].to_numpy()})
        bars, day, extra = cache[(tf, repr(prm))]
        tr = simulate(m, bars, rules, con, day_dir=day, rows=extra)
        tr["symbol"], tr["code"] = sym, code
        tr["net_pts"] = tr["net_inr"] / con.multiplier
        rows.append(tr)
trades = pd.concat(rows).sort_values(["symbol", "code", "exit_time"]).reset_index(drop=True)
trades["symbol"] = pd.Categorical(trades["symbol"], SYMS)
trades["code"] = pd.Categorical(trades["code"], [s[0] for s in STRATS])
trades = trades.sort_values(["symbol", "code", "exit_time"]).reset_index(drop=True)

# ── styles ────────────────────────────────────────────────────────────────
F = "Arial"
base, bold = Font(name=F, size=10), Font(name=F, size=10, bold=True)
title = Font(name=F, size=14, bold=True)
blue = Font(name=F, size=10, color="0000FF")
green = Font(name=F, size=10, color="008000")
white_b = Font(name=F, size=10, bold=True, color="FFFFFF")
hdr_fill = PatternFill("solid", fgColor="1F3864")
sub_fill = PatternFill("solid", fgColor="D9E1F2")
yellow = PatternFill("solid", fgColor="FFFF00")
tot_fill = PatternFill("solid", fgColor="F2F2F2")
thin = Side(style="thin", color="BFBFBF")
box = Border(top=thin, bottom=thin, left=thin, right=thin)
INR = '"₹"#,##0;[Red]("₹"#,##0);"-"'
PCT = '0.0%;-0.0%;"-"'
CNT = '0;-0;"-"'
center = Alignment(horizontal="center", vertical="center", wrap_text=True)

def style(c, font=base, fmt=None, fill=None, align=None, border=True):
    c.font = font
    if fmt: c.number_format = fmt
    if fill: c.fill = fill
    if align: c.alignment = align
    if border: c.border = box

wb = Workbook()
ws_sum = wb.active; ws_sum.title = "Summary"
ws_tr = wb.create_sheet("Trades")
monthly = {s: wb.create_sheet(f"{s.title()} Monthly") for s in SYMS}
ws_notes = wb.create_sheet("Notes")

# ── Summary: inputs block ─────────────────────────────────────────────────
ws_sum["A1"] = "Swastika Signal (reconstructed) - backtest summary, MCX 1h, Jan 2025 - Sep 2026"
ws_sum["A1"].font = title
ws_sum["A3"] = "Inputs (edit the yellow cells)"; ws_sum["A3"].font = bold
inputs = [("Lots per trade", 1, "Number of standard lots per trade. All P&L scales with this."),
          ("Silver: ₹ per point per lot", 30, "MCX SILVER lot = 30 kg, quoted in ₹/kg."),
          ("Gold: ₹ per point per lot", 100, "MCX GOLD lot = 1 kg, quoted in ₹/10 g.")]
for i, (k, v, note) in enumerate(inputs, start=4):
    ws_sum.cell(i, 1, k).font = base
    c = ws_sum.cell(i, 2, v); style(c, blue, "#,##0", yellow)
    c.comment = Comment(note, "backtest")
    ws_sum.cell(i, 3, note).font = Font(name=F, size=9, italic=True, color="595959")
LOTS, MULT = "Summary!$B$4", {"SILVER": "Summary!$B$5", "GOLD": "Summary!$B$6"}

# ── Trades sheet ──────────────────────────────────────────────────────────
th = ["Metal", "Strategy", "Side", "Entry time", "Exit time", "Exit month", "Entry price",
      "Exit reason", "Net points / lot (after costs)", "Lots", "Net P&L (₹)", "R multiple",
      "Win (1/0)", "Cumulative P&L (₹)", "Peak (₹)", "Drawdown (₹)"]
for j, h in enumerate(th, 1):
    style(ws_tr.cell(1, j, h), white_b, fill=hdr_fill, align=center)
n = len(trades)
for i, r in enumerate(trades.itertuples(), start=2):
    vals = [r.symbol, r.code, r.side, r.entry_time.to_pydatetime(), r.exit_time.to_pydatetime()]
    for j, v in enumerate(vals, 1):
        style(ws_tr.cell(i, j, v), blue if j > 3 else base,
              "dd-mmm-yy hh:mm" if j in (4, 5) else None)
    style(ws_tr.cell(i, 6, f"=DATE(YEAR(E{i}),MONTH(E{i}),1)"), base, "mmm-yyyy")
    style(ws_tr.cell(i, 7, round(r.entry, 2)), blue, "#,##0")
    style(ws_tr.cell(i, 8, r.reason), base)
    style(ws_tr.cell(i, 9, round(r.net_pts, 2)), blue, "#,##0.0;[Red]-#,##0.0")
    style(ws_tr.cell(i, 10, f"={LOTS}"), green, "0")
    style(ws_tr.cell(i, 11, f'=I{i}*J{i}*IF(A{i}="SILVER",{MULT["SILVER"]},{MULT["GOLD"]})'), base, INR)
    style(ws_tr.cell(i, 12, round(r.r_multiple, 3)), blue, "0.00;[Red]-0.00")
    style(ws_tr.cell(i, 13, f"=IF(K{i}>0,1,0)"), base, "0")
    style(ws_tr.cell(i, 14, f"=SUMIFS(K$2:K{i},A$2:A{i},A{i},B$2:B{i},B{i})"), base, INR)
    style(ws_tr.cell(i, 15, f"=MAX(0,_xlfn.MAXIFS(N$2:N{i},A$2:A{i},A{i},B$2:B{i},B{i}))"), base, INR)
    style(ws_tr.cell(i, 16, f"=N{i}-O{i}"), base, INR)
ws_tr.freeze_panes = "A2"
ws_tr.auto_filter.ref = f"A1:P{n + 1}"
for j, w in enumerate([8, 9, 7, 16, 16, 10, 11, 11, 13, 6, 13, 9, 8, 15, 13, 13], 1):
    ws_tr.column_dimensions[L(j)].width = w
ws_tr.row_dimensions[1].height = 42
last = n + 1
R = lambda col: f"Trades!${col}$2:${col}${last}"

# ── Monthly sheets ────────────────────────────────────────────────────────
FIRST = 5
LASTM = FIRST + len(MONTHS) - 1
mcols = {}  # (sym, code) -> dict of column letters
for sym, ws in monthly.items():
    ws["A1"] = f"{sym.title()} - monthly backtest (P&L booked in the month a trade closes)"
    ws["A1"].font = title
    ws["A2"] = "All figures are formulas over the Trades sheet; lot size comes from Summary!B4."
    ws["A2"].font = Font(name=F, size=9, italic=True, color="595959")
    style(ws.cell(3, 1, "Month"), white_b, fill=hdr_fill, align=center)
    ws.merge_cells(start_row=3, start_column=1, end_row=4, end_column=1)
    for k, (code, name, _) in enumerate(STRATS):
        c0 = 2 + k * 4
        ws.merge_cells(start_row=3, start_column=c0, end_row=3, end_column=c0 + 3)
        style(ws.cell(3, c0, f"{code}: {name}"), white_b, fill=hdr_fill, align=center)
        for jj in range(c0 + 1, c0 + 4):
            ws.cell(3, jj).border = box; ws.cell(3, jj).fill = hdr_fill
        for jj, h in enumerate(["Trades", "Win %", "Net P&L (₹)", "Cumulative (₹)"]):
            style(ws.cell(4, c0 + jj, h), bold, fill=sub_fill, align=center)
        t, w, p, cum = (L(c0 + x) for x in range(4))
        mcols[(sym, code)] = dict(t=t, w=w, p=p, cum=cum)
        crit = f'{R("A")},"{sym}",{R("B")},"{code}"'
        for i, mth in enumerate(MONTHS, start=FIRST):
            if k == 0:
                style(ws.cell(i, 1, mth.to_pydatetime()), bold, "mmm-yyyy")
            mc = f"{R('F')},$A{i}"
            style(ws[f"{t}{i}"], base, CNT); ws[f"{t}{i}"] = f"=COUNTIFS({crit},{mc})"
            ws[f"{w}{i}"] = f'=IF({t}{i}=0,"",COUNTIFS({crit},{mc},{R("M")},1)/{t}{i})'
            style(ws[f"{w}{i}"], base, PCT)
            ws[f"{p}{i}"] = f"=SUMIFS({R('K')},{crit},{mc})"; style(ws[f"{p}{i}"], base, INR)
            ws[f"{cum}{i}"] = f"={p}{i}" if i == FIRST else f"={cum}{i - 1}+{p}{i}"
            style(ws[f"{cum}{i}"], base, INR)
        # yearly + total rows
        for off, (lab, lo, hi) in enumerate([("2025 total", "2025-01-01", "2026-01-01"),
                                             ("2026 total (to Sep)", "2026-01-01", "2027-01-01"),
                                             ("All months", "2025-01-01", "2027-01-01")]):
            i = LASTM + 2 + off
            if k == 0:
                style(ws.cell(i, 1, lab), bold, fill=tot_fill)
            y0, y1 = pd.Timestamp(lo), pd.Timestamp(hi)
            dcrit = (f'$A${FIRST}:$A${LASTM},">="&DATE({y0.year},1,1),'
                     f'$A${FIRST}:$A${LASTM},"<"&DATE({y1.year},1,1)')
            ws[f"{t}{i}"] = f"=SUMIFS({t}${FIRST}:{t}${LASTM},{dcrit})"
            tcrit = (f'{crit},{R("E")},">="&DATE({y0.year},1,1),{R("E")},"<"&DATE({y1.year},1,1)')
            ws[f"{w}{i}"] = f'=IF({t}{i}=0,"",COUNTIFS({tcrit},{R("M")},1)/{t}{i})'
            ws[f"{p}{i}"] = f"=SUMIFS({p}${FIRST}:{p}${LASTM},{dcrit})"
            ws[f"{cum}{i}"] = ""
            for col, fmt in ((t, CNT), (w, PCT), (p, INR), (cum, INR)):
                style(ws[f"{col}{i}"], bold, fmt, tot_fill)
    ws.column_dimensions["A"].width = 18
    for j in range(2, 2 + 4 * len(STRATS)):
        ws.column_dimensions[L(j)].width = 13
    ws.row_dimensions[3].height = 30
    ws.freeze_panes = f"B{FIRST}"
    ch = LineChart()
    ch.title = f"{sym.title()} - cumulative net P&L by month (₹)"
    ch.height, ch.width = 9, 24
    ch.y_axis.title, ch.y_axis.numFmt = "₹", "#,##0"
    ch.x_axis.number_format = "mmm-yy"
    for code, _, _ in STRATS:
        col = ws[f"{mcols[(sym, code)]['cum']}1"].column
        ref = Reference(ws, min_col=col, min_row=FIRST, max_row=LASTM)
        ch.add_data(ref, titles_from_data=False)
        ch.series[-1].tx = None
    from openpyxl.chart.series import SeriesLabel
    for s, (code, name, _) in zip(ch.series, STRATS):
        s.tx = SeriesLabel(v=f"{code} {name}")
    ch.set_categories(Reference(ws, min_col=1, min_row=FIRST, max_row=LASTM))
    ws.add_chart(ch, f"A{LASTM + 7}")

# ── Summary table ─────────────────────────────────────────────────────────
H0 = 9
ws_sum.cell(H0 - 1, 1, "Results by strategy (all formulas)").font = bold
sh = ["Metal", "Strategy", "Description", "Trades", "Wins", "Win %", "Net P&L (₹)", "2025 net (₹)",
      "2026 net (₹)", "Avg win (₹)", "Avg loss (₹)", "Profit factor", "Max drawdown (₹)",
      "Profitable months %", "Best month (₹)", "Worst month (₹)", "Trades / month"]
for j, h in enumerate(sh, 1):
    style(ws_sum.cell(H0, j, h), white_b, fill=hdr_fill, align=center)
ws_sum.row_dimensions[H0].height = 32
i = H0 + 1
for sym in SYMS:
    sheet = f"'{sym.title()} Monthly'"
    for code, name, _ in STRATS:
        mc = mcols[(sym, code)]
        crit = f'{R("A")},A{i},{R("B")},B{i}'
        cells = [sym, code, name,
                 f"=COUNTIFS({crit})",
                 f"=COUNTIFS({crit},{R('M')},1)",
                 f'=IF(D{i}=0,"",E{i}/D{i})',
                 f"=SUMIFS({R('K')},{crit})",
                 f'=SUMIFS({R("K")},{crit},{R("E")},">="&DATE(2025,1,1),{R("E")},"<"&DATE(2026,1,1))',
                 f'=SUMIFS({R("K")},{crit},{R("E")},">="&DATE(2026,1,1))',
                 f'=IFERROR(AVERAGEIFS({R("K")},{crit},{R("K")},">0"),0)',
                 f'=IFERROR(AVERAGEIFS({R("K")},{crit},{R("K")},"<=0"),0)',
                 f'=IFERROR(SUMIFS({R("K")},{crit},{R("K")},">0")/-SUMIFS({R("K")},{crit},{R("K")},"<=0"),"no losses")',
                 f"=_xlfn.MINIFS({R('P')},{crit})",
                 f'=IFERROR(COUNTIF({sheet}!{mc["p"]}${FIRST}:{mc["p"]}${LASTM},">0")/COUNTIF({sheet}!{mc["t"]}${FIRST}:{mc["t"]}${LASTM},">0"),"")',
                 f"=MAX({sheet}!{mc['p']}${FIRST}:{mc['p']}${LASTM})",
                 f"=MIN({sheet}!{mc['p']}${FIRST}:{mc['p']}${LASTM})",
                 f"=D{i}/COUNT({sheet}!$A${FIRST}:$A${LASTM})"]
        fmts = [None, None, None, CNT, CNT, PCT, INR, INR, INR, INR, INR, "0.00", INR, PCT, INR, INR, "0.0"]
        for j, (v, fm) in enumerate(zip(cells, fmts), 1):
            style(ws_sum.cell(i, j, v), bold if j <= 2 else base, fm,
                  sub_fill if (sym, code) in (("SILVER", "BS"), ("GOLD", "BG")) else None)
        i += 1
ws_sum.cell(i + 1, 1, "Highlighted rows = recommended setup per metal (BS for Silver, BG for Gold). "
                      "W8C was chosen after seeing results and rests on 16-18 trades. T6/T7/U1/U9 trade more often at a lower win rate. Recommended: BS on Silver, BG on Gold (chosen on 2025 only, held up in 2026).").font = \
    Font(name=F, size=9, italic=True, color="595959")
for j, w in enumerate([10, 9, 26, 8, 7, 8, 14, 13, 13, 12, 12, 10, 15, 11, 13, 13, 9], 1):
    ws_sum.column_dimensions[L(j)].width = w
ws_sum.column_dimensions["A"].width = 28
ws_sum.freeze_panes = f"D{H0 + 1}"

# ── Notes ─────────────────────────────────────────────────────────────────
notes = [
    ("Data", "MCX near-month futures, 1-minute bars, 1 Jan 2025 - 23 Sep 2026 (user-supplied CSVs). "
             "Contract rolls are back-adjusted by the roll gap (like TradingView B-ADJ)."),
    ("Signals", "Reconstructed Swastika Signal on 1h bars from 09:00: SuperTrend band ATR 20, inner x5 / outer x6. "
                "These settings reproduce all 9 real Buy/Sell labels on the user's SILVER1! screenshot (Jul-Sep 2026)."),
    ("Day row", "Direction of the same band on daily bars, using the previous finished day only (no look-ahead)."),
    ("V0", "Every Buy/Sell label, always in the market (stop-and-reverse)."),
    ("V1", "Take Buy/Sell only when the Day row agrees; exit on the opposite label; otherwise flat."),
    ("W8", "V1 + once the trade is +0.5R in profit, move the stop to entry +0.1R. "
           "R = distance from entry to the outer band at entry. Checked minute by minute."),
    ("W8C", "W8 + wait one bar after the signal and enter only if the band held and the bar closed beyond the signal bar. "
            "Chosen after seeing results; small sample (16-18 trades per metal)."),
    ("T6", "W8 with a faster band (inner x3 / outer x4, ATR 20) on 1h. About twice the trades; no longer matches the real indicator's settings. "
           "Its Day filter uses the real band (x6), as in the Pine scripts, so figures differ slightly from REPORT.md section 5."),
    ("T7", "W8 on the 30m chart (real band settings) + trend re-entry: while flat and the band and Day row still agree, "
           "re-enter when a bar closes beyond the previous 20 bars' high (long) or low (short)."),
    ("U1", "W8 rules (real band settings, Day filter, profit lock) on the 15m chart. ~6 trades/month per metal."),
    ("U9", "W8 rules on the 5m chart. ~16 trades/month per metal. Silver held in both years; Gold fell to PF 1.1 in 2026 "
           "and is fragile to slippage (research/ten_trades_costs.csv)."),
    ("Q1", "5m chart, real band. Take signals only when the 1h band AND the Day row agree; once +0.3R, lock the stop at +0.15R; "
           "while flat and all three still agree, re-enter on a close beyond the last 120 bars' (10 h) high/low. "
           "Silver: ~16 trades/month, ~76% wins, held at 20-tick slippage. Gold: win rate falls to ~59% at 20 ticks. "
           "The re-entry part was chosen after seeing results (research/fast_winrate_followup.py)."),
    ("Q2", "Q1 with the profit lock at +0.2R once +0.4R. Meant for Gold: its costs are ~2x Silver's as a share of R on 5m, "
           "so the smaller Q1 lock is eaten by fills (research/silver_vs_gold.py, research/gold_lock.py). Chosen after seeing results."),
    ("BS / BG", "Chosen by a 3,456-config search (research/optimize.py) using 2025 only at 20-tick fills; 2026 was held out. "
                "BS = Silver's pick, BG = Gold's pick; both are run on both metals here. Higher-timeframe filters use the "
                "real band (ATR 20, x6). See REPORT.md section 9."),
    ("Execution", "Signal on 1h close, fill at next bar's open. Stops fill at the stop price, or the minute's open if it gapped."),
    ("Costs", "Already inside 'Net points / lot': 0.02% of notional per round trip + 5 ticks slippage per side, "
              "plus one extra round trip for every roll a position is held through."),
    ("Monthly P&L", "Booked in the month a trade closes. Open positions are not marked to market at month end."),
    ("Caveats", "2025-26 was a strong trending period for both metals. Back-adjustment removes the overnight move on "
                "roll days. Past results do not guarantee future returns."),
    ("Blue / green / black", "Blue = values from the simulation, green = link to the Summary inputs, black = formulas."),
]
ws_notes["A1"] = "Method and assumptions"; ws_notes["A1"].font = title
for i, (k, v) in enumerate(notes, start=3):
    ws_notes.cell(i, 1, k).font = bold
    c = ws_notes.cell(i, 2, v); c.font = base; c.alignment = Alignment(wrap_text=True, vertical="top")
    ws_notes.row_dimensions[i].height = 30
ws_notes.column_dimensions["A"].width = 18
ws_notes.column_dimensions["B"].width = 120

out = "results/Swastika_Monthly_Backtest.xlsx"
wb.save(out)
print(out, n, "trades")
