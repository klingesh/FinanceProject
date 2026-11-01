"""Build AsianPaints_Comps_and_DCF.xlsx from the tidy inputs in data/ (openpyxl, live Excel formulas).

Run:   python build/build_model.py
Then:  python build/recalc_verify.py   (Excel recalculation via COM + checks)

Conventions: blue font = typed input, black = formula, green = link to another sheet,
light-yellow fill = judgment assumption (with a one-line reason next to it). Rs crore unless stated.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference, ScatterChart, Series
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "AsianPaints_Comps_and_DCF.xlsx"
RS = "\u20b9"  # rupee sign

# ----------------------------------------------------------------------------------------------
# Styles and helpers
# ----------------------------------------------------------------------------------------------
def _font(color: str = "000000", bold: bool = False, italic: bool = False, size: int = 10) -> Font:
    return Font(name="Calibri", size=size, color=color, bold=bold, italic=italic)


STY = {
    "input": _font("0000FF"), "calc": _font("000000"), "link": _font("008000"), "label": _font("000000"),
    "bold": _font("000000", bold=True), "note": _font("595959", italic=True, size=9),
    "title": _font("1F4E78", bold=True, size=14), "hdr": _font("FFFFFF", bold=True),
    "sub": _font("1F4E78", bold=True, size=11),
}
FILL_HDR = PatternFill("solid", fgColor="1F4E78")
FILL_SUB = PatternFill("solid", fgColor="DDEBF7")
FILL_JUDG = PatternFill("solid", fgColor="FFF2CC")
FILL_TGT = PatternFill("solid", fgColor="E2EFDA")
FILL_PASS = PatternFill("solid", fgColor="C6EFCE")
FILL_FAIL = PatternFill("solid", fgColor="FFC7CE")
FMT = {"cr": "#,##0", "cr1": "#,##0.0", "cr2": "#,##0.00", "pct": "0.0%", "pct2": "0.00%",
       "pp": '+0.0%;-0.0%;0.0%', "x": '0.0"x"', "x2": '0.00"x"', "rs": "#,##0.00", "rs0": "#,##0",
       "eps": "0.00", "date": "dd-mmm-yyyy", "beta": "0.000", "n": "0", "f4": "0.0000",
       "f3": "0.000", "chg": '+0.0%;-0.0%;0.0%'}


def put(ws, ref: str, value, sty: str = "calc", fmt: str | None = None, fill=None, bold: bool = False,
        align: str | None = None, wrap: bool = False):
    """Write a value or formula with the house style."""
    c = ws[ref]
    c.value = value
    f = STY[sty]
    if bold:
        f = Font(name=f.name, size=f.size, color=f.color, bold=True, italic=f.italic)
    c.font = f
    if fmt:
        c.number_format = FMT.get(fmt, fmt)
    if fill is not None:
        c.fill = fill
    if align or wrap:
        c.alignment = Alignment(horizontal=align, wrap_text=wrap, vertical="top" if wrap else None)
    return c


def header(ws, row: int, labels: list[str], start_col: int = 1, height: float = 30) -> None:
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=lab)
        c.font = STY["hdr"]
        c.fill = FILL_HDR
        c.alignment = Alignment(horizontal="left" if i == 0 else "center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = height


def sub(ws, row: int, text: str, ncols: int) -> None:
    for col in range(1, ncols + 1):
        ws.cell(row=row, column=col).fill = FILL_SUB
    c = ws.cell(row=row, column=1, value=text)
    c.font = STY["sub"]


def title(ws, text: str, note: str) -> None:
    put(ws, "A1", text, "title")
    put(ws, "A2", note, "note")


def widths(ws, spec: dict[str, float]) -> None:
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def pass_fail_format(ws, rng: str) -> None:
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"PASS"'], fill=FILL_PASS))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"FAIL"'], fill=FILL_FAIL))


# ----------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------
peers = pd.read_csv(DATA / "peer_inputs.csv").set_index("symbol")
fil = pd.read_csv(DATA / "asian_paints_q2fy27_filing.csv")
hist = pd.read_csv(DATA / "asian_paints_history.csv").set_index("period")
betas = pd.read_csv(DATA / "beta_summary.csv")
pts = pd.read_csv(DATA / "price_targets.csv").set_index("symbol")


def filing(item: str, period_prefix: str) -> float:
    """One value from the Asian Paints Q2 FY27 filing extract (Rs crore unless the item says otherwise)."""
    m = fil[(fil["item"] == item) & (fil["period"].str.startswith(period_prefix))]
    if len(m) != 1:
        raise KeyError(f"{item} / {period_prefix}: {len(m)} matches")
    return float(m["value_rs_crore"].iloc[0])


def beta(sym: str, window: str, col: str = "beta") -> float:
    m = betas[(betas["symbol"] == sym) & (betas["window"] == window)]
    return float(m[col].iloc[0])


COMP = ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "JSWDULUX", "INDIGOPNTS"]
PEERS = COMP[1:]
NAME = {"ASIANPAINT": "Asian Paints", "BERGEPAINT": "Berger Paints", "KANSAINER": "Kansai Nerolac",
        "JSWDULUX": "JSW Dulux", "INDIGOPNTS": "Indigo Paints"}

wb = Workbook()
ws_cover = wb.active
ws_cover.title = "Cover"
ws_pd = wb.create_sheet("Peer_Data")
ws_c = wb.create_sheet("Comps")
ws_da = wb.create_sheet("DCF_Assumptions")
ws_w = wb.create_sheet("WACC")
ws_d = wb.create_sheet("DCF")
ws_s = wb.create_sheet("Sensitivity")
ws_f = wb.create_sheet("Football_Field")
ws_k = wb.create_sheet("Checks")

# ----------------------------------------------------------------------------------------------
# Peer_Data: one row per input field, one column per company (all blue inputs)
# ----------------------------------------------------------------------------------------------
PCOL = {s: get_column_letter(2 + i) for i, s in enumerate(COMP)}   # B..F
PD: dict[str, int] = {}


def pdref(key: str, sym: str) -> str:
    return f"Peer_Data!${PCOL[sym]}${PD[key]}"


def ttm_label(x: str) -> str:
    return str(x).replace(" ", "-")


SA = "stockanalysis.com (S&P Global Market Intelligence)"
PD_FIELDS = [
    ("symbol", "NSE symbol", "", "NSE", None, lambda r, s: s),
    ("role", "Role", "", "Target = company valued; peers = listed Indian decorative-paint companies", None,
     lambda r, s: r["role"]),
    ("basis", "Financial statements", "", "Screener.in consolidated pages (Indigo's consolidated history starts FY2023)",
     None, lambda r, s: "Consolidated"),
    ("price", "Share price, 30-Oct-2026 close", RS, "Yahoo Finance daily close (yfinance, auto_adjust=False)",
     "rs", lambda r, s: r["price_rs"]),
    ("shares", "Shares outstanding (diluted)", "crore", SA + " statistics: 'Current Share Class'", "f4",
     lambda r, s: r["shares_crore"]),
    ("high52", "52-week high (intraday)", RS, "Yahoo Finance, 31-Oct-2025 to 30-Oct-2026", "rs",
     lambda r, s: r["high_52w_rs"]),
    ("low52", "52-week low (intraday)", RS, "Yahoo Finance, 31-Oct-2025 to 30-Oct-2026", "rs",
     lambda r, s: r["low_52w_rs"]),
    ("ttm_end", "Latest quarter in TTM", "", "Sep-2026 if Q2 FY27 results were filed by 30-Oct-2026, else Jun-2026",
     None, lambda r, s: ttm_label(r["ttm_end"])),
    ("results_date", "Filing date of that quarter's results", "date", "NSE corporate announcements", "date",
     lambda r, s: dt.datetime.fromisoformat(r["latest_results_date"])),
    ("ttm_revenue", "TTM revenue from operations", RS + " cr", "Screener.in quarterly results, sum of last 4 quarters",
     "cr", lambda r, s: r["ttm_revenue"]),
    ("ttm_ebitda", "TTM EBITDA (operating profit before other income)", RS + " cr",
     "Screener.in: sales minus operating expenses (Ind AS 116: lease rent is not an operating expense)", "cr",
     lambda r, s: r["ttm_ebitda"]),
    ("ttm_dep", "TTM depreciation and amortisation", RS + " cr", "Screener.in quarterly results", "cr",
     lambda r, s: r["ttm_depreciation"]),
    ("ttm_oi", "TTM other income (memo, not in EBITDA)", RS + " cr", "Screener.in quarterly results", "cr",
     lambda r, s: r["ttm_other_income"]),
    ("ttm_pat_rep", "TTM net profit as reported (memo)", RS + " cr", "Screener.in quarterly results", "cr",
     lambda r, s: r["ttm_pat_reported"]),
    ("ttm_exc", "TTM exceptional items after tax (memo)", RS + " cr", "Screener.in schedule 'Exceptional items AT'",
     "cr", lambda r, s: r["ttm_exceptional_after_tax"]),
    ("ttm_pat_pe", "TTM PAT for P/E (owners, excl. exceptional items)", RS + " cr",
     "Screener.in schedule 'Profit for PE'", "cr", lambda r, s: r["ttm_pat_for_pe"]),
    ("bs_date", "Balance-sheet date for EV items", "", "Latest published balance sheet (half-yearly in India)", None,
     lambda r, s: r["bs_date"]),
    ("borrow", "Borrowings excl. lease liabilities", RS + " cr", "Screener.in schedule 'Borrowings' (long + short term)",
     "cr", lambda r, s: round(r["borrowings_incl_leases"] - r["lease_liabilities"], 2)),
    ("lease", "Lease liabilities", RS + " cr", "Screener.in schedule 'Borrowings': Lease Liabilities", "cr",
     lambda r, s: r["lease_liabilities"]),
    ("nci", "Minority (non-controlling) interest", RS + " cr",
     "Screener.in schedule 'Other Liabilities' (Indigo: see note 5 below)", "cr", lambda r, s: r["minority_interest"]),
    ("cash", "Cash and equivalents incl. other bank balances", RS + " cr", SA + " balance sheet: 'Cash & Equivalents'",
     "cr", lambda r, s: r["cash_and_equivalents"]),
    ("liquid", "Liquid investments (current investments)", RS + " cr",
     SA + ": 'Short-Term Investments' + 'Trading Asset Securities'", "cr", lambda r, s: r["liquid_investments"]),
    ("ncinv", "Non-current investments incl. associates (memo, not subtracted)", RS + " cr",
     SA + ": 'Long-Term Investments'", "cr", lambda r, s: r["noncurrent_investments_memo"]),
    ("rev23", "Revenue FY2023 (year to Mar-2023)", RS + " cr", "Screener.in annual P&L", "cr",
     lambda r, s: r["revenue_fy2023"]),
    ("rev26", "Revenue FY2026 (year to Mar-2026)", RS + " cr", "Screener.in annual P&L", "cr",
     lambda r, s: r["revenue_fy2026"]),
    ("roce", "ROCE FY2026", "%", "Screener.in top ratios", "pct", lambda r, s: r["roce_fy2026_pct"] / 100),
    ("roe", "ROE FY2026", "%", "Screener.in top ratios", "pct", lambda r, s: r["roe_fy2026_pct"] / 100),
    ("c_rev27", "Consensus revenue FY2027E", RS + " cr", SA + " forecast page, downloaded 1-Nov-2026", "cr",
     lambda r, s: r["fy27e_revenue"]),
    ("c_rev28", "Consensus revenue FY2028E", RS + " cr", SA + " forecast page", "cr", lambda r, s: r["fy28e_revenue"]),
    ("c_ebit27", "Consensus operating income (EBIT) FY2027E", RS + " cr", SA + " forecast page", "cr",
     lambda r, s: r["fy27e_ebit"]),
    ("c_eps27", "Consensus EPS FY2027E", RS, SA + " forecast page (JSW Dulux divided by 10 for the 1:10 split)", "eps",
     lambda r, s: r["fy27e_eps_rs"]),
    ("c_eps28", "Consensus EPS FY2028E", RS, SA + " forecast page (JSW Dulux divided by 10)", "eps",
     lambda r, s: r["fy28e_eps_rs"]),
    ("c_n", "Analysts in the FY2027E estimate", "count", SA + " forecast page", "n", lambda r, s: r["fy27e_analysts"]),
    ("pt_low", "Analyst price target: low", RS, SA + " forecast page", "rs", lambda r, s: pts.loc[s, "pt_low"]),
    ("pt_med", "Analyst price target: median", RS, SA + " forecast page", "rs", lambda r, s: pts.loc[s, "pt_median"]),
    ("pt_avg", "Analyst price target: average", RS, SA + " forecast page", "rs", lambda r, s: pts.loc[s, "pt_average"]),
    ("pt_high", "Analyst price target: high", RS, SA + " forecast page", "rs", lambda r, s: pts.loc[s, "pt_high"]),
    ("pt_n", "Analysts with a price target", "count", SA + " statistics page", "n", lambda r, s: pts.loc[s, "pt_analysts"]),
    ("scr_mcap", "Screener market cap (cross-check only)", RS + " cr", "Screener.in top ratios (30-Oct-2026 close)",
     "cr", lambda r, s: r["screener_market_cap"]),
    ("scr_pe", "Screener P/E (cross-check only)", "x", "Screener.in top ratios", "x", lambda r, s: r["screener_pe"]),
]

ws = ws_pd
title(ws, "Peer data: Asian Paints and four listed paint peers (inputs)",
      f"All cells in columns B-F are typed inputs (blue) from the files in source_data/, prepared by "
      f"build/prepare_data.py. {RS} crore unless stated. Prices are 30-Oct-2026 closes.")
header(ws, 4, ["Input"] + [NAME[s] for s in COMP] + ["Units", "Source / note"])
row = 5
for key, label, unit, source, fmt, getter in PD_FIELDS:
    PD[key] = row
    put(ws, f"A{row}", label, "label")
    for s in COMP:
        val = getter(peers.loc[s], s)
        if isinstance(val, float) and pd.isna(val):
            val = None
        elif hasattr(val, "item") and not isinstance(val, (str, dt.datetime)):
            val = val.item()
        c = put(ws, f"{PCOL[s]}{row}", val, "input", fmt, align="right")
        if s == "ASIANPAINT":
            c.fill = FILL_TGT
    put(ws, f"G{row}", unit, "label")
    put(ws, f"H{row}", source, "note")
    row += 1

row += 1
put(ws, f"A{row}", "Notes", "bold")
PD_NOTES = [
    "1. TTM timing. Asian Paints filed Q2 FY27 on 29-Oct-2026 (14:04 IST, during market hours) and Indigo Paints on "
    "30-Oct-2026 (17:41 IST, after the close), so both TTMs end Sep-2026.",
    "   Berger (board meeting 5-Nov-2026), Kansai Nerolac (4-Nov-2026) and JSW Dulux (investor call 4-Nov-2026) had not "
    "reported, so their TTMs end Jun-2026 and their balance sheets are at 31-Mar-2026.",
    "2. Indigo's 30-Oct-2026 price does not yet reflect its weak Q2 FY27 (PAT Rs 13 cr vs Rs 25 cr a year earlier), "
    "which was published after the close.",
    "3. JSW Dulux (formerly Akzo Nobel India, renamed 2026): 1:10 share split, record date 22-Oct-2026. Prices and the "
    "share count are post-split; S&P consensus EPS is still pre-split and is divided by 10.",
    "   Its TTM net profit includes a Rs 1,578 cr after-tax exceptional gain in the Sep-2025 quarter (other income "
    "Rs 1,882 cr); the P/E uses profit excluding it (Rs 384 cr).",
    "4. Kansai Nerolac reports a negative minority interest (-Rs 25 cr, loss-making subsidiary). It is used as reported.",
    "5. Indigo Paints has no minority-interest line in equity. The 49% of Apple Chemie it does not own is carried as a "
    "financial liability (Rs 61.72 cr = consolidated minus standalone",
    "   non-current other financial liabilities, Q2 FY27 results p.6). That amount is used as the minority-interest "
    "equivalent.",
    "6. Asian Paints figures above come from Screener/S&P like the peers; the Checks sheet reconciles them with the "
    "company filing (differences below 0.1%). The DCF uses the filing figures.",
    "7. EBITDA follows Ind AS 116 (lease rent is replaced by depreciation and interest), so lease liabilities are "
    "counted as debt in EV.",
]
for i, note in enumerate(PD_NOTES, start=1):
    put(ws, f"A{row + i}", note, "note")
widths(ws, {"A": 52, "B": 14, "C": 14, "D": 14, "E": 14, "F": 14, "G": 8, "H": 80})
ws.freeze_panes = "B5"

# ----------------------------------------------------------------------------------------------
# Comps: trading multiples, peer statistics, implied values, drop-one-peer sensitivity
# ----------------------------------------------------------------------------------------------
ws = ws_c
CROW = {s: 5 + i for i, s in enumerate(COMP)}   # AP row 5, peers rows 6-9
P1, P4 = 6, 9                                   # peer block
title(ws, f"Trading comparables: Indian decorative-paint companies ({RS} crore unless stated)",
      "Black = formulas on the Peer_Data inputs. EV = market cap + borrowings + lease liabilities + minority interest "
      "- cash - liquid (current) investments. TTM = trailing twelve months to the quarter in column B.")
COLS = ["Company", "TTM to", f"Price ({RS})", "Shares (cr)", "Market cap", "Debt incl. leases", "Minority interest",
        "Cash + liquid investments", "Enterprise value (EV)", "TTM revenue", "TTM EBITDA", "TTM PAT (for P/E)",
        f"TTM EPS ({RS})", "EBITDA margin", "Revenue CAGR FY23-26", "ROCE FY26", "ROE FY26", "EV/EBITDA TTM",
        "P/E TTM", "EV/Sales TTM", "FY27E EBITDA (consensus EBIT + TTM D&A)", "EV/EBITDA FY27E", "P/E FY27E",
        "Memo: EV/EBITDA TTM if non-current investments also deducted", "Flags"]
header(ws, 4, COLS, height=58)
FLAGS = {
    "ASIANPAINT": "Target. TTM and balance sheet to Sep-2026 (results filed 29-Oct-2026).",
    "BERGEPAINT": "Q2 FY27 results due 5-Nov-2026; balance sheet 31-Mar-2026.",
    "KANSAINER": "Q2 FY27 results due 4-Nov-2026; negative minority interest as reported; large treasury book.",
    "JSWDULUX": "TTM PAT excludes a Rs 1,578 cr after-tax exceptional gain; 1:10 split on 22-Oct-2026; 2 analysts.",
    "INDIGOPNTS": "Q2 FY27 filed 30-Oct-2026 after the close, so the price does not reflect it; smallest peer.",
}
for s in COMP:
    r = CROW[s]
    fill = FILL_TGT if s == "ASIANPAINT" else None
    put(ws, f"A{r}", NAME[s], "bold" if s == "ASIANPAINT" else "label", fill=fill)
    put(ws, f"B{r}", f"={pdref('ttm_end', s)}", "link", fill=fill, align="center")
    put(ws, f"C{r}", f"={pdref('price', s)}", "link", "rs", fill)
    put(ws, f"D{r}", f"={pdref('shares', s)}", "link", "f3", fill)
    put(ws, f"E{r}", f"=C{r}*D{r}", "calc", "cr", fill)
    put(ws, f"F{r}", f"={pdref('borrow', s)}+{pdref('lease', s)}", "link", "cr", fill)
    put(ws, f"G{r}", f"={pdref('nci', s)}", "link", "cr", fill)
    put(ws, f"H{r}", f"={pdref('cash', s)}+{pdref('liquid', s)}", "link", "cr", fill)
    put(ws, f"I{r}", f"=E{r}+F{r}+G{r}-H{r}", "calc", "cr", fill)
    put(ws, f"J{r}", f"={pdref('ttm_revenue', s)}", "link", "cr", fill)
    put(ws, f"K{r}", f"={pdref('ttm_ebitda', s)}", "link", "cr", fill)
    put(ws, f"L{r}", f"={pdref('ttm_pat_pe', s)}", "link", "cr", fill)
    put(ws, f"M{r}", f"=L{r}/D{r}", "calc", "eps", fill)
    put(ws, f"N{r}", f"=K{r}/J{r}", "calc", "pct", fill)
    put(ws, f"O{r}", f"=({pdref('rev26', s)}/{pdref('rev23', s)})^(1/3)-1", "calc", "pct", fill)
    put(ws, f"P{r}", f"={pdref('roce', s)}", "link", "pct", fill)
    put(ws, f"Q{r}", f"={pdref('roe', s)}", "link", "pct", fill)
    put(ws, f"R{r}", f"=I{r}/K{r}", "calc", "x", fill)
    put(ws, f"S{r}", f"=E{r}/L{r}", "calc", "x", fill)
    put(ws, f"T{r}", f"=I{r}/J{r}", "calc", "x2", fill)
    put(ws, f"U{r}", f"={pdref('c_ebit27', s)}+{pdref('ttm_dep', s)}", "calc", "cr", fill)
    put(ws, f"V{r}", f"=I{r}/U{r}", "calc", "x", fill)
    put(ws, f"W{r}", f"=C{r}/{pdref('c_eps27', s)}", "calc", "x", fill)
    put(ws, f"X{r}", f"=(I{r}-{pdref('ncinv', s)})/K{r}", "calc", "x", fill)
    flag = FLAGS[s]
    if s == "ASIANPAINT":
        put(ws, f"Y{r}", flag, "note", fill=fill)
    else:
        put(ws, f"Y{r}", f'=IF(B{r}<>$B$5,"TTM one quarter older than Asian Paints. ","")&"{flag}"', "calc")

STAT_COLS = ["N", "O", "P", "Q", "R", "S", "T", "V", "W", "X"]
STAT_FMT = {"N": "pct", "O": "pct", "P": "pct", "Q": "pct", "R": "x", "S": "x", "T": "x2", "V": "x", "W": "x", "X": "x"}
sub(ws, 11, "Peer statistics (4 peers; Asian Paints excluded)", 25)
STATS = [(12, "Minimum", "MIN({r})"), (13, "25th percentile", "QUARTILE({r},1)"), (14, "Median", "MEDIAN({r})"),
         (15, "75th percentile", "QUARTILE({r},3)"), (16, "Maximum", "MAX({r})")]
for r, label, f in STATS:
    put(ws, f"A{r}", label, "label")
    for col in STAT_COLS:
        put(ws, f"{col}{r}", "=" + f.format(r=f"{col}{P1}:{col}{P4}"), "calc", STAT_FMT[col])
put(ws, "A17", "Asian Paints premium / (discount) to the peer median", "bold")
for col in STAT_COLS:
    if col in ("N", "O", "P", "Q"):
        put(ws, f"{col}17", f"={col}5-{col}14", "calc", "pp")
    else:
        put(ws, f"{col}17", f"={col}5/{col}14-1", "calc", "chg")
put(ws, "Y17", "Margin, growth, ROCE, ROE: difference in percentage points. Multiples: ratio to the median minus 1.",
    "note")

sub(ws, 19, f"Implied Asian Paints value per share ({RS}) from peer multiples", 25)
header(ws, 20, ["Multiple x Asian Paints metric", "Asian Paints metric", "At peer minimum", "At 25th percentile",
                "At median", "At 75th percentile", "At peer maximum", "Median vs price", "Asian Paints own multiple",
                "Basis"], height=32)
# (row, label, metric formula, stat column, EV-based?, metric format, basis note)
IMPLIED = [
    (21, f"EV/EBITDA TTM x TTM EBITDA ({RS} cr)", "=$K$5", "R", True, "cr", "TTM to Sep-2026"),
    (22, f"P/E TTM x TTM EPS ({RS})", "=$M$5", "S", False, "eps", "TTM to Sep-2026"),
    (23, f"EV/Sales TTM x TTM revenue ({RS} cr)", "=$J$5", "T", True, "cr", "TTM to Sep-2026"),
    (24, f"EV/EBITDA FY27E x FY27E EBITDA ({RS} cr)", "=$U$5", "V", True, "cr", "S&P consensus, FY ending Mar-2027"),
    (25, f"P/E FY27E x FY27E EPS ({RS})", f"={pdref('c_eps27', 'ASIANPAINT')}", "W", False, "eps",
     "S&P consensus, FY ending Mar-2027"),
]
IMPL_ROW = {}
for r, label, metric, scol, ev_based, mfmt, basis in IMPLIED:
    IMPL_ROW[scol] = r
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", metric, "link" if "Peer_Data" in metric else "calc", mfmt)
    for col, srow in zip("CDEFG", (12, 13, 14, 15, 16)):
        if ev_based:
            fml = f"=($B{r}*{scol}${srow}-$F$5-$G$5+$H$5)/$D$5"
        else:
            fml = f"=$B{r}*{scol}${srow}"
        put(ws, f"{col}{r}", fml, "calc", "rs0")
    put(ws, f"H{r}", f"=E{r}/$C$5-1", "calc", "chg")
    put(ws, f"I{r}", f"={scol}5", "calc", "x2" if scol == "T" else "x")
    put(ws, f"J{r}", basis, "note")
put(ws, "A26", "EV-based rows: (metric x multiple - Asian Paints debt incl. leases - minority interest + cash and liquid "
               "investments) / shares. P/E rows: EPS x multiple.", "note")

sub(ws, 28, "Drop-one-peer sensitivity: median of the remaining three peers", 25)
header(ws, 29, ["Peer dropped", "Median EV/EBITDA TTM", "Median P/E TTM", "Median EV/Sales TTM",
                f"Implied {RS}/share: EV/EBITDA", f"Implied {RS}/share: P/E", f"Implied {RS}/share: EV/Sales"], height=32)
DROP_ROWS = {"none": 30}
put(ws, "A30", "None (all four peers)", "bold")
for col, mcol in zip("BCD", "RST"):
    put(ws, f"{col}30", f"=MEDIAN({mcol}{P1}:{mcol}{P4})", "calc", "x2" if mcol == "T" else "x")
for i, s in enumerate(PEERS):
    r = 31 + i
    DROP_ROWS[s] = r
    put(ws, f"A{r}", f"Drop {NAME[s]}", "label")
    keep = [CROW[p] for p in PEERS if p != s]
    for col, mcol in zip("BCD", "RST"):
        cells = ",".join(f"{mcol}{k}" for k in keep)
        put(ws, f"{col}{r}", f"=MEDIAN({cells})", "calc", "x2" if mcol == "T" else "x")
for r in range(30, 35):
    put(ws, f"E{r}", f"=($K$5*B{r}-$F$5-$G$5+$H$5)/$D$5", "calc", "rs0")
    put(ws, f"F{r}", f"=$M$5*C{r}", "calc", "rs0")
    put(ws, f"G{r}", f"=($J$5*D{r}-$F$5-$G$5+$H$5)/$D$5", "calc", "rs0")
put(ws, "A35", "Lowest drop-one result", "label")
put(ws, "A36", "Highest drop-one result", "label")
put(ws, "A37", "Largest change vs the four-peer result", "bold")
for col in "BCDEFG":
    fmt = "x2" if col == "D" else ("x" if col in "BC" else "rs0")
    put(ws, f"{col}35", f"=MIN({col}31:{col}34)", "calc", fmt)
    put(ws, f"{col}36", f"=MAX({col}31:{col}34)", "calc", fmt)
    put(ws, f"{col}37", f"=MAX({col}36/{col}30-1,1-{col}35/{col}30)", "calc", "pct")

sub(ws, 39, "What is in EV, and why", 25)
COMPS_NOTES = [
    "Added: borrowings (long and short term) and lease liabilities. EBITDA is after Ind AS 116, so lease rent sits below "
    "EBITDA and the lease liability must be in EV to match.",
    "Added: minority interest at book value, because EBITDA includes 100% of subsidiaries that the company does not fully own.",
    "Subtracted: cash, bank balances and current investments. For Asian Paints that is Rs 612.6 cr cash plus Rs 5,512 cr "
    "of current investments, mostly liquid mutual funds",
    "   that the cash-flow statement itself counts as cash equivalents (Rs 5,508.9 cr). Berger (Rs 1,073 cr) and Kansai "
    "(Rs 2,388 cr) hold similar treasury books.",
    "Not subtracted: non-current investments (Asian Paints Rs 877 cr, of which Rs 693 cr is equity-accounted associates such "
    "as PPG Asian Paints). They are strategic",
    "   holdings, not spare cash. Column X shows the effect of deducting them too: about 0.1x on Asian Paints' EV/EBITDA.",
    "Timing: Berger, Kansai and JSW Dulux are one quarter behind (TTM to Jun-2026). Their Q2 FY27 results were due on "
    "4-5 Nov-2026, after the price date.",
    "With only four peers, one company moves the median a lot; the drop-one table above shows how much.",
]
for i, note in enumerate(COMPS_NOTES):
    put(ws, f"A{40 + i}", note, "note")
widths(ws, {"A": 40, "B": 10, "C": 10, "D": 9, "E": 11, "F": 10, "G": 10, "H": 11, "I": 12, "J": 10, "K": 10,
            "L": 10, "M": 9, "N": 9, "O": 10, "P": 8, "Q": 8, "R": 10, "S": 8, "T": 9, "U": 13, "V": 10, "W": 9,
            "X": 15, "Y": 95})
ws.freeze_panes = "C5"

# ----------------------------------------------------------------------------------------------
# DCF_Assumptions: history (inputs), balance sheet at the valuation date, forecast drivers
# ----------------------------------------------------------------------------------------------
ws = ws_da
DA = "DCF_Assumptions!"
title(ws, f"DCF assumptions: Asian Paints (consolidated, {RS} crore unless stated)",
      "Blue = inputs from the company filing (Q2 FY27 results of 29-Oct-2026) and Screener.in. Yellow = my judgment, "
      "with the reason in the last column. Black = formulas.")
sub(ws, 5, "A. Historical financials (inputs)", 10)
header(ws, 6, [f"{RS} crore", "FY2022A", "FY2023A", "FY2024A", "FY2025A", "FY2026A", "H1 FY2026A",
               "H2 FY2026A (derived)", "H1 FY2027A", "Source"])
HCOL = {"FY2022A": "B", "FY2023A": "C", "FY2024A": "D", "FY2025A": "E", "FY2026A": "F"}
HIST_ITEMS = [(7, "Revenue from operations", "revenue"), (8, "EBITDA (PBDIT before other income)", "ebitda"),
              (9, "Depreciation and amortisation", "depreciation"),
              (10, "Capex (purchase of PPE and intangibles)", "capex"),
              (11, "Lease principal repaid (proxy for new leases)", "lease_principal_repaid")]
for r, label, col in HIST_ITEMS:
    put(ws, f"A{r}", label, "label")
    for per, c in HCOL.items():
        put(ws, f"{c}{r}", float(hist.loc[per, col]), "input", "cr")
    if col != "lease_principal_repaid":
        put(ws, f"G{r}", float(hist.loc["H1 FY2026A", col]), "input", "cr")
        put(ws, f"H{r}", f"=F{r}-G{r}", "calc", "cr")
        put(ws, f"I{r}", float(hist.loc["H1 FY2027A", col]), "input", "cr")
put(ws, "J7", "FY22-FY25 Screener.in; FY26, H1 FY26 and H1 FY27 company filing (consolidated P&L, p.12)", "note")
put(ws, "J10", "Screener.in cash-flow schedule (FY); company cash-flow statement for H1 (p.14)", "note")
put(ws, "J11", "Screener.in financing schedule 'Financial liabilities' (S&P 'lease payments' FY26: Rs 339.8 cr)",
    "note")
BS_ITEMS = [(12, "Inventories (period end)", "inventories"), (13, "Trade receivables (period end)", "trade_receivables"),
            (14, "Trade payables (period end)", "trade_payables")]
for r, label, item in BS_ITEMS:
    put(ws, f"A{r}", label, "label")
    for per, c in list(HCOL.items())[:4]:
        put(ws, f"{c}{r}", float(hist.loc[per, item]), "input", "cr")
    put(ws, f"F{r}", filing(item, "31-Mar-2026"), "input", "cr")
    put(ws, f"I{r}", filing(item, "30-Sep-2026"), "input", "cr")
put(ws, "J12", "FY22-FY25 Screener.in schedules; 31-Mar-2026 and 30-Sep-2026 company balance sheet (p.13)", "note")
put(ws, "A15", "Trade working capital (inventories + receivables - payables)", "bold")
for c in "BCDEFI":
    put(ws, f"{c}15", f"={c}12+{c}13-{c}14", "calc", "cr")
put(ws, "A16", "Revenue growth (H1 FY2027A: vs H1 FY2026A)", "label")
for prev, c in zip("BCDE", "CDEF"):
    put(ws, f"{c}16", f"={c}7/{prev}7-1", "calc", "pct")
put(ws, "I16", "=I7/G7-1", "calc", "pct")
for r, label, num in [(17, "EBITDA margin", 8), (18, "D&A % of revenue", 9), (19, "Capex % of revenue", 10)]:
    put(ws, f"A{r}", label, "label")
    for c in "BCDEFGHI":
        put(ws, f"{c}{r}", f"={c}{num}/{c}7", "calc", "pct")
put(ws, "A20", "Lease principal repaid % of revenue", "label")
for c in "BCDEF":
    put(ws, f"{c}20", f"={c}11/{c}7", "calc", "pct")
put(ws, "A21", "Trade working capital % of revenue (30-Sep-2026: % of TTM revenue)", "label")
for c in "BCDEF":
    put(ws, f"{c}21", f"={c}15/{c}7", "calc", "pct")
put(ws, "I21", "=I15/(F7+I7-G7)", "calc", "pct")

sub(ws, 23, "B. P&L below EBITDA, FY2026A and H1 FY2027A (company filing, consolidated P&L p.12)", 10)
header(ws, 24, ["", "", "", "", "", "FY2026A", "", "", "H1 FY2027A", "Note"])
PL_ITEMS = [(25, "Other income", "other_income", "Mostly treasury income; not in EBITDA or FCFF"),
            (26, "Finance costs (incl. interest on leases)", "finance_costs", ""),
            (27, "Share of profit of associates", "share_of_profit_of_associates", "PPG Asian Paints and others"),
            (28, "Exceptional items (loss)", "exceptional_items_loss", "None in H1 FY2027"),
            (29, "Profit before tax (reported)", "profit_before_tax", ""),
            (30, "Tax expense", "tax_expense", ""),
            (31, "PAT attributable to owners", "pat_attributable_to_owners", "")]
for r, label, item, note in PL_ITEMS:
    put(ws, f"A{r}", label, "label")
    put(ws, f"F{r}", filing(item, "FY26"), "input", "cr2")
    put(ws, f"I{r}", 0.0 if item == "exceptional_items_loss" else filing(item, "H1 FY27"), "input", "cr2")
    put(ws, f"J{r}", note, "note")
put(ws, "A32", f"Diluted EPS as reported ({RS})", "label")
put(ws, "F32", filing("diluted_eps_rs", "FY26"), "input", "eps")

sub(ws, 34, "C. Balance sheet at 30-Sep-2026, the valuation date (company filing, consolidated balance sheet p.13)", 10)
BS_VAL = [(35, "Borrowings, non-current", "borrowings_noncurrent"), (36, "Borrowings, current", "borrowings_current"),
          (37, "Lease liabilities, non-current", "lease_liabilities_noncurrent"),
          (38, "Lease liabilities, current", "lease_liabilities_current"),
          (39, "Non-controlling interests (book value)", "non_controlling_interests"),
          (40, "Cash and cash equivalents", "cash_and_cash_equivalents"),
          (41, "Other bank balances (term deposits)", "other_balances_with_banks"),
          (42, "Current investments (mostly liquid mutual funds)", "current_investments"),
          (43, "Non-current investments (financial assets)", "noncurrent_investments"),
          (44, "Investments in associates (equity-accounted)", "investments_in_associates")]
for r, label, item in BS_VAL:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", filing(item, "30-Sep-2026"), "input", "cr2")
put(ws, "C42", "Rs 5,508.90 cr of these are liquid funds that the cash-flow statement counts as cash equivalents (p.15)",
    "note")
put(ws, "A45", "Total debt incl. lease liabilities", "bold")
put(ws, "B45", "=SUM(B35:B38)", "calc", "cr2")
put(ws, "A46", "Debt incl. leases, 31-Mar-2025 (for the cost-of-debt memo)", "label")
put(ws, "B46", float(hist.loc["FY2025A", "borrowings_incl_leases"]), "input", "cr")
put(ws, "A47", "Debt incl. leases, 31-Mar-2026", "label")
put(ws, "B47", float(hist.loc["FY2026A", "borrowings_incl_leases"]), "input", "cr")
put(ws, "C46", "Screener.in balance sheet", "note")

sub(ws, 49, "D. Forecast drivers (yellow = judgment)", 10)
header(ws, 50, ["Driver", "FY2026A", "H1 FY2027A", "H2 FY2027E", "FY2027E (implied)", "FY2028E", "FY2029E",
                "FY2030E", "FY2031E", "Reason (one line)"])
DRIVERS = [
    # row, label, B (FY26A), C (H1 FY27A), D (H2 FY27E input), E (FY27E), F..I inputs, reason
    (51, "Revenue growth (H2: vs H2 FY2026A)", "=F16", "=I16", 0.15, "=DCF!E5", [0.08, 0.085, 0.085, 0.08],
     "H1 FY27 +17.4% (Q2 decorative volume +6.4%, price rises ~12%) and more staggered price rises under way "
     "(press release); 15% allows for softer demand and Birla Opus. Consensus FY27E +17.1%, FY28E +7.6%."),
    (52, "EBITDA margin", "=F17", "=I17", 0.17, "=DCF!E7", [0.185, 0.19, 0.19, 0.19],
     "Q2 FY27 15.6% (-202 bp) on raw-material inflation; H2 is seasonally stronger (H2 FY26 19.7%), so 17.0%. "
     "FY28E = FY22-26 average 18.5%; 19.0% later as the VAE/VAM plant lowers costs."),
    (53, "D&A % of revenue", "=F18", "=I18", 0.031, "=DCF!E9", [0.032] * 4,
     "FY26 3.5%, H1 FY27 3.0% of price-inflated revenue; the new VAE plant (Phase 1 gross block ~Rs 1,060 cr) "
     "adds depreciation."),
    (54, "Capex % of revenue", "=F19", "=I19", 0.035, "=DCF!E16", [0.04, 0.038, 0.035, 0.035],
     "FY23-FY26 average 5.2%; VAE/VAM project Rs 3,250 cr in total (Phase 1 ~Rs 1,060 cr done), Phase 2 mostly in "
     "FY28-FY29; 3.5% after that."),
    (55, "New leases (right-of-use additions) % of revenue", "=F20", None, 0.01, "=DCF!E18", [0.01] * 4,
     "Lease principal repaid in FY26 was Rs 340 cr = 1.0% of revenue; new leases assumed to replace them, "
     "so the lease book stays steady relative to sales."),
    (56, "Trade working capital % of revenue (year end)", "=F21", "=I21", None, 0.19, [0.19] * 4,
     "FY22-FY25 19.7-21.2%, FY26 17.8%, 30-Sep-2026 20.8% of TTM revenue (inflation-led inventory build); 19% sits "
     "between FY26 and the 5-year average."),
    (57, "Other income % of revenue (EPS only)", "=F25/F7", "=I25/I7", 0.02, "=DCF!E31/DCF!E6", [0.02] * 4,
     "Treasury income on ~Rs 6,100 cr of cash and liquid funds: FY26 2.0%, H1 FY27 2.4%. Not in FCFF."),
    (58, "Finance costs % of revenue (EPS only)", "=F26/F7", "=I26/I7", 0.005, "=DCF!E32/DCF!E6", [0.005] * 4,
     "FY26 0.55%, H1 FY27 0.50% (includes lease interest)."),
    (59, "Share of associates % of revenue (EPS only)", "=F27/F7", "=I27/I7", 0.0045, "=DCF!E33/DCF!E6",
     [0.0045] * 4, "FY26 0.47%, H1 FY27 0.39% (PPG Asian Paints JV and others)."),
    (60, "Effective tax rate on PBT (EPS only)", "=F30/F29", "=I30/I29", 0.26, "=DCF!E37/DCF!E35", [0.26] * 4,
     "FY26 26.8%, H1 FY27 26.0%. FCFF uses the 25.17% statutory rate on EBIT instead."),
    (61, "Minority share of PAT (EPS only)", "=(F29-F30-F31)/(F29-F30)", "=(I29-I30-I31)/(I29-I30)", 0.015,
     "=DCF!E39/DCF!E38", [0.015] * 4, "FY26 1.6%, H1 FY27 1.4%."),
]
for r, label, b, c, d, e, fwd, reason in DRIVERS:
    put(ws, f"A{r}", label, "label")
    if b is not None:
        put(ws, f"B{r}", b, "calc", "pct2" if r >= 58 else "pct")
    if c is not None:
        put(ws, f"C{r}", c, "calc", "pct2" if r >= 58 else "pct")
    fmt = "pct2" if r >= 58 else "pct"
    if d is not None:
        put(ws, f"D{r}", d, "input", fmt, FILL_JUDG)
    if isinstance(e, str):
        put(ws, f"E{r}", e, "link", fmt)
    else:
        put(ws, f"E{r}", e, "input", fmt, FILL_JUDG)
    for col, v in zip("FGHI", fwd):
        put(ws, f"{col}{r}", v, "input", fmt, FILL_JUDG)
    put(ws, f"J{r}", reason, "note")
put(ws, "D56", "=E56", "calc", "pct")

sub(ws, 63, "E. Valuation inputs", 10)
VAL_INPUTS = [
    (64, "Valuation date (balance-sheet date)", dt.datetime(2026, 9, 30), "input", "date", None,
     "Latest reported balance sheet (Q2 FY27); cash, debt and minority interests are taken at this date."),
    (65, "End of FY2027 (year 1)", dt.datetime(2027, 3, 31), "input", "date", None,
     "Only H2 FY2027E (Oct-2026 to Mar-2027) is valued: H1 cash flows are already in the 30-Sep-2026 balance sheet."),
    (66, "Stub: years from valuation date to end-FY2027", "=(B65-B64)/365", "calc", "f4", None,
     "Discount period of the H2 FY2027E cash flow (cash flows at each 31-Mar, as in the TCS model)."),
    (67, "Terminal growth rate (g)", 0.06, "input", "pct", FILL_JUDG,
     "Long-run nominal growth for a mature market leader (~4% inflation + ~2% real); below the 7.41% risk-free "
     "rate. The grid tests 5.0-7.0%."),
    (68, "Corporate tax rate (new regime, s.115BAA)", 0.2517, "input", "pct2", None,
     "22% + 10% surcharge + 4% cess = 25.17% (Income-tax Act). Applied to EBIT in FCFF."),
    (69, "Exit EV/EBITDA multiple (cross-check only)", "=Comps!R14", "link", "x", None,
     "Median TTM EV/EBITDA of the four peers (Comps sheet)."),
    (70, f"Share price, 30-Oct-2026 close ({RS})", f"={pdref('price', 'ASIANPAINT')}", "link", "rs", None,
     "Yahoo Finance close."),
    (71, "Diluted shares (crore)", f"={pdref('shares', 'ASIANPAINT')}", "link", "f4", None,
     "S&P current share class (95.92 crore shares of Re 1; paid-up capital Rs 95.92 cr)."),
]
for r, label, val, sty, fmt, fill, reason in VAL_INPUTS:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", val, sty, fmt, fill)
    put(ws, f"C{r}", reason, "note")
widths(ws, {"A": 50, "B": 12, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12, "H": 13, "I": 12, "J": 100})
ws.freeze_panes = "B7"

# ----------------------------------------------------------------------------------------------
# WACC
# ----------------------------------------------------------------------------------------------
ws = ws_w
title(ws, "WACC (Indian rupees, CAPM)",
      "Blue = inputs, yellow = judgment, black = formulas. Asian Paints is net cash, so WACC is almost the cost of equity.")
sub(ws, 4, "Cost of equity (CAPM: Ke = rf + beta x ERP)", 3)
WACC_ROWS = [
    (5, "Risk-free rate: India 10-year G-sec, 30-Oct-2026", 0.0741, "input", "pct2", None,
     "Reuters via ETBFSI (30-Oct-2026): 6.94% 2036 benchmark at 7.4139%; Trading Economics: 7.40%. "
     "The 7.44% figure is the 29-Oct close (Financial Express)."),
    (6, "Regression beta: 5 years of weekly returns vs NIFTY 50", "=B33", "calc", "f3", None,
     "OLS in Python (build/prepare_data.py), 260 weeks to 30-Oct-2026, Yahoo adjusted closes; table below."),
    (7, "Blume-adjusted beta (0.67 x raw + 0.33)", "=0.67*B6+0.33", "calc", "f3", None,
     "Pulls the raw estimate toward 1.0."),
    (8, "Peer median beta (5y weekly)", "=MEDIAN(B34:B37)", "calc", "f3", None, "Four peers, same method."),
    (9, "Beta used (judgment)", 0.90, "input", "f3", FILL_JUDG,
     "Close to the regression (0.885, R2 0.25, s.e. 0.10), its Blume value (0.92) and the peer median (0.89). "
     "S&P's 0.31 uses a different method and is not used."),
    (10, "Equity risk premium (ERP)", 0.06, "input", "pct2", FILL_JUDG,
     "Same 6.0% as the TCS model (project 2). Damodaran's method gives a lower Ke (memo below); 6.0% is the more "
     "conservative choice."),
    (11, "Cost of equity (Ke)", "=B5+B9*B10", "calc", "pct2", None, ""),
    (12, "Memo: Damodaran total ERP for India, Jan-2026", 0.0708, "input", "pct2", None,
     "Mature-market ERP 4.23% + country risk premium 2.85% (Damodaran, ctryprem page, saved in source_data)."),
    (13, "Memo: India sovereign default spread (already in the G-sec yield)", 0.0187, "input", "pct2", None,
     "Damodaran, Jan-2026 (Baa3)."),
    (14, "Memo: Ke on Damodaran's method = (rf - default spread) + beta x total ERP", "=(B5-B13)+B9*B12", "calc",
     "pct2", None, "About 0.9 pp below the Ke used; the WACC grid on the Sensitivity sheet covers it."),
]
for r, label, val, sty, fmt, fill, note in WACC_ROWS:
    put(ws, f"A{r}", label, "bold" if r == 11 else "label")
    put(ws, f"B{r}", val, sty, fmt, fill, bold=(r == 11))
    put(ws, f"C{r}", note, "note")
sub(ws, 16, "Cost of debt", 3)
KD_ROWS = [
    (17, "Spread over the G-sec (judgment)", 0.01, "input", "pct2", FILL_JUDG,
     "Asian Paints is net cash and borrows mostly short term; rf + 1.0% approximates a top-rated corporate. "
     "Debt is ~2% of capital, so this barely moves WACC."),
    (18, "Pre-tax cost of debt (Kd)", "=B5+B17", "calc", "pct2", None, ""),
    (19, "Memo: FY2026 finance costs / average debt incl. leases", f"={DA}F26/AVERAGE({DA}B46,{DA}B47)", "link",
     "pct2", None, "Historical rate is lower (cheap working-capital lines); the marginal rate above is used."),
    (20, "Tax rate", f"={DA}B68", "link", "pct2", None, ""),
    (21, "After-tax cost of debt", "=B18*(1-B20)", "calc", "pct2", None, ""),
]
for r, label, val, sty, fmt, fill, note in KD_ROWS:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", val, sty, fmt, fill)
    put(ws, f"C{r}", note, "note")
sub(ws, 23, "Capital structure (market values) and WACC", 3)
CS_ROWS = [
    (24, f"Market capitalisation ({RS} cr) = price x shares", f"={DA}B70*{DA}B71", "link", "cr", ""),
    (25, f"Debt incl. lease liabilities, 30-Sep-2026 ({RS} cr)", f"={DA}B45", "link", "cr", ""),
    (26, "Equity weight E / (D + E)", "=B24/(B24+B25)", "calc", "pct2", ""),
    (27, "Debt weight D / (D + E)", "=B25/(B24+B25)", "calc", "pct2", ""),
    (28, "WACC", "=B26*B11+B27*B21", "calc", "pct2", ""),
    (29, "Sanity check (Indian large caps ~10-14% at current rates)",
     '=IF(AND(B28>=0.1,B28<=0.14),"Within range","Outside range")', "calc", None, ""),
]
for r, label, val, sty, fmt, note in CS_ROWS:
    put(ws, f"A{r}", label, "bold" if r == 28 else "label")
    put(ws, f"B{r}", val, sty, fmt, bold=(r == 28))
sub(ws, 31, "Regression betas vs NIFTY 50 (computed in Python; data/beta_summary.csv)", 8)
header(ws, 32, ["Company", "5y weekly beta", "R-squared", "Std error", "Weekly returns", "2y weekly beta",
                "5y monthly beta", "Blume-adjusted (5y weekly)"], height=32)
for i, s in enumerate(COMP):
    r = 33 + i
    put(ws, f"A{r}", NAME[s], "bold" if s == "ASIANPAINT" else "label")
    put(ws, f"B{r}", round(beta(s, "5y weekly"), 4), "input", "f3")
    put(ws, f"C{r}", round(beta(s, "5y weekly", "r_squared"), 4), "input", "f3")
    put(ws, f"D{r}", round(beta(s, "5y weekly", "std_error"), 4), "input", "f3")
    put(ws, f"E{r}", int(beta(s, "5y weekly", "n_obs")), "input", "n")
    put(ws, f"F{r}", round(beta(s, "2y weekly"), 4), "input", "f3")
    put(ws, f"G{r}", round(beta(s, "5y monthly"), 4), "input", "f3")
    put(ws, f"H{r}", f"=0.67*B{r}+0.33", "calc", "f3")
put(ws, "A38", "Window: weeks ending 12-Nov-2021 to 30-Oct-2026 (Friday closes). Total returns from Yahoo 'Adj Close'. "
               "No demerger-type moves found (largest weekly falls are results or market sell-offs).", "note")
put(ws, "A39", "JSW Dulux's low beta (0.44, R2 0.04) reflects a small free float and stock-specific news around its "
               "change of control, so it is a weak guide. Monthly betas are higher (1.09-1.16) but noisier "
               "(60 points).", "note")
widths(ws, {"A": 62, "B": 12, "C": 12, "D": 10, "E": 10, "F": 11, "G": 11, "H": 13})

# ----------------------------------------------------------------------------------------------
# DCF: FCFF build, EPS bridge, valuation and cross-checks
# ----------------------------------------------------------------------------------------------
ws = ws_d
title(ws, f"Asian Paints: discounted cash flow (FCFF, {RS} crore)",
      "Valuation date = 30-Sep-2026 balance sheet. Year 1 counts only H2 FY2027E; H1 FY2027 actuals are shown "
      "for reference. Cash flows are discounted from each 31-Mar (year-end convention, as in the TCS model).")
DC = ["B", "C", "D", "E", "F", "G", "H", "I"]          # FY26A, H1 FY27A, H2 FY27E, FY27E, FY28E..FY31E
FWD = ["F", "G", "H", "I"]
header(ws, 4, [f"{RS} crore", "FY2026A", "H1 FY2027A", "H2 FY2027E", "FY2027E", "FY2028E", "FY2029E", "FY2030E",
               "FY2031E", "Note"])


def drow(r: int, label: str, cells: dict[str, str], fmt: str, sty_label: str = "label", note: str = "",
         link_cols: str = "") -> None:
    """Write one DCF row: cells maps column letter -> formula; columns in link_cols get the green link style."""
    put(ws, f"A{r}", label, sty_label)
    for col, fml in cells.items():
        put(ws, f"{col}{r}", fml, "link" if col in link_cols else "calc", fmt, bold=(sty_label == "bold"))
    if note:
        put(ws, f"J{r}", note, "note")


def fwd(template: str) -> dict[str, str]:
    """Expand a template over FY2028E-FY2031E; {c} = this column, {p} = previous column."""
    prev = {"F": "E", "G": "F", "H": "G", "I": "H"}
    return {c: template.format(c=c, p=prev[c]) for c in FWD}


drow(5, "Revenue growth (H1 vs H1; H2 vs H2)", {"B": f"={DA}F16", "C": f"={DA}I16", "D": f"={DA}D51",
     "E": "=E6/B6-1", **fwd(f"={DA}{{c}}51")}, "pct", link_cols="BCDFGHI")
drow(6, "Revenue", {"B": f"={DA}F7", "C": f"={DA}I7", "D": f"={DA}H7*(1+D5)", "E": "=C6+D6",
     **fwd("={p}6*(1+{c}5)")}, "cr", "bold", link_cols="BC", note="H2 FY2027E = H2 FY2026A x (1 + growth)")
drow(7, "EBITDA margin", {"B": "=B8/B6", "C": "=C8/C6", "D": f"={DA}D52", "E": "=E8/E6",
     **fwd(f"={DA}{{c}}52")}, "pct", link_cols="DFGHI")
drow(8, "EBITDA", {"B": f"={DA}F8", "C": f"={DA}I8", "D": "=D6*D7", "E": "=C8+D8", **fwd("={c}6*{c}7")}, "cr",
     link_cols="BC")
drow(9, "D&A % of revenue", {"B": "=B10/B6", "C": "=C10/C6", "D": f"={DA}D53", "E": "=E10/E6",
     **fwd(f"={DA}{{c}}53")}, "pct", link_cols="DFGHI")
drow(10, "Depreciation and amortisation", {"B": f"={DA}F9", "C": f"={DA}I9", "D": "=D6*D9", "E": "=C10+D10",
     **fwd("={c}6*{c}9")}, "cr", link_cols="BC")
drow(11, "EBIT", {c: f"={c}8-{c}10" for c in DC}, "cr", "bold")
drow(12, "Tax rate on EBIT", {c: f"={DA}$B$68" for c in DC}, "pct2", link_cols="BCDEFGHI")
drow(13, "Tax on EBIT", {c: f"={c}11*{c}12" for c in DC}, "cr")
drow(14, "NOPAT = EBIT x (1 - tax)", {c: f"={c}11-{c}13" for c in DC}, "cr")
drow(15, "+ Depreciation and amortisation", {c: f"={c}10" for c in DC}, "cr")
drow(16, "Capex % of revenue", {"B": "=B17/B6", "C": "=C17/C6", "D": f"={DA}D54", "E": "=E17/E6",
     **fwd(f"={DA}{{c}}54")}, "pct", link_cols="DFGHI")
drow(17, "- Capex", {"B": f"={DA}F10", "C": f"={DA}I10", "D": "=D6*D16", "E": "=C17+D17", **fwd("={c}6*{c}16")},
     "cr", link_cols="BC")
drow(18, "New leases % of revenue", {"B": "=B19/B6", "C": f"={DA}D55", "D": f"={DA}D55", "E": "=E19/E6",
     **fwd(f"={DA}{{c}}55")}, "pct", link_cols="CDFGHI",
     note="FY2026A: lease principal repaid. H1 FY2027A: estimated at the 1.0% assumption")
drow(19, "- New leases (right-of-use additions)", {"B": f"={DA}F11", "C": "=C6*C18", "D": "=D6*D18",
     "E": "=C19+D19", **fwd("={c}6*{c}18")}, "cr", link_cols="B")
drow(20, "Trade working capital (period end)", {"B": f"={DA}F15", "C": f"={DA}I15", "D": "=E20",
     "E": f"=E6*{DA}E56", **fwd(f"={{c}}6*{DA}{{c}}56")}, "cr", link_cols="BC",
     note="31-Mar-2026, 30-Sep-2026 (actual), then each 31-Mar")
drow(21, "- Increase in trade working capital", {"B": f"={DA}F15-{DA}E15", "C": "=C20-B20", "D": "=D20-C20",
     "E": "=E20-B20", **fwd("={c}20-{p}20")}, "cr", link_cols="B",
     note="H2 FY2027E releases part of the seasonal 30-Sep inventory build")
drow(22, "Free cash flow to the firm (FCFF)", {c: f"={c}14+{c}15-{c}17-{c}19-{c}21" for c in DC}, "cr", "bold",
     note="FCFF = EBIT x (1 - t) + D&A - capex - new leases - increase in working capital")
drow(23, "FCFF margin", {c: f"={c}22/{c}6" for c in DC}, "pct")
drow(24, "FCFF counted in the valuation", {"D": "=D22", **fwd("={c}22")}, "cr", "bold",
     note="H2 FY2027E plus FY2028E-FY2031E (H1 FY2027 has already happened)")
drow(25, "Discount period (years from 30-Sep-2026)", {"D": f"={DA}B66", "F": "=D25+1", "G": "=F25+1",
     "H": "=G25+1", "I": "=H25+1"}, "f4", link_cols="D")
drow(26, "Discount factor at WACC", {c: f"=1/(1+$B$49)^{c}25" for c in ["D"] + FWD}, "f4")
drow(27, "PV of FCFF", {c: f"={c}24*{c}26" for c in ["D"] + FWD}, "cr")

sub(ws, 29, "Net profit and EPS (reference for Project 5; not used in FCFF)", 10)
drow(30, "EBIT", {c: f"={c}11" for c in DC}, "cr")
drow(31, "+ Other income", {"B": f"={DA}F25", "C": f"={DA}I25", "D": f"=D6*{DA}D57", "E": "=C31+D31",
     **fwd(f"={{c}}6*{DA}{{c}}57")}, "cr", link_cols="BC")
drow(32, "- Finance costs", {"B": f"={DA}F26", "C": f"={DA}I26", "D": f"=D6*{DA}D58", "E": "=C32+D32",
     **fwd(f"={{c}}6*{DA}{{c}}58")}, "cr", link_cols="BC")
drow(33, "+ Share of profit of associates", {"B": f"={DA}F27", "C": f"={DA}I27", "D": f"=D6*{DA}D59",
     "E": "=C33+D33", **fwd(f"={{c}}6*{DA}{{c}}59")}, "cr", link_cols="BC")
drow(34, "- Exceptional items", {"B": f"={DA}F28", "C": f"={DA}I28", "E": "=C34+D34"}, "cr", link_cols="BC",
     note="None forecast")
for c in ["D"] + FWD:
    put(ws, f"{c}34", 0, "input", "cr")
drow(35, "Profit before tax", {c: f"={c}30+{c}31-{c}32+{c}33-{c}34" for c in DC}, "cr", "bold")
drow(36, "Memo: profit before tax as reported", {"B": f"={DA}F29", "C": f"={DA}I29"}, "cr", link_cols="BC",
     note="Check: the rebuild from EBITDA equals the reported figure")
drow(37, "- Tax", {"B": f"={DA}F30", "C": f"={DA}I30", "D": f"=D35*{DA}D60", "E": "=C37+D37",
     **fwd(f"={{c}}35*{DA}{{c}}60")}, "cr", link_cols="BC")
drow(38, "Profit after tax", {c: f"={c}35-{c}37" for c in DC}, "cr")
drow(39, "- Minority interest", {"B": f"=B38-{DA}F31", "C": f"=C38-{DA}I31", "D": f"=D38*{DA}D61",
     "E": "=C39+D39", **fwd(f"={{c}}38*{DA}{{c}}61")}, "cr")
drow(40, "PAT attributable to owners", {c: f"={c}38-{c}39" for c in DC}, "cr", "bold")
drow(41, f"EPS ({RS}, on {RS}95.92 crore shares)", {c: f"={c}40/{DA}$B$71" for c in DC}, "eps", "bold")
drow(42, f"Consensus EPS ({RS}, S&P)", {"E": f"={pdref('c_eps27', 'ASIANPAINT')}",
     "F": f"={pdref('c_eps28', 'ASIANPAINT')}"}, "eps", link_cols="EF")
drow(43, "Model EPS vs consensus", {"E": "=E41/E42-1", "F": "=F41/F42-1"}, "chg")
drow(44, f"Consensus revenue ({RS} cr, S&P)", {"E": f"={pdref('c_rev27', 'ASIANPAINT')}",
     "F": f"={pdref('c_rev28', 'ASIANPAINT')}"}, "cr", link_cols="EF")
drow(45, "Model revenue vs consensus", {"E": "=E6/E44-1", "F": "=F6/F44-1"}, "chg")

sub(ws, 47, f"Valuation ({RS} crore unless stated)", 10)
VAL = [
    (48, "Sum of PV of FCFF (H2 FY2027E to FY2031E)", "=SUM(D27:I27)", "cr", "calc"),
    (49, "WACC", "=WACC!B28", "pct2", "link"),
    (50, "Terminal growth rate (g)", f"={DA}B67", "pct2", "link"),
    (51, "FCFF in FY2031E", "=I22", "cr", "calc"),
    (52, "Terminal value at end-FY2031E = FCFF x (1 + g) / (WACC - g)", "=B51*(1+B50)/(B49-B50)", "cr", "calc"),
    (53, "PV of terminal value", "=B52*I26", "cr", "calc"),
    (54, "Enterprise value", "=B48+B53", "cr", "calc"),
    (55, "+ Cash and bank balances", f"={DA}B40+{DA}B41", "cr", "link"),
    (56, "+ Current investments (liquid mutual funds)", f"={DA}B42", "cr", "link"),
    (57, "+ Non-current investments incl. associates (book value)", f"={DA}B43+{DA}B44", "cr", "link"),
    (58, "- Borrowings", f"={DA}B35+{DA}B36", "cr", "link"),
    (59, "- Lease liabilities", f"={DA}B37+{DA}B38", "cr", "link"),
    (60, "- Non-controlling interests (book value)", f"={DA}B39", "cr", "link"),
    (61, "Net adjustments from EV to equity", "=B55+B56+B57-B58-B59-B60", "cr", "calc"),
    (62, "Equity value", "=B54+B61", "cr", "calc"),
    (63, "Diluted shares (crore)", f"={DA}B71", "f4", "link"),
    (64, f"DCF value per share ({RS})", "=B62/B63", "rs", "calc"),
    (65, f"Share price, 30-Oct-2026 ({RS})", f"={DA}B70", "rs", "link"),
    (66, "Upside / (downside) = value / price - 1", "=B64/B65-1", "chg", "calc"),
    (67, "Verdict", '=IF(B66>0.1,"DCF value is more than 10% above the market price",IF(B66<-0.1,'
                    '"DCF value is more than 10% below the market price","DCF value is within 10% of the market price"))',
     None, "calc"),
]
for r, label, fml, fmt, sty in VAL:
    bold = r in (54, 62, 64)
    put(ws, f"A{r}", label, "bold" if bold else "label")
    put(ws, f"B{r}", fml, sty, fmt, bold=bold)
put(ws, "C57", "Their income (other income, associates) is excluded from FCFF, so their value is added here", "note")
put(ws, "C60", "Book value; a market value would be a little higher", "note")

sub(ws, 69, "Cross-checks", 10)
XCHK = [
    (70, "Terminal value as % of EV", "=B53/B54", "pct"),
    (71, "EBITDA in FY2031E", "=I8", "cr"),
    (72, "EV/EBITDA implied by the Gordon terminal value (TV / FY2031E EBITDA)", "=B52/B71", "x"),
    (73, "Exit multiple: peer median EV/EBITDA TTM", f"={DA}B69", "x"),
    (74, "Terminal value at the exit multiple", "=B71*B73", "cr"),
    (75, "EV using the exit-multiple terminal value", "=B48+B74*I26", "cr"),
    (76, f"Value per share using the exit multiple ({RS})", "=(B75+B61)/B63", "rs"),
    (77, "Perpetual growth implied by the exit multiple", "=(B74*B49-B51)/(B74+B51)", "pct2"),
    (78, "Market EV on the same definition (market cap - net adjustments)", "=B65*B63-B61", "cr"),
    (79, "Terminal value needed for the DCF to equal the market EV", "=(B78-B48)/I26", "cr"),
    (80, "Perpetual FCFF growth after FY2031E implied by the market price", "=(B79*B49-B51)/(B79+B51)", "pct2"),
    (81, "Market EV / FY2027E EBITDA", "=B78/E8", "x"),
    (82, "DCF EV / FY2027E EBITDA", "=B54/E8", "x"),
    (83, "FCFF check: H1 FY2027A + H2 FY2027E - FY2027E (should be 0)", "=C22+D22-E22", "cr2"),
]
for r, label, fml, fmt in XCHK:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", fml, "link" if "DCF_Assumptions" in fml else "calc", fmt)
put(ws, "C77", "Growth formula from TV = FCFF x (1 + g) / (WACC - g), solved for g: g = (TV x WACC - FCFF) / (TV + FCFF)",
    "note")
put(ws, "C80", "Same formula with the terminal value the market price requires", "note")
widths(ws, {"A": 62, "B": 13, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12, "H": 12, "I": 12, "J": 70})
ws.freeze_panes = "B5"

# ----------------------------------------------------------------------------------------------
# Sensitivity: WACC x g (5 x 5), every cell a full formula (no Data Table)
# ----------------------------------------------------------------------------------------------
ws = ws_s
title(ws, f"Sensitivity: DCF value per share ({RS})",
      "Every cell recomputes the DCF from the FCFF row on the DCF sheet: PV of H2 FY2027E-FY2031E FCFF + PV of the "
      "Gordon terminal value + net adjustments, divided by shares.")
put(ws, "A3", f"Share price, 30-Oct-2026 ({RS})", "label")
put(ws, "B3", "=DCF!B65", "link", "rs")
sub(ws, 5, f"1) Value per share ({RS}): WACC (down) x terminal growth g (across)", 7)
put(ws, "A6", "WACC (down) / g (across); corner = base value", "bold")
put(ws, "B6", "=DCF!B64", "link", "rs0")
STEPS = [-0.01, -0.005, 0.0, 0.005, 0.01]
GCOLS = ["C", "D", "E", "F", "G"]
for col, st in zip(GCOLS, STEPS):
    put(ws, f"{col}6", f"={DA}$B$67+({st})", "link", "pct", bold=True)
for i, st in enumerate(STEPS):
    r = 7 + i
    put(ws, f"B{r}", f"=WACC!$B$28+({st})", "link", "pct2", bold=True)
    for col in GCOLS:
        fml = (f'=IF($B{r}<={col}$6,"n/a",(SUMPRODUCT(DCF!$D$24:$I$24/(1+$B{r})^DCF!$D$25:$I$25)'
               f'+DCF!$I$22*(1+{col}$6)/($B{r}-{col}$6)/(1+$B{r})^DCF!$I$25+DCF!$B$61)/DCF!$B$63)')
        put(ws, f"{col}{r}", fml, "calc", "rs0", fill=FILL_TGT if (i == 2 and col == "E") else None)
sub(ws, 13, "2) Upside / (downside) vs the 30-Oct-2026 price", 7)
for col in GCOLS:
    put(ws, f"{col}14", f"={col}6", "calc", "pct", bold=True)
for i in range(5):
    r = 15 + i
    put(ws, f"B{r}", f"=B{7 + i}", "calc", "pct2", bold=True)
    for col in GCOLS:
        put(ws, f"{col}{r}", f'=IF(ISNUMBER({col}{7 + i}),{col}{7 + i}/$B$3-1,"n/a")', "calc", "chg")
sub(ws, 21, "3) Checks and football-field range", 7)
put(ws, "A22", "Grid centre equals the DCF value", "label")
put(ws, "B22", '=IF(ABS(E9-DCF!B64)<0.01,"PASS","FAIL")', "calc")
put(ws, "A23", "WACC above g in every cell", "label")
put(ws, "B23", '=IF(COUNTIF(C7:G11,"n/a")=0,"PASS","FAIL")', "calc")
put(ws, "A24", f"Inner 3x3 (WACC +/-0.5 pp, g +/-0.5 pp): low ({RS})", "label")
put(ws, "B24", "=MIN(D8:F10)", "calc", "rs0")
put(ws, "A25", f"Inner 3x3: high ({RS})", "label")
put(ws, "B25", "=MAX(D8:F10)", "calc", "rs0")
put(ws, "A26", f"Full grid: low - high ({RS})", "label")
put(ws, "B26", "=MIN(C7:G11)", "calc", "rs0")
put(ws, "C26", "=MAX(C7:G11)", "calc", "rs0")
pass_fail_format(ws, "B22:B23")
widths(ws, {"A": 50, "B": 12, "C": 11, "D": 11, "E": 11, "F": 11, "G": 11})

# ----------------------------------------------------------------------------------------------
# Football field
# ----------------------------------------------------------------------------------------------
ws = ws_f
title(ws, f"Football field: Asian Paints value per share ({RS})",
      "Bars show the low-high range of each method; the red dashed line is the 30-Oct-2026 share price. "
      "All values link to the Sensitivity, Comps and Peer_Data sheets.")
header(ws, 4, ["Method", f"Low ({RS})", f"High ({RS})", f"Mid / base ({RS})", "Basis", "Price inside the range?",
               "Chart: invisible base", "Chart: range"], height=32)
FF = [
    (5, "52-week trading range", f"={pdref('low52', 'ASIANPAINT')}", f"={pdref('high52', 'ASIANPAINT')}", None,
     "Intraday low and high, 31-Oct-2025 to 30-Oct-2026 (Yahoo Finance). Context, not a valuation."),
    (6, "DCF (WACC +/-0.5 pp, g +/-0.5 pp)", "=Sensitivity!B24", "=Sensitivity!B25", "=DCF!B64",
     "Inner 3x3 of the WACC x g grid; mid = base case"),
    (7, "EV/EBITDA comps (peer 25th-75th, TTM)", "=Comps!D21", "=Comps!F21", "=Comps!E21",
     "Peer quartiles x Asian Paints TTM EBITDA; mid = peer median"),
    (8, "P/E comps (peer 25th-75th, TTM)", "=Comps!D22", "=Comps!F22", "=Comps!E22",
     "Peer quartiles x Asian Paints TTM EPS; mid = peer median"),
    (9, "EV/Sales comps (peer 25th-75th, TTM)", "=Comps!D23", "=Comps!F23", "=Comps!E23",
     "Peer quartiles x Asian Paints TTM revenue; ignores the margin gap"),
    (10, "Analyst price targets (low-high)", f"={pdref('pt_low', 'ASIANPAINT')}", f"={pdref('pt_high', 'ASIANPAINT')}",
     f"={pdref('pt_med', 'ASIANPAINT')}", "S&P Global consensus via stockanalysis.com (34 analysts); mid = median"),
]
for r, label, lo, hi, mid, basis in FF:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", lo, "link", "rs0")
    put(ws, f"C{r}", hi, "link", "rs0")
    if mid:
        put(ws, f"D{r}", mid, "link", "rs0")
    else:
        put(ws, f"D{r}", "n/a", "calc", align="right")
    put(ws, f"E{r}", basis, "note")
    put(ws, f"F{r}", f'=IF(AND($B$11>=B{r},$B$11<=C{r}),"Yes","No")', "calc", align="center")
    put(ws, f"G{r}", f"=B{r}", "calc", "rs0")
    put(ws, f"H{r}", f"=C{r}-B{r}", "calc", "rs0")
put(ws, "A11", "Share price, 30-Oct-2026 close", "bold")
for col in "BCD":
    put(ws, f"{col}11", f"={pdref('price', 'ASIANPAINT')}", "link", "rs0", bold=True)
put(ws, "E11", "Drawn as the vertical line (helper cells J5:K6)", "note")
put(ws, "J4", "Price line x", "bold")
put(ws, "K4", "Price line y", "bold")
put(ws, "J5", "=$B$11", "calc", "rs0")
put(ws, "K5", 0, "calc")
put(ws, "J6", "=$B$11", "calc", "rs0")
put(ws, "K6", 1, "calc")

sub(ws, 13, "Read-across", 8)
RA = [
    (14, f"DCF base value ({RS})", "=D6", "rs0", "=B14/$B$11-1"),
    (15, f"Comps blended median: average of the EV/EBITDA and P/E medians ({RS})", "=AVERAGE(D7:D8)", "rs0",
     "=B15/$B$11-1"),
    (16, "Gap between the DCF and the comps blended median (DCF / comps - 1)", "=B14/B15-1", "chg", None),
    (17, f"Share price ({RS})", "=B11", "rs0", None),
    (18, "Price inside the DCF range?", "=F6", None, None),
    (19, "Price inside the EV/EBITDA comps range?", "=F7", None, None),
    (20, "Price inside the P/E comps range?", "=F8", None, None),
    (21, "Price inside the EV/Sales comps range?", "=F9", None, None),
    (22, "Price inside the analyst price-target range?", "=F10", None, None),
    (23, "Do the DCF and EV/EBITDA comps ranges overlap?", '=IF(AND(B6<=C7,B7<=C6),"Yes","No")', None, None),
    (24, "Highest valuation-based value (DCF and comps bars) vs price", "=MAX(C6:C9)/B11-1", "chg", None),
    (25, "Asian Paints EV/EBITDA premium to the peer median", "=Comps!R17", "chg", None),
]
put(ws, "C13", "Gap vs price", "bold")
for r, label, fml, fmt, gap in RA:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", fml, "calc", fmt, align=None if fmt else "center")
    if gap:
        put(ws, f"C{r}", gap, "calc", "chg")
put(ws, "A26", "Summary", "bold")
put(ws, "B26", '="The price of Rs "&TEXT(B11,"#,##0")&" is above every valuation-based range: comps give Rs "'
               '&TEXT(MIN(B7:B9),"#,##0")&"-"&TEXT(MAX(C7:C9),"#,##0")&" and the DCF Rs "&TEXT(B6,"#,##0")&"-"'
               '&TEXT(C6,"#,##0")&". Only the 52-week range and analyst targets contain it."', "calc")
put(ws, "A27", "The 52-week bar and analyst targets are context, not valuation methods. Column C of rows 14-15 is "
               "the gap to the market price.", "note")

bar = BarChart()
bar.type = "bar"
bar.grouping = "stacked"
bar.overlap = 100
bar.gapWidth = 60
bar.title = "Asian Paints: value per share by method (Rs per share; red line = 30-Oct-2026 price)"
bar.title.overlay = False
bar.add_data(Reference(ws, min_col=7, min_row=4, max_row=10), titles_from_data=True)
bar.add_data(Reference(ws, min_col=8, min_row=4, max_row=10), titles_from_data=True)
bar.set_categories(Reference(ws, min_col=1, min_row=5, max_row=10))
bar.series[0].graphicalProperties.noFill = True
bar.series[0].graphicalProperties.line.noFill = True
bar.series[1].graphicalProperties.solidFill = "4472C4"
bar.series[1].graphicalProperties.line.solidFill = "2F5597"
bar.x_axis.scaling.orientation = "maxMin"     # first method at the top
bar.x_axis.delete = False
bar.y_axis.delete = False
bar.y_axis.scaling.min = 0
bar.y_axis.scaling.max = 3600
bar.y_axis.majorUnit = 400
bar.y_axis.crosses = "max"                     # keeps the value axis at the bottom with reversed categories
bar.y_axis.numFmt = "#,##0"
bar.x_axis.majorGridlines = None
bar.legend = None
sc = ScatterChart()
price_line = Series(Reference(ws, min_col=11, min_row=5, max_row=6), Reference(ws, min_col=10, min_row=5, max_row=6),
                    title="Share price 30-Oct-2026")
price_line.marker.symbol = "none"
price_line.smooth = False
price_line.graphicalProperties.line.solidFill = "C00000"
price_line.graphicalProperties.line.width = 28575
price_line.graphicalProperties.line.dashStyle = "dash"
sc.series.append(price_line)
sc.x_axis.axId = 500
sc.y_axis.axId = 600
sc.x_axis.crossAx = 600
sc.y_axis.crossAx = 500
sc.x_axis.scaling.min = 0
sc.x_axis.scaling.max = 3600
sc.y_axis.scaling.min = 0
sc.y_axis.scaling.max = 1
sc.x_axis.delete = True
sc.y_axis.delete = True
sc.x_axis.majorGridlines = None
sc.y_axis.majorGridlines = None
sc.y_axis.crosses = "max"
bar += sc
bar.width = 26
bar.height = 11
ws.add_chart(bar, "A29")
widths(ws, {"A": 62, "B": 12, "C": 12, "D": 13, "E": 70, "F": 12, "G": 12, "H": 12, "J": 12, "K": 12})

# ----------------------------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------------------------
ws = ws_k
title(ws, "Model checks", "Each check returns PASS or FAIL. The Cover sheet shows the overall result.")
header(ws, 4, ["#", "Check", "Result", "Detail"], height=20)
mc = ",".join(f"ABS(Comps!E{CROW[s]}/{pdref('scr_mcap', s)}-1)" for s in COMP)
pe = ",".join(f"ABS(Comps!S{CROW[s]}/{pdref('scr_pe', s)}-1)" for s in COMP)
quart = ",".join(f"Comps!{c}12<=Comps!{c}13,Comps!{c}13<=Comps!{c}14,Comps!{c}14<=Comps!{c}15,"
                 f"Comps!{c}15<=Comps!{c}16" for c in STAT_COLS)
ap_ttm_ebitda = f"({DA}F8+{DA}I8-{DA}G8)"
ap_ttm_rev = f"({DA}F7+{DA}I7-{DA}G7)"
CHECKS = [
    ("Market cap (price x shares) within 1% of Screener's, all five companies",
     f'=IF(MAX({mc})<0.01,"PASS","FAIL")', f"=MAX({mc})", "pct2"),
    ("P/E (market cap / TTM PAT) within 2% of Screener's, all five companies",
     f'=IF(MAX({pe})<0.02,"PASS","FAIL")', f"=MAX({pe})", "pct2"),
    ("Asian Paints TTM revenue (Screener) within 0.1% of the filing (FY26 + H1 FY27 - H1 FY26)",
     f'=IF(ABS(Comps!J5/{ap_ttm_rev}-1)<0.001,"PASS","FAIL")', f"=Comps!J5/{ap_ttm_rev}-1", "pct2"),
    ("Asian Paints TTM EBITDA (Screener) within 0.1% of the filing",
     f'=IF(ABS(Comps!K5/{ap_ttm_ebitda}-1)<0.001,"PASS","FAIL")', f"=Comps!K5/{ap_ttm_ebitda}-1", "pct2"),
    ("Asian Paints debt incl. leases (Screener) within 0.5% of the filing",
     f'=IF(ABS(Comps!F5/{DA}B45-1)<0.005,"PASS","FAIL")', f"=Comps!F5/{DA}B45-1", "pct2"),
    ("Asian Paints cash + liquid investments (S&P) within 0.5% of the filing",
     f'=IF(ABS(Comps!H5/({DA}B40+{DA}B41+{DA}B42)-1)<0.005,"PASS","FAIL")',
     f"=Comps!H5/({DA}B40+{DA}B41+{DA}B42)-1", "pct2"),
    ("Asian Paints minority interest (Screener) within 0.5% of the filing",
     f'=IF(ABS(Comps!G5/{DA}B39-1)<0.005,"PASS","FAIL")', f"=Comps!G5/{DA}B39-1", "pct2"),
    ("Peer statistics in order (min <= 25th <= median <= 75th <= max) in every column",
     f'=IF(AND({quart}),"PASS","FAIL")', None, None),
    ("Drop-one medians stay inside the four-peer min-max",
     '=IF(AND(MIN(Comps!B31:B34)>=Comps!R12,MAX(Comps!B31:B34)<=Comps!R16,MIN(Comps!C31:C34)>=Comps!S12,'
     'MAX(Comps!C31:C34)<=Comps!S16,MIN(Comps!D31:D34)>=Comps!T12,MAX(Comps!D31:D34)<=Comps!T16),"PASS","FAIL")',
     None, None),
    ("Every implied value per share is positive", '=IF(MIN(Comps!C21:G25)>0,"PASS","FAIL")', "=MIN(Comps!C21:G25)",
     "rs0"),
    ("FY2026 profit before tax rebuilt from EBITDA equals the reported figure (within Rs 1 cr)",
     '=IF(ABS(DCF!B35-DCF!B36)<1,"PASS","FAIL")', "=DCF!B35-DCF!B36", "cr2"),
    ("H1 FY2027 profit before tax rebuilt from EBITDA equals the reported figure (within Rs 1 cr)",
     '=IF(ABS(DCF!C35-DCF!C36)<1,"PASS","FAIL")', "=DCF!C35-DCF!C36", "cr2"),
    ("FY2027E FCFF equals H1 FY2027A + H2 FY2027E", '=IF(ABS(DCF!B83)<0.01,"PASS","FAIL")', "=DCF!B83", "cr2"),
    ("WACC is above the terminal growth rate", '=IF(DCF!B49>DCF!B50,"PASS","FAIL")', "=DCF!B49-DCF!B50", "pct2"),
    ("Sensitivity grid centre equals the DCF value", "=Sensitivity!B22", "=Sensitivity!E9-DCF!B64", "cr2"),
    ("WACC above g in every grid cell", "=Sensitivity!B23", None, None),
    ("WACC within the 10-14% sanity range", '=IF(AND(WACC!B28>=0.1,WACC!B28<=0.14),"PASS","FAIL")', "=WACC!B28",
     "pct2"),
    ("Terminal value between 50% and 90% of EV", '=IF(AND(DCF!B70>=0.5,DCF!B70<=0.9),"PASS","FAIL")', "=DCF!B70",
     "pct"),
    ("Capital-structure weights sum to 100%", '=IF(ABS(WACC!B26+WACC!B27-1)<0.000001,"PASS","FAIL")',
     "=WACC!B26+WACC!B27", "pct2"),
    ("Beta used within 0.15 of the 5-year regression beta", '=IF(ABS(WACC!B9-WACC!B6)<=0.15,"PASS","FAIL")',
     "=WACC!B9-WACC!B6", "f3"),
    ("Football field: every low <= high",
     "=IF(AND(" + ",".join(f"Football_Field!B{r}<=Football_Field!C{r}" for r in range(5, 11)) + '),"PASS","FAIL")',
     None, None),
    ("No error values in the key output ranges",
     '=IF(ISERROR(SUM(Comps!C5:X37)+SUM(DCF!B5:I45)+SUM(DCF!B48:B66)+SUM(DCF!B70:B83)+SUM(Sensitivity!B6:G19)'
     '+SUM(Football_Field!B5:D11)+SUM(WACC!B5:B28)),"FAIL","PASS")', None, None),
]
for i, (label, fml, detail, fmt) in enumerate(CHECKS, start=1):
    r = 4 + i
    put(ws, f"A{r}", i, "calc", "n", align="center")
    put(ws, f"B{r}", label, "label")
    put(ws, f"C{r}", fml, "calc", align="center")
    if detail:
        put(ws, f"D{r}", detail, "calc", fmt)
LAST_CHECK = 4 + len(CHECKS)
pass_fail_format(ws, f"C5:C{LAST_CHECK}")
r = LAST_CHECK + 2
put(ws, f"B{r}", "Overall result", "bold")
put(ws, f"C{r}", f'=IF(COUNTIF(C5:C{LAST_CHECK},"FAIL")=0,"PASS","FAIL")', "calc", bold=True, align="center")
put(ws, f"D{r}", f'=COUNTIF(C5:C{LAST_CHECK},"PASS")&" of {len(CHECKS)} checks pass"', "calc")
pass_fail_format(ws, f"C{r}")
OVERALL = f"Checks!C{r}"
OVERALL_TXT = f"Checks!D{r}"
put(ws, f"B{r + 2}", "Information (not pass/fail)", "bold")
put(ws, f"B{r + 3}", "Peers whose TTM ends Jun-2026 (one quarter older than Asian Paints)", "label")
put(ws, f"C{r + 3}", '=COUNTIF(Comps!B6:B9,"Jun-2026")', "calc", "n", align="center")
put(ws, f"D{r + 3}", "Berger, Kansai Nerolac and JSW Dulux reported Q2 FY27 after the 30-Oct-2026 price date", "note")
put(ws, f"B{r + 4}", "Peer with results published after the price date's close", "label")
put(ws, f"C{r + 4}", "Indigo", "calc", align="center")
put(ws, f"D{r + 4}", "Filed 30-Oct-2026 at 17:41 IST; its TTM includes the quarter but the price does not", "note")
widths(ws, {"A": 5, "B": 84, "C": 10, "D": 16})
ws.freeze_panes = "A5"

# ----------------------------------------------------------------------------------------------
# Cover
# ----------------------------------------------------------------------------------------------
ws = ws_cover
title(ws, "Asian Paints: comparable company analysis and DCF, with a football field",
      f"{RS} crore unless stated. Prices: 30-Oct-2026 close. Valuation date: 30-Sep-2026 balance sheet. "
      "Educational project, not investment advice.")
sub(ws, 4, "Purpose", 3)
for i, line in enumerate([
    "Value Asian Paints two ways and compare: (1) trading multiples of four listed Indian paint peers (EV/EBITDA, P/E,",
    "EV/Sales) and (2) a five-year FCFF DCF. The football field puts both next to the 52-week range, analyst targets",
    "and the share price.",
], start=5):
    put(ws, f"A{i}", line, "label")
sub(ws, 9, "Key outputs", 3)
header(ws, 10, ["Item", "Value", "Note"], height=20)
COVER = [
    (11, f"Share price, 30-Oct-2026 ({RS})", "=DCF!B65", "rs", "Yahoo Finance close"),
    (12, f"DCF value per share ({RS})", "=DCF!B64", "rs", "Base case"),
    (13, "DCF upside / (downside) vs price", "=DCF!B66", "chg", "=DCF!B67"),
    (14, f"DCF range, WACC +/-0.5 pp and g +/-0.5 pp ({RS})",
     '=TEXT(Football_Field!B6,"#,##0")&" - "&TEXT(Football_Field!C6,"#,##0")', None, "Inner 3x3 of the grid"),
    (15, "WACC", "=WACC!B28", "pct2", '="Ke "&TEXT(WACC!B11,"0.00%")&" (rf 7.41%, beta 0.90, ERP 6.0%)"'),
    (16, "Terminal growth (g)", f"={DA}B67", "pct", "Judgment"),
    (17, "Perpetual growth after FY2031E implied by the market price", "=DCF!B80", "pct2",
     "Same cash flows and WACC; solves for g"),
    (18, "EV/EBITDA TTM: peer median | Asian Paints",
     '=TEXT(Comps!R14,"0.0")&"x | "&TEXT(Comps!R5,"0.0")&"x (premium "&TEXT(Comps!R17,"0%")&")"', None, ""),
    (19, "P/E TTM: peer median | Asian Paints",
     '=TEXT(Comps!S14,"0.0")&"x | "&TEXT(Comps!S5,"0.0")&"x (premium "&TEXT(Comps!S17,"0%")&")"', None, ""),
    (20, "EV/Sales TTM: peer median | Asian Paints",
     '=TEXT(Comps!T14,"0.00")&"x | "&TEXT(Comps!T5,"0.00")&"x (premium "&TEXT(Comps!T17,"0%")&")"', None, ""),
    (21, f"Implied value, EV/EBITDA: median (25th-75th) ({RS})",
     '=TEXT(Comps!E21,"#,##0")&" ("&TEXT(Comps!D21,"#,##0")&" - "&TEXT(Comps!F21,"#,##0")&")"', None, ""),
    (22, f"Implied value, P/E: median (25th-75th) ({RS})",
     '=TEXT(Comps!E22,"#,##0")&" ("&TEXT(Comps!D22,"#,##0")&" - "&TEXT(Comps!F22,"#,##0")&")"', None, ""),
    (23, f"Implied value, EV/Sales: median (25th-75th) ({RS})",
     '=TEXT(Comps!E23,"#,##0")&" ("&TEXT(Comps!D23,"#,##0")&" - "&TEXT(Comps!F23,"#,##0")&")"', None, ""),
    (24, f"Analyst price targets: low - median - high ({RS})",
     '=TEXT(Football_Field!B10,"#,##0")&" - "&TEXT(Football_Field!D10,"#,##0")&" - "&TEXT(Football_Field!C10,"#,##0")',
     None, "S&P Global consensus, 34 analysts"),
    (25, f"52-week range ({RS})", '=TEXT(Football_Field!B5,"#,##0")&" - "&TEXT(Football_Field!C5,"#,##0")', None,
     "Intraday"),
    (26, "Read-across", "=Football_Field!B26", None, ""),
]
for r, label, fml, fmt, note in COVER:
    put(ws, f"A{r}", label, "label")
    put(ws, f"B{r}", fml, "link", fmt, align="right" if fmt else None)
    put(ws, f"C{r}", note, "calc" if str(note).startswith("=") else "note")
sub(ws, 28, "Scenario", 3)
put(ws, "A29", "Single base case (no scenario switch). The Sensitivity sheet varies WACC and g; the drop-one table on "
               "Comps varies the peer set.", "label")
sub(ws, 31, "Model checks", 3)
put(ws, "A32", "Overall status (Checks sheet)", "bold")
put(ws, "B32", f"={OVERALL}", "link", bold=True, align="center")
put(ws, "C32", f"={OVERALL_TXT}", "link")
pass_fail_format(ws, "B32")
sub(ws, 34, "How to use", 3)
for i, line in enumerate([
    "1. Blue cells are inputs: Peer_Data (market and financial data), DCF_Assumptions and WACC. Change one and every "
    "sheet recalculates.",
    "2. Yellow cells are my judgment calls; each has a one-line reason next to it.",
    "3. Comps shows the multiples, peer quartiles, implied values and the drop-one-peer test.",
    "4. DCF builds FCFF from the drivers; Sensitivity gives the WACC x g grid; Football_Field summarises everything.",
    "5. Checks must all say PASS after any change. Rebuild from scratch: python build/build_model.py, then "
    "python build/recalc_verify.py.",
], start=35):
    put(ws, f"A{i}", line, "label")
sub(ws, 41, "Sheet guide and colour key", 3)
GUIDE = [
    ("Peer_Data", "Inputs for the five companies, with units and sources"),
    ("Comps", "Market cap, EV, multiples, peer statistics, implied values, drop-one-peer sensitivity"),
    ("DCF_Assumptions", "Asian Paints history, balance sheet at 30-Sep-2026, forecast drivers, valuation inputs"),
    ("WACC", "CAPM cost of equity, cost of debt, weights; regression betas from Python"),
    ("DCF", "FCFF FY2026A-FY2031E, EPS bridge, valuation bridge, cross-checks"),
    ("Sensitivity", "Value per share for WACC x g (5 x 5) and upside vs price"),
    ("Football_Field", "Ranges by method, read-across, native Excel chart"),
    ("Checks", "PASS/FAIL tests"),
]
for i, (sheet, desc) in enumerate(GUIDE):
    put(ws, f"A{42 + i}", sheet, "bold")
    put(ws, f"B{42 + i}", desc, "label")
put(ws, "A51", "Blue = input", "input")
put(ws, "B51", "Black = formula", "calc")
put(ws, "C51", "Green = link to another sheet", "link")
put(ws, "A52", "Yellow fill = judgment assumption", "label", fill=FILL_JUDG)
put(ws, "B52", "Green fill = Asian Paints row", "label", fill=FILL_TGT)
widths(ws, {"A": 62, "B": 34, "C": 60})

for sheet in wb.worksheets:
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.tabColor = {"Cover": "1F4E78", "Peer_Data": "0000FF", "DCF_Assumptions": "0000FF",
                                       "WACC": "0000FF", "Checks": "00B050"}.get(sheet.title, "808080")
wb.save(OUT)
print(f"saved {OUT} ({OUT.stat().st_size:,} bytes)")
print("BUILD DONE")
