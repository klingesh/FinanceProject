"""Build AsianPaints_Ratio_Analysis.xlsx: ratio analysis and peer benchmarking of five Indian paint companies.

Every ratio is a live Excel formula that points at the Raw_Data input cells, so changing an input recalculates
the whole workbook. ratio_engine.py computes the same numbers in pandas; verify_workbook.py compares the two.

Sheets: Cover | Raw_Data | Ratios | DuPont | Peer_Comparison | Charts | Conclusion | Checks
Colours: blue font = input from a source; black = formula; green = link to another sheet;
         yellow fill = judgment input (ranking weights, ranking basis) with the reason next to it.

Run:  python build/build_ratio_workbook.py      (then python build/verify_workbook.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ratio_engine as RE  # noqa: E402
import wb_common as C  # noqa: E402

FILL_PASS = PatternFill("solid", fgColor="C6EFCE")
FILL_FAIL = PatternFill("solid", fgColor="FFC7CE")
COLS_FY = [C.YCOL[f] for f in C.FYS]          # D..I
COLS_R = [C.YCOL[f] for f in C.RFYS]          # E..I
PREV = {C.YCOL[C.FYS[i + 1]]: C.YCOL[C.FYS[i]] for i in range(5)}   # E->D ... I->H
LAST = C.YCOL["FY2026"]                        # I
SCOPE = {"ASIANPAINT": "consolidated", "BERGEPAINT": "consolidated", "KANSAINER": "consolidated",
         "JSWDULUX": "consolidated (formerly Akzo Nobel India)",
         "INDIGOPNTS": "standalone FY2021-FY2023 (no subsidiary), consolidated FY2024-FY2026"}

RAW_SECTIONS = [
    ("Income statement", ["REV", "COGS", "EBITDA", "OTHINC", "EXCEP", "ONEOFF", "INT", "DEP", "PBT", "PAT", "PATOWN"]),
    ("Balance sheet", ["EQCAP", "RES", "NCI", "BORR", "LEASE", "OTHLIAB", "TOTLIAB", "FA", "CWIP", "INVEST",
                       "OTHASSET", "TA", "INV", "REC", "CASH", "PAY", "CA", "CL", "CASHSTI"]),
    ("Cash flow", ["CFO", "CAPEX"]),
    ("Cross-check lines (not used in ratios; see Checks)", ["REV_CO", "PATOWN_CO", "COGS_SP", "RMC_SCR",
                                                          "PATOWN_SP", "TA_SP", "INV_SP"]),
]
RATIO_GROUPS = ["Profitability", "Liquidity", "Leverage", "Efficiency", "Growth and cash"]
DEFN = {
    "GM": "(Revenue - COGS) / revenue; COGS = materials + purchases of traded goods + inventory change",
    "EBITDAM": "Operating profit before other income / revenue",
    "NPM": "PAT attributable to owners / revenue",
    "NPM_ADJ": "Adjusted PAT / revenue",
    "ROE": "PAT to owners / average owners' equity",
    "ROE_ADJ": "Adjusted PAT / average owners' equity",
    "ROA": "PAT to owners / average total assets",
    "ROCE": "(EBIT - one-offs) / average capital employed",
    "CR": "Current assets / current liabilities",
    "QR": "(Current assets - inventories) / current liabilities",
    "CASHR": "(Cash + short-term investments) / current liabilities",
    "DE": "Borrowings incl. leases / owners' equity (closing)",
    "NDEBITDA": "(Borrowings incl. leases - cash and short-term investments) / EBITDA",
    "ICR": "(EBITDA - depreciation) / finance costs",
    "AT": "Revenue / average total assets",
    "FAT": "Revenue / average net fixed assets",
    "INVD": "Average inventories / COGS x days",
    "RECD": "Average trade receivables / revenue x days",
    "PAYD": "Average trade payables / COGS x days",
    "CCC": "Inventory days + receivable days - payable days",
    "REVG": "Revenue / previous-year revenue - 1",
    "CFOE": "Cash from operations / EBITDA",
    "FCFM": "(Cash from operations - capex) / revenue",
    "OIPBT": "(Other income - one-offs) / PBT; shows reliance on treasury income",
}


def fmt_cell(c, fmt: str, font=C.F_CALC):
    c.number_format = C.FMT[fmt]
    c.font = font


def add_pass_fail_format(ws, rng: str) -> None:
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"PASS"'], fill=FILL_PASS))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"FAIL"'], fill=FILL_FAIL))


# ----------------------------------------------------------------------------------------------- Raw_Data
def build_raw(wb) -> tuple[dict, str]:
    ws = wb.create_sheet("Raw_Data")
    ws["A1"] = "Raw data: Asian Paints and four listed peers, FY2021-FY2026 (Rs crore unless stated)"
    ws["A1"].font = C.F_TITLE
    C.note(ws, 2, 1, "Blue = value typed from the source named in column J. FY2021 is only the opening balance "
                     "sheet for averages. Fiscal year ends 31 March (FY2026 = Apr-2025 to Mar-2026).")
    ws["B4"] = "Days in a year (for working-capital days)"
    ws["B4"].font = C.F_BOLD
    ws["D4"] = 365
    ws["D4"].font = C.F_IN
    ws["E4"] = "Convention: 365-day year"
    ws["E4"].font = C.F_NOTE
    days_ref = "Raw_Data!$D$4"
    hdr = ["Code", "Line item (Rs crore)", "Unit"] + C.FYS + ["Source", "Note"]
    C.style_header(ws, 6, hdr)
    r = 7
    rowmap: dict = {}
    for sym in C.SYMS:
        C.block_title(ws, r, f"{C.NAMES[sym]} ({sym}) - {SCOPE[sym]}", ncols=len(hdr))
        r += 1
        for sec, codes in RAW_SECTIONS:
            C.section_row(ws, r, sec, ncols=len(hdr))
            r += 1
            for code in codes:
                ws.cell(r, 1, code).font = C.F_NOTE
                ws.cell(r, 2, C.label(sym, code)).font = C.F_TXT
                ws.cell(r, 3, "Rs cr").font = C.F_NOTE
                for fy in C.FYS:
                    v = C.val(sym, code, fy)
                    c = ws[f"{C.YCOL[fy]}{r}"]
                    if v is not None:
                        c.value = v
                        c.font = C.F_IN
                        c.number_format = C.FMT["cr"]
                ws.cell(r, 10, C.meta(sym, code, "source")).font = C.F_NOTE
                ws.cell(r, 11, C.meta(sym, code, "note")).font = C.F_NOTE
                rowmap[(sym, code)] = r
                r += 1
        r += 1
    C.set_widths(ws, {"A": 10, "B": 52, "C": 6, "D": 10, "E": 10, "F": 10, "G": 10, "H": 10, "I": 10,
                      "J": 70, "K": 70})
    ws.freeze_panes = "D7"
    return rowmap, days_ref


# ----------------------------------------------------------------------------------------------- Ratios
BB = [  # building blocks: (code, label, fmt, from_FY2021?)
    ("OE", "Owners' equity, closing (share capital + reserves)", "cr", True),
    ("OE_AVG", "Average owners' equity", "cr", False),
    ("TA_AVG", "Average total assets", "cr", False),
    ("CE", "Capital employed, closing (equity + NCI + borrowings incl. leases)", "cr", True),
    ("CE_AVG", "Average capital employed", "cr", False),
    ("FA_AVG", "Average net fixed assets", "cr", False),
    ("INV_AVG", "Average inventories", "cr", False),
    ("REC_AVG", "Average trade receivables", "cr", False),
    ("PAY_AVG", "Average trade payables", "cr", False),
    ("EBIT", "EBIT = PBT + finance costs", "cr", False),
    ("ONE", "One-off items, pre-tax (exceptional + other one-offs; + = gain)", "cr", False),
    ("PATADJ", "Adjusted PAT to owners = PAT to owners - one-offs x (PAT / PBT)", "cr", False),
]


def build_ratios(wb, rm: dict, days: str) -> dict:
    ws = wb.create_sheet("Ratios")
    ws["A1"] = "Ratios by company, FY2022-FY2026 (live formulas on Raw_Data)"
    ws["A1"].font = C.F_TITLE
    C.note(ws, 2, 1, "Averages = (opening + closing) / 2. 'One-offs' = exceptional items + other one-off gains "
                     "(JSW Dulux FY2026 property sale). Adjusted figures remove one-offs at the year's tax rate.")
    hdr = ["Code", "Ratio / building block", "Unit"] + C.FYS + ["5-yr avg", "Better", "Definition"]
    C.style_header(ws, 4, hdr)
    r = 5
    xm: dict = {}

    def R(sym, code, col):
        return f"Raw_Data!{col}{rm[(sym, code)]}"

    for sym in C.SYMS:
        C.block_title(ws, r, f"{C.NAMES[sym]} - {SCOPE[sym]}", ncols=len(hdr))
        r += 1
        C.section_row(ws, r, "Building blocks (Rs crore)", ncols=len(hdr))
        r += 1
        for code, lab, fmt, from21 in BB:
            ws.cell(r, 1, code).font = C.F_NOTE
            ws.cell(r, 2, lab).font = C.F_TXT
            ws.cell(r, 3, "Rs cr").font = C.F_NOTE
            xm[(sym, code)] = r
            cols = COLS_FY if from21 else COLS_R
            for col in cols:
                p = PREV.get(col)
                if code == "OE":
                    f = f"={R(sym, 'EQCAP', col)}+{R(sym, 'RES', col)}"
                elif code == "CE":
                    f = (f"={R(sym, 'EQCAP', col)}+{R(sym, 'RES', col)}+{R(sym, 'NCI', col)}"
                         f"+{R(sym, 'BORR', col)}")
                elif code == "OE_AVG":
                    f = f"=({p}{xm[(sym, 'OE')]}+{col}{xm[(sym, 'OE')]})/2"
                elif code == "CE_AVG":
                    f = f"=({p}{xm[(sym, 'CE')]}+{col}{xm[(sym, 'CE')]})/2"
                elif code in ("TA_AVG", "FA_AVG", "INV_AVG", "REC_AVG", "PAY_AVG"):
                    src = code.replace("_AVG", "")
                    f = f"=({R(sym, src, p)}+{R(sym, src, col)})/2"
                elif code == "EBIT":
                    f = f"={R(sym, 'PBT', col)}+{R(sym, 'INT', col)}"
                elif code == "ONE":
                    f = f"={R(sym, 'EXCEP', col)}+{R(sym, 'ONEOFF', col)}"
                elif code == "PATADJ":
                    f = (f"={R(sym, 'PATOWN', col)}-{col}{xm[(sym, 'ONE')]}*{R(sym, 'PAT', col)}"
                         f"/{R(sym, 'PBT', col)}")
                c = ws[f"{col}{r}"]
                c.value = f
                fmt_cell(c, "cr")
            r += 1
        for grp in RATIO_GROUPS:
            C.section_row(ws, r, grp, ncols=len(hdr))
            r += 1
            for code, lab, g, fmt, better in RE.RATIOS:
                if g != grp:
                    continue
                xm[(sym, code)] = r
                ws.cell(r, 1, code).font = C.F_NOTE
                ws.cell(r, 2, lab).font = C.F_TXT
                ws.cell(r, 3, C.RATIO_UNIT[fmt]).font = C.F_NOTE
                ws.cell(r, 11, {"high": "Higher", "low": "Lower", "": "n/a"}[better]).font = C.F_NOTE
                ws.cell(r, 12, DEFN[code]).font = C.F_NOTE
                r += 1
        # second pass: formulas (rows of all ratios now known)
        for code, lab, g, fmt, better in RE.RATIOS:
            rr = xm[(sym, code)]
            for col in COLS_R:
                p = PREV[col]
                X = lambda k: f"{col}{xm[(sym, k)]}"  # noqa: E731  (same-sheet building block / ratio)
                f = {
                    "GM": f"=({R(sym, 'REV', col)}-{R(sym, 'COGS', col)})/{R(sym, 'REV', col)}",
                    "EBITDAM": f"={R(sym, 'EBITDA', col)}/{R(sym, 'REV', col)}",
                    "NPM": f"={R(sym, 'PATOWN', col)}/{R(sym, 'REV', col)}",
                    "NPM_ADJ": f"={X('PATADJ')}/{R(sym, 'REV', col)}",
                    "ROE": f"={R(sym, 'PATOWN', col)}/{X('OE_AVG')}",
                    "ROE_ADJ": f"={X('PATADJ')}/{X('OE_AVG')}",
                    "ROA": f"={R(sym, 'PATOWN', col)}/{X('TA_AVG')}",
                    "ROCE": f"=({X('EBIT')}-{X('ONE')})/{X('CE_AVG')}",
                    "CR": f"={R(sym, 'CA', col)}/{R(sym, 'CL', col)}",
                    "QR": f"=({R(sym, 'CA', col)}-{R(sym, 'INV', col)})/{R(sym, 'CL', col)}",
                    "CASHR": f"={R(sym, 'CASHSTI', col)}/{R(sym, 'CL', col)}",
                    "DE": f"={R(sym, 'BORR', col)}/{col}{xm[(sym, 'OE')]}",
                    "NDEBITDA": f"=({R(sym, 'BORR', col)}-{R(sym, 'CASHSTI', col)})/{R(sym, 'EBITDA', col)}",
                    "ICR": f"=({R(sym, 'EBITDA', col)}-{R(sym, 'DEP', col)})/{R(sym, 'INT', col)}",
                    "AT": f"={R(sym, 'REV', col)}/{X('TA_AVG')}",
                    "FAT": f"={R(sym, 'REV', col)}/{X('FA_AVG')}",
                    "INVD": f"={X('INV_AVG')}/{R(sym, 'COGS', col)}*{days}",
                    "RECD": f"={X('REC_AVG')}/{R(sym, 'REV', col)}*{days}",
                    "PAYD": f"={X('PAY_AVG')}/{R(sym, 'COGS', col)}*{days}",
                    "CCC": f"={X('INVD')}+{X('RECD')}-{X('PAYD')}",
                    "REVG": f"={R(sym, 'REV', col)}/{R(sym, 'REV', p)}-1",
                    "CFOE": f"={R(sym, 'CFO', col)}/{R(sym, 'EBITDA', col)}",
                    "FCFM": f"=({R(sym, 'CFO', col)}-{R(sym, 'CAPEX', col)})/{R(sym, 'REV', col)}",
                    "OIPBT": f"=({R(sym, 'OTHINC', col)}-{X('ONE')})/{R(sym, 'PBT', col)}",
                }[code]
                c = ws[f"{col}{rr}"]
                c.value = f
                fmt_cell(c, fmt)
            c = ws[f"J{rr}"]
            c.value = f"=AVERAGE(E{rr}:I{rr})"
            fmt_cell(c, fmt, C.F_CALC_B)
        r += 1
    C.set_widths(ws, {"A": 10, "B": 56, "C": 6, "D": 9, "E": 10, "F": 10, "G": 10, "H": 10, "I": 10, "J": 10,
                      "K": 8, "L": 80})
    ws.freeze_panes = "D5"
    return xm


# ----------------------------------------------------------------------------------------------- DuPont
def build_dupont(wb, rm: dict, xm: dict) -> dict:
    ws = wb.create_sheet("DuPont")
    ws["A1"] = "DuPont analysis: what drives each company's ROE (FY2022-FY2026)"
    ws["A1"].font = C.F_TITLE
    C.note(ws, 2, 1, "3-step: ROE = net margin x asset turnover x equity multiplier. 5-step: ROE = tax burden x "
                     "interest burden x EBIT margin x asset turnover x equity multiplier. EBIT = PBT + finance costs.")
    hdr = ["Code", "Component", "Unit"] + C.FYS + ["5-yr avg"]
    C.style_header(ws, 4, hdr)
    r = 5
    dm: dict = {}
    for sym in C.SYMS:
        C.block_title(ws, r, C.NAMES[sym], ncols=len(hdr))
        r += 1
        rows = [("D3_NPM", "Net profit margin (PAT to owners / revenue)", "pct"),
                ("D3_AT", "x Asset turnover (revenue / average total assets)", "x"),
                ("D3_EM", "x Equity multiplier (average total assets / average owners' equity)", "x"),
                ("D3_ROE", "Product of the 3 factors (= ROE)", "pct"),
                ("D3_REF", "ROE on the Ratios sheet", "pct"),
                ("D3_DIFF", "Difference (must be 0)", "pct"),
                (None, "5-step", None),
                ("D5_TB", "Tax burden (PAT to owners / PBT)", "x"),
                ("D5_IB", "x Interest burden (PBT / EBIT)", "x"),
                ("D5_EBITM", "x EBIT margin (EBIT / revenue)", "pct"),
                ("D5_AT", "x Asset turnover", "x"),
                ("D5_EM", "x Equity multiplier", "x"),
                ("D5_ROE", "Product of the 5 factors (= ROE)", "pct"),
                ("D5_REF", "ROE on the Ratios sheet", "pct"),
                ("D5_DIFF", "Difference (must be 0)", "pct")]
        C.section_row(ws, r, "3-step", ncols=len(hdr))
        r += 1
        for code, lab, fmt in rows:
            if code is None:
                C.section_row(ws, r, lab, ncols=len(hdr))
                r += 1
                continue
            dm[(sym, code)] = r
            ws.cell(r, 1, code).font = C.F_NOTE
            assert not lab.startswith("="), lab  # a leading '=' would be written as a formula
            ws.cell(r, 2, lab).font = C.F_BOLD if code.endswith("ROE") else C.F_TXT
            ws.cell(r, 3, C.RATIO_UNIT[fmt]).font = C.F_NOTE
            r += 1
        for col in COLS_R:
            D = lambda k: f"{col}{dm[(sym, k)]}"  # noqa: E731
            Rt = lambda k: f"Ratios!{col}{xm[(sym, k)]}"  # noqa: E731
            Rw = lambda k: f"Raw_Data!{col}{rm[(sym, k)]}"  # noqa: E731
            spec = {
                "D3_NPM": (f"={Rt('NPM')}", "pct", C.F_LINK),
                "D3_AT": (f"={Rt('AT')}", "x", C.F_LINK),
                "D3_EM": (f"={Rt('TA_AVG')}/{Rt('OE_AVG')}", "x", C.F_CALC),
                "D3_ROE": (f"={D('D3_NPM')}*{D('D3_AT')}*{D('D3_EM')}", "pct", C.F_CALC_B),
                "D3_REF": (f"={Rt('ROE')}", "pct", C.F_LINK),
                "D3_DIFF": (f"={D('D3_ROE')}-{D('D3_REF')}", "pct", C.F_CALC),
                "D5_TB": (f"={Rw('PATOWN')}/{Rw('PBT')}", "x", C.F_CALC),
                "D5_IB": (f"={Rw('PBT')}/{Rt('EBIT')}", "x", C.F_CALC),
                "D5_EBITM": (f"={Rt('EBIT')}/{Rw('REV')}", "pct", C.F_CALC),
                "D5_AT": (f"={D('D3_AT')}", "x", C.F_CALC),
                "D5_EM": (f"={D('D3_EM')}", "x", C.F_CALC),
                "D5_ROE": (f"={D('D5_TB')}*{D('D5_IB')}*{D('D5_EBITM')}*{D('D5_AT')}*{D('D5_EM')}", "pct",
                           C.F_CALC_B),
                "D5_REF": (f"={Rt('ROE')}", "pct", C.F_LINK),
                "D5_DIFF": (f"={D('D5_ROE')}-{D('D5_REF')}", "pct", C.F_CALC),
            }
            for code, (f, fmt, font) in spec.items():
                c = ws[f"{col}{dm[(sym, code)]}"]
                c.value = f
                fmt_cell(c, fmt, font)
                if code.endswith("DIFF"):
                    c.number_format = "0.000000%"
        for code, (_f, fmt, _font) in spec.items():
            rr = dm[(sym, code)]
            c = ws[f"J{rr}"]
            c.value = f"=AVERAGE(E{rr}:I{rr})"
            fmt_cell(c, fmt, C.F_CALC_B)
            if code.endswith("DIFF"):
                c.number_format = "0.000000%"
        r += 1
    # summary table for FY2026
    C.block_title(ws, r, "FY2026 DuPont summary (links to the blocks above)", ncols=len(hdr))
    r += 1
    sh = ["Component"] + [C.NAMES[s] for s in C.SYMS]
    for i, h in enumerate(sh):
        c = ws.cell(r, 2 + i, h)
        c.font, c.fill = C.F_HDR, C.FILL_HDR
        c.alignment = C.CENTER
    r += 1
    dm["summary_start"] = r
    for code, lab, fmt in [("D5_TB", "Tax burden", "x"), ("D5_IB", "Interest burden", "x"),
                           ("D5_EBITM", "EBIT margin", "pct"), ("D3_NPM", "Net profit margin", "pct"),
                           ("D3_AT", "Asset turnover", "x"), ("D3_EM", "Equity multiplier", "x"),
                           ("D3_ROE", "ROE", "pct")]:
        ws.cell(r, 2, lab).font = C.F_TXT
        for i, sym in enumerate(C.SYMS):
            c = ws.cell(r, 3 + i, f"={LAST}{dm[(sym, code)]}")
            fmt_cell(c, fmt, C.F_CALC)
        dm[("summary", code)] = r
        r += 1
    C.set_widths(ws, {"A": 10, "B": 62, "C": 14, "D": 14, "E": 14, "F": 14, "G": 14, "H": 10, "I": 10, "J": 10})
    ws.freeze_panes = "D5"
    return dm


# ----------------------------------------------------------------------------------------------- Peer_Comparison
def build_peer(wb, rm: dict, xm: dict) -> dict:
    ws = wb.create_sheet("Peer_Comparison")
    ws["A1"] = "Peer comparison and ranking (1 = best of the five)"
    ws["A1"].font = C.F_TITLE
    C.note(ws, 2, 1, "Peer median excludes Asian Paints. Ranks use RANK(); ties share the better rank. "
                     "Ratios with no 'better' direction are shown but not ranked.")
    ws["B3"] = "Ranking basis used for the verdict on Cover and Conclusion"
    ws["B3"].font = C.F_BOLD
    ws["D3"] = "FY2026"
    ws["D3"].font = C.F_IN
    ws["D3"].fill = C.FILL_YEL
    ws["E3"] = ("Judgment: choose 'FY2026' (latest year) or '5-year average' (through-cycle view). "
                "FY2026 is the default because it reflects the market after Birla Opus entered.")
    ws["E3"].font = C.F_NOTE
    dv = DataValidation(type="list", formula1='"FY2026,5-year average"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("D3")
    pm: dict = {"basis": "Peer_Comparison!$D$3"}
    names = [C.NAMES[s] for s in C.SYMS]
    hdr = ["Code", "Ratio", "Better"] + names + ["Peer median", "AP minus median"] + [f"Rank {n}" for n in names]
    r = 5
    for basis, col_src, title in [("FY2026", LAST, "A. Latest year: FY2026"),
                                  ("AVG5", "J", "B. Five-year average, FY2022-FY2026 (growth = revenue CAGR FY2021-26)")]:
        C.block_title(ws, r, title, ncols=len(hdr))
        r += 1
        C.style_header(ws, r, hdr)
        r += 1
        pm[(basis, "first")] = r
        for code, lab, grp, fmt, better in RE.RATIOS:
            pm[(basis, code)] = r
            ws.cell(r, 1, code).font = C.F_NOTE
            ws.cell(r, 2, ("Revenue CAGR FY2021-26" if (basis == "AVG5" and code == "REVG") else lab)).font = C.F_TXT
            ws.cell(r, 3, {"high": "Higher", "low": "Lower", "": "n/a"}[better]).font = C.F_NOTE
            for i, sym in enumerate(C.SYMS):
                col = 4 + i
                if basis == "AVG5" and code == "REVG":
                    f = (f"=(Raw_Data!{LAST}{rm[(sym, 'REV')]}/Raw_Data!D{rm[(sym, 'REV')]})^(1/5)-1")
                    font = C.F_CALC
                else:
                    f = f"=Ratios!{col_src}{xm[(sym, code)]}"
                    font = C.F_LINK
                c = ws.cell(r, col, f)
                fmt_cell(c, fmt, font)
                if sym == "ASIANPAINT":
                    c.fill = C.FILL_AP
            c = ws.cell(r, 9, f"=MEDIAN(E{r}:H{r})")
            fmt_cell(c, fmt)
            c = ws.cell(r, 10, f"=D{r}-I{r}")
            fmt_cell(c, fmt)
            if better:
                order = 0 if better == "high" else 1
                for i in range(5):
                    colL = "DEFGH"[i]
                    c = ws.cell(r, 11 + i, f"=RANK({colL}{r},$D{r}:$H{r},{order})")
                    fmt_cell(c, "rank")
                    c.alignment = C.CENTER
            r += 1
        pm[(basis, "last")] = r - 1
        r += 1
    # Scorecard
    C.block_title(ws, r, "C. Weighted scorecard (weights are judgment inputs; must sum to 100%)", ncols=len(hdr))
    r += 1
    sh = ["Code", "Metric", "Weight"] + [f"FY2026 rank: {n}" for n in names] + [f"5-yr rank: {n}" for n in names] \
        + ["Why this weight"]
    C.style_header(ws, r, sh, height=42)
    r += 1
    first = r
    for code, (w, why) in RE.SCORECARD.items():
        ws.cell(r, 1, code).font = C.F_NOTE
        ws.cell(r, 2, C.RATIO_LABEL[code] if code != "REVG" else "Revenue growth (FY2026) / CAGR (5-yr)").font = C.F_TXT
        c = ws.cell(r, 3, w)
        c.font, c.fill, c.number_format = C.F_IN, C.FILL_YEL, "0.0%"
        for i, sym in enumerate(C.SYMS):
            c = ws.cell(r, 4 + i, f"={'KLMNO'[i]}{pm[('FY2026', code)]}")
            fmt_cell(c, "rank", C.F_CALC)
            c.alignment = C.CENTER
            c = ws.cell(r, 9 + i, f"={'KLMNO'[i]}{pm[('AVG5', code)]}")
            fmt_cell(c, "rank", C.F_CALC)
            c.alignment = C.CENTER
        ws.cell(r, 14, why).font = C.F_NOTE
        pm[("score_row", code)] = r
        r += 1
    last = r - 1
    pm["weights"] = f"Peer_Comparison!$C${first}:$C${last}"
    ws.cell(r, 2, "Total weight").font = C.F_BOLD
    c = ws.cell(r, 3, f"=SUM(C{first}:C{last})")
    c.number_format, c.font = "0.0%", C.F_CALC_B
    pm["weight_total"] = f"Peer_Comparison!$C${r}"
    r += 1
    ws.cell(r, 2, "Weighted average rank (lower = stronger)").font = C.F_BOLD
    for i in range(5):
        L1, L2 = "DEFGH"[i], "IJKLM"[i]
        c = ws.cell(r, 4 + i, f"=SUMPRODUCT($C${first}:$C${last},{L1}{first}:{L1}{last})/SUM($C${first}:$C${last})")
        fmt_cell(c, "score", C.F_CALC_B)
        c = ws.cell(r, 9 + i, f"=SUMPRODUCT($C${first}:$C${last},{L2}{first}:{L2}{last})/SUM($C${first}:$C${last})")
        fmt_cell(c, "score", C.F_CALC_B)
    pm["score_r"] = r
    r += 1
    ws.cell(r, 2, "Overall position (1 = strongest)").font = C.F_BOLD
    sr = pm["score_r"]
    for i in range(5):
        L1, L2 = "DEFGH"[i], "IJKLM"[i]
        c = ws.cell(r, 4 + i, f"=RANK({L1}{sr},$D${sr}:$H${sr},1)")
        fmt_cell(c, "rank", C.F_CALC_B)
        c.alignment = C.CENTER
        c = ws.cell(r, 9 + i, f"=RANK({L2}{sr},$I${sr}:$M${sr},1)")
        fmt_cell(c, "rank", C.F_CALC_B)
        c.alignment = C.CENTER
    pm["pos_r"] = r
    r += 2
    # selected basis summary
    C.block_title(ws, r, "D. Result on the selected basis (cell D3)", ncols=len(hdr))
    r += 1
    for i, h in enumerate(["", "Company", "Weighted rank", "Position"]):
        c = ws.cell(r, 1 + i, h)
        if h:
            c.font, c.fill = C.F_HDR, C.FILL_HDR
    r += 1
    pm["sel_first"] = r
    for i, sym in enumerate(C.SYMS):
        ws.cell(r, 2, C.NAMES[sym]).font = C.F_TXT
        L1, L2 = "DEFGH"[i], "IJKLM"[i]
        c = ws.cell(r, 3, f'=IF($D$3="FY2026",{L1}{sr},{L2}{sr})')
        fmt_cell(c, "score", C.F_CALC_B)
        c = ws.cell(r, 4, f'=IF($D$3="FY2026",{L1}{pm["pos_r"]},{L2}{pm["pos_r"]})')
        fmt_cell(c, "rank", C.F_CALC_B)
        pm[("sel", sym)] = r
        r += 1
    pm["sel_last"] = r - 1
    ws.cell(r, 2, "Strongest on the selected basis").font = C.F_BOLD
    c = ws.cell(r, 3, f"=INDEX(B{pm['sel_first']}:B{pm['sel_last']},MATCH(1,D{pm['sel_first']}:D{pm['sel_last']},0))")
    c.font = C.F_CALC_B
    pm["winner"] = f"Peer_Comparison!$C${r}"
    r += 2
    notes = [
        "Reading the table: JSW Dulux's FY2026 reported ROE (104%), ROA and net margin include a Rs 1,846 cr gain on "
        "the slump sale of its Powder Coatings and research divisions; use the 'excl. one-off items' rows.",
        "JSW Dulux FY2026 capex and fixed assets include Rs 1,152 cr of intangible assets bought in the year (cash "
        "flow statement), which lowers its fixed-asset turnover and free cash flow for that year.",
        "Kansai Nerolac FY2024-FY2025 profits include gains on selling investment property (Rs 661 cr and Rs 630 cr).",
        "All five companies hold more cash and liquid investments than debt in FY2026 (net debt / EBITDA below zero).",
    ]
    for t in notes:
        C.note(ws, r, 2, t)
        r += 1
    C.set_widths(ws, {"A": 10, "B": 50, "C": 9, "D": 11, "E": 11, "F": 11, "G": 11, "H": 11, "I": 11, "J": 11,
                      "K": 11, "L": 11, "M": 11, "N": 11, "O": 11})
    ws.freeze_panes = "D5"
    return pm


# ----------------------------------------------------------------------------------------------- Charts
def build_charts(wb, xm: dict) -> None:
    ws = wb.create_sheet("Charts")
    ws["A1"] = "Charts (data block on the left links to the Ratios sheet)"
    ws["A1"].font = C.F_TITLE
    names = [C.NAMES[s] for s in C.SYMS]
    # block 1: FY2026 returns
    ws["A3"] = "FY2026 returns"
    ws["A3"].font = C.F_BOLD
    for j, h in enumerate(["Company", "ROE excl. one-offs", "ROCE", "ROE reported"]):
        ws.cell(4, 1 + j, h).font = C.F_BOLD
    for i, sym in enumerate(C.SYMS):
        ws.cell(5 + i, 1, names[i])
        for j, code in enumerate(["ROE_ADJ", "ROCE", "ROE"]):
            c = ws.cell(5 + i, 2 + j, f"=Ratios!{LAST}{xm[(sym, code)]}")
            fmt_cell(c, "pct", C.F_LINK)
    ch = BarChart()
    ch.type = "col"
    ch.title = "FY2026 returns: ROE excl. one-offs and ROCE"
    ch.y_axis.title = "%"
    ch.y_axis.number_format = "0%"
    ch.add_data(Reference(ws, min_col=2, min_row=4, max_col=3, max_row=9), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=9))
    ch.height, ch.width = 7.5, 16
    ws.add_chart(ch, "G3")
    # block 2: EBITDA margin trend
    ws["A12"] = "EBITDA margin by year"
    ws["A12"].font = C.F_BOLD
    ws.cell(13, 1, "Year").font = C.F_BOLD
    for i, n in enumerate(names):
        ws.cell(13, 2 + i, n).font = C.F_BOLD
    for k, fy in enumerate(C.RFYS):
        ws.cell(14 + k, 1, fy)
        for i, sym in enumerate(C.SYMS):
            c = ws.cell(14 + k, 2 + i, f"=Ratios!{C.YCOL[fy]}{xm[(sym, 'EBITDAM')]}")
            fmt_cell(c, "pct", C.F_LINK)
    ch = LineChart()
    ch.title = "EBITDA margin (before other income), FY2022-FY2026"
    ch.y_axis.title = "% of revenue"
    ch.y_axis.number_format = "0%"
    ch.add_data(Reference(ws, min_col=2, min_row=13, max_col=6, max_row=18), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=14, max_row=18))
    ch.height, ch.width = 7.5, 16
    ws.add_chart(ch, "G19")
    # block 3: gross margin trend
    ws["A21"] = "Gross margin by year"
    ws["A21"].font = C.F_BOLD
    ws.cell(22, 1, "Year").font = C.F_BOLD
    for i, n in enumerate(names):
        ws.cell(22, 2 + i, n).font = C.F_BOLD
    for k, fy in enumerate(C.RFYS):
        ws.cell(23 + k, 1, fy)
        for i, sym in enumerate(C.SYMS):
            c = ws.cell(23 + k, 2 + i, f"=Ratios!{C.YCOL[fy]}{xm[(sym, 'GM')]}")
            fmt_cell(c, "pct", C.F_LINK)
    ch = LineChart()
    ch.title = "Gross margin, FY2022-FY2026"
    ch.y_axis.title = "% of revenue"
    ch.y_axis.number_format = "0%"
    ch.add_data(Reference(ws, min_col=2, min_row=22, max_col=6, max_row=27), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=23, max_row=27))
    ch.height, ch.width = 7.5, 16
    ws.add_chart(ch, "G35")
    # block 4: working capital FY2026
    ws["A30"] = "FY2026 working-capital days"
    ws["A30"].font = C.F_BOLD
    for j, h in enumerate(["Company", "Inventory days", "Receivable days", "Payable days", "Cash conversion cycle"]):
        ws.cell(31, 1 + j, h).font = C.F_BOLD
    for i, sym in enumerate(C.SYMS):
        ws.cell(32 + i, 1, names[i])
        for j, code in enumerate(["INVD", "RECD", "PAYD", "CCC"]):
            c = ws.cell(32 + i, 2 + j, f"=Ratios!{LAST}{xm[(sym, code)]}")
            fmt_cell(c, "days", C.F_LINK)
    ch = BarChart()
    ch.type = "col"
    ch.title = "FY2026 working-capital days"
    ch.y_axis.title = "Days"
    ch.add_data(Reference(ws, min_col=2, min_row=31, max_col=5, max_row=36), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=32, max_row=36))
    ch.height, ch.width = 7.5, 16
    ws.add_chart(ch, "G51")
    C.set_widths(ws, {"A": 18, "B": 14, "C": 14, "D": 14, "E": 14, "F": 14})


# ----------------------------------------------------------------------------------------------- Checks
def build_checks(wb, rm: dict, dm: dict, pm: dict) -> dict:
    ws = wb.create_sheet("Checks")
    ws["A1"] = "Checks (every row must say PASS)"
    ws["A1"].font = C.F_TITLE
    C.note(ws, 2, 1, "Differences in Rs crore unless stated. Screener rounds to Rs 1 crore, so balance-sheet "
                     "additions allow Rs 2 crore of rounding.")
    hdr = ["#", "Check", "Company"] + C.FYS + ["Result", "Tolerance / note"]
    C.style_header(ws, 4, hdr)
    r = 5
    n = 0
    res_rows = []

    def R(sym, code, col):
        return f"Raw_Data!{col}{rm[(sym, code)]}"

    def add_row(name, sym_name, cells: dict, tol_expr: str, tol_note: str, pct=False, cols=COLS_FY):
        nonlocal r, n
        n += 1
        ws.cell(r, 1, n).font = C.F_NOTE
        ws.cell(r, 2, name).font = C.F_TXT
        ws.cell(r, 3, sym_name).font = C.F_TXT
        for col, f in cells.items():
            c = ws[f"{col}{r}"]
            c.value = f
            c.number_format = "0.00%" if pct else "#,##0.0"
            c.font = C.F_CALC
        rng = f"{cols[0]}{r}:{cols[-1]}{r}"
        ws[f"J{r}"] = f'=IF(SUMPRODUCT(--(ABS({rng})>{tol_expr}))=0,"PASS","FAIL")'
        ws[f"J{r}"].font = C.F_CALC_B
        ws[f"J{r}"].alignment = C.CENTER
        ws[f"K{r}"] = tol_note
        ws[f"K{r}"].font = C.F_NOTE
        res_rows.append(r)
        r += 1

    C.section_row(ws, r, "1. Balance sheets add up and balance (Screener statements)", ncols=len(hdr))
    r += 1
    for sym in C.SYMS:
        add_row("Liabilities side: equity + borrowings + other liabilities - total", C.NAMES[sym],
                {col: f"={R(sym, 'EQCAP', col)}+{R(sym, 'RES', col)}+{R(sym, 'BORR', col)}+{R(sym, 'OTHLIAB', col)}"
                      f"-{R(sym, 'TOTLIAB', col)}" for col in COLS_FY}, "2", "|difference| <= Rs 2 cr each year")
        add_row("Assets side: fixed assets + CWIP + investments + other assets - total", C.NAMES[sym],
                {col: f"={R(sym, 'FA', col)}+{R(sym, 'CWIP', col)}+{R(sym, 'INVEST', col)}+{R(sym, 'OTHASSET', col)}"
                      f"-{R(sym, 'TA', col)}" for col in COLS_FY}, "2", "|difference| <= Rs 2 cr each year")
        add_row("Balance sheet balances: total assets - total liabilities and equity", C.NAMES[sym],
                {col: f"={R(sym, 'TA', col)}-{R(sym, 'TOTLIAB', col)}" for col in COLS_FY}, "0.5", "must be 0")
    C.section_row(ws, r, "2. DuPont products equal ROE", ncols=len(hdr))
    r += 1
    for sym in C.SYMS:
        for code, lab in [("D3_DIFF", "3-step product - ROE"), ("D5_DIFF", "5-step product - ROE")]:
            add_row(lab, C.NAMES[sym], {col: f"=DuPont!{col}{dm[(sym, code)]}" for col in COLS_R}, "0.0000001",
                    "|difference| < 0.00001%", pct=True, cols=COLS_R)
    C.section_row(ws, r, "3. Inputs agree across sources (gap as % of the base line, FY2022-FY2026)", ncols=len(hdr))
    r += 1
    for sym in C.SYMS:
        add_row("Revenue: Screener vs company filing (% of revenue)", C.NAMES[sym],
                {col: f"=({R(sym, 'REV_CO', col)}-{R(sym, 'REV', col)})/{R(sym, 'REV', col)}" for col in COLS_R},
                "0.005", "< 0.5%", pct=True, cols=COLS_R)
        add_row("COGS: company filing vs S&P cost of revenue (% of revenue)", C.NAMES[sym],
                {col: f"=({R(sym, 'COGS_SP', col)}-{R(sym, 'COGS', col)})/{R(sym, 'REV', col)}" for col in COLS_R},
                "0.025", "< 2.5% of revenue (S&P books some costs differently)", pct=True, cols=COLS_R)
        add_row("PAT to owners: Screener vs S&P (% of PAT)", C.NAMES[sym],
                {col: f"=({R(sym, 'PATOWN_SP', col)}-{R(sym, 'PATOWN', col)})/{R(sym, 'PATOWN', col)}"
                 for col in COLS_R}, "0.01", "< 1%", pct=True, cols=COLS_R)
        add_row("PAT to owners: Screener vs company filing, FY2025-26 (% of PAT)", C.NAMES[sym],
                {col: f"=({R(sym, 'PATOWN_CO', col)}-{R(sym, 'PATOWN', col)})/{R(sym, 'PATOWN', col)}"
                 for col in ["H", "I"]}, "0.005", "< 0.5%", pct=True, cols=["H", "I"])
        add_row("Total assets: Screener vs S&P (% of total assets)", C.NAMES[sym],
                {col: f"=({R(sym, 'TA_SP', col)}-{R(sym, 'TA', col)})/{R(sym, 'TA', col)}" for col in COLS_R},
                "0.01", "< 1%", pct=True, cols=COLS_R)
        add_row("Inventories: Screener vs S&P (% of inventories)", C.NAMES[sym],
                {col: f"=({R(sym, 'INV_SP', col)}-{R(sym, 'INV', col)})/{R(sym, 'INV', col)}" for col in COLS_R},
                "0.01", "< 1%", pct=True, cols=COLS_R)
    C.section_row(ws, r, "4. Asian Paints FY2026 inputs vs the audited results (data/company_reported_checks.csv)",
                  ncols=len(hdr))
    r += 1
    item_code = {"Revenue from operations": "REV", "Profit attributable to owners": "PATOWN", "Total assets": "TA",
                 "Total current assets": "CA", "Total current liabilities": "CL"}
    for _, row in C.COMPANY_CHECKS.iterrows():
        it = str(row["item"])
        if it.startswith("COGS"):
            expr = f"={R('ASIANPAINT', 'COGS', LAST)}"
        elif it == "Equity attributable to owners":
            expr = f"={R('ASIANPAINT', 'EQCAP', LAST)}+{R('ASIANPAINT', 'RES', LAST)}"
        elif it in item_code:
            expr = f"={R('ASIANPAINT', item_code[it], LAST)}"
        else:
            continue
        n += 1
        ws.cell(r, 1, n).font = C.F_NOTE
        ws.cell(r, 2, f"{it[:60]}: workbook vs filing").font = C.F_TXT
        ws.cell(r, 3, "Asian Paints").font = C.F_TXT
        ws[f"G{r}"] = float(row["value_rs_cr"])
        ws[f"G{r}"].font, ws[f"G{r}"].number_format = C.F_IN, "#,##0.00"
        ws[f"H{r}"] = expr
        ws[f"H{r}"].font, ws[f"H{r}"].number_format = C.F_LINK, "#,##0.00"
        ws[f"I{r}"] = f"=(H{r}-G{r})/G{r}"
        ws[f"I{r}"].font, ws[f"I{r}"].number_format = C.F_CALC, "0.00%"
        ws[f"J{r}"] = f'=IF(ABS(I{r})<0.005,"PASS","FAIL")'
        ws[f"J{r}"].font, ws[f"J{r}"].alignment = C.F_CALC_B, C.CENTER
        ws[f"K{r}"] = f"G = filing ({row['where_in_file']}), H = workbook, I = gap; < 0.5%"
        ws[f"K{r}"].font = C.F_NOTE
        res_rows.append(r)
        r += 1
    C.section_row(ws, r, "5. Workbook integrity", ncols=len(hdr))
    r += 1
    integ = [
        ("No error values on Raw_Data", '=SUMPRODUCT(--ISERROR(Raw_Data!A1:K400))'),
        ("No error values on Ratios", '=SUMPRODUCT(--ISERROR(Ratios!A1:L500))'),
        ("No error values on DuPont", '=SUMPRODUCT(--ISERROR(DuPont!A1:J200))'),
        ("No error values on Peer_Comparison", '=SUMPRODUCT(--ISERROR(Peer_Comparison!A1:O120))'),
        ("No error values on Charts", '=SUMPRODUCT(--ISERROR(Charts!A1:F40))'),
        ("No error values on Conclusion", '=SUMPRODUCT(--ISERROR(Conclusion!A1:H60))'),
        ("Key ratio inputs complete FY2022-26 (blank cells)", None),
        ("Scorecard weights sum to 100%", f"=ABS({pm['weight_total']}-1)"),
    ]
    blanks = "+".join(f"COUNTBLANK(Raw_Data!E{rm[(s, k)]}:I{rm[(s, k)]})" for s in C.SYMS
                      for k in ["REV", "COGS", "EBITDA", "PBT", "PATOWN", "TA", "INV", "REC", "PAY", "CA", "CL",
                                "CASHSTI", "CFO", "CAPEX", "BORR", "EQCAP", "RES", "FA"])
    for name, f in integ:
        n += 1
        ws.cell(r, 1, n).font = C.F_NOTE
        ws.cell(r, 2, name).font = C.F_TXT
        ws.cell(r, 3, "All").font = C.F_TXT
        ws[f"I{r}"] = f if f else f"={blanks}"
        ws[f"I{r}"].font = C.F_CALC
        ws[f"J{r}"] = f'=IF(I{r}<0.000001,"PASS","FAIL")'
        ws[f"J{r}"].font, ws[f"J{r}"].alignment = C.F_CALC_B, C.CENTER
        ws[f"K{r}"] = "count / difference must be 0"
        ws[f"K{r}"].font = C.F_NOTE
        res_rows.append(r)
        r += 1
    r += 1
    ws.cell(r, 2, "Checks passed").font = C.F_BOLD
    ws[f"I{r}"] = f'=COUNTIF(J5:J{r - 2},"PASS")'
    ws[f"I{r}"].font = C.F_CALC_B
    cm = {"passed": f"Checks!$I${r}"}
    r += 1
    ws.cell(r, 2, "Checks in total").font = C.F_BOLD
    ws[f"I{r}"] = f'=COUNTA(J5:J{r - 3})'
    ws[f"I{r}"].font = C.F_CALC_B
    cm["total"] = f"Checks!$I${r}"
    r += 1
    ws.cell(r, 2, "OVERALL").font = Font(name="Calibri", size=12, bold=True)
    ws[f"J{r}"] = f'=IF(COUNTIF(J5:J{r - 4},"FAIL")=0,"PASS","FAIL")'
    ws[f"J{r}"].font = Font(name="Calibri", size=12, bold=True)
    ws[f"J{r}"].alignment = C.CENTER
    cm["overall"] = f"Checks!$J${r}"
    add_pass_fail_format(ws, f"J5:J{r}")
    C.set_widths(ws, {"A": 5, "B": 62, "C": 15, "D": 10, "E": 10, "F": 10, "G": 11, "H": 11, "I": 10, "J": 9,
                      "K": 70})
    ws.freeze_panes = "D5"
    cm["n_rows"] = len(res_rows)
    return cm


# ----------------------------------------------------------------------------------------------- Conclusion
def build_conclusion(wb, xm: dict, dm: dict, pm: dict) -> None:
    ws = wb.create_sheet("Conclusion")
    ws["A1"] = "Conclusion: which paint company is strongest, and why"
    ws["A1"].font = C.F_TITLE
    ws["A3"] = (f'="Verdict: on the weighted scorecard ("&{pm["basis"]}&" basis, Peer_Comparison section C), '
                f'the strongest company is "&{pm["winner"]}&"."')
    ws["A3"].font = Font(name="Calibri", size=12, bold=True, color="1F3864")
    ws.merge_cells("A3:H3")
    # evidence table
    hdr = ["Metric (FY2026 unless stated)"] + [C.NAMES[s] for s in C.SYMS] + ["Peer median", "AP rank"]
    C.style_header(ws, 5, hdr)
    metrics = ["ROE_ADJ", "ROCE", "EBITDAM", "GM", "NPM_ADJ", "AT", "CCC", "CFOE", "FCFM", "REVG", "NDEBITDA"]
    r = 6
    for code in metrics:
        pr = pm[("FY2026", code)]
        ws.cell(r, 1, C.RATIO_LABEL[code]).font = C.F_TXT
        for i in range(5):
            c = ws.cell(r, 2 + i, f"=Peer_Comparison!{'DEFGH'[i]}{pr}")
            fmt_cell(c, C.RATIO_FMT[code], C.F_LINK)
            if i == 0:
                c.fill = C.FILL_AP
        c = ws.cell(r, 7, f"=Peer_Comparison!I{pr}")
        fmt_cell(c, C.RATIO_FMT[code], C.F_LINK)
        c = ws.cell(r, 8, f"=Peer_Comparison!K{pr}")
        fmt_cell(c, "rank", C.F_LINK)
        c.alignment = C.CENTER
        r += 1
    # 5-year rows
    for code, lab in [("ROE_ADJ", "ROE excl. one-offs, 5-yr average"), ("ROCE", "ROCE, 5-yr average"),
                      ("REVG", "Revenue CAGR FY2021-26")]:
        pr = pm[("AVG5", code)]
        ws.cell(r, 1, lab).font = C.F_TXT
        for i in range(5):
            c = ws.cell(r, 2 + i, f"=Peer_Comparison!{'DEFGH'[i]}{pr}")
            fmt_cell(c, "pct", C.F_LINK)
            if i == 0:
                c.fill = C.FILL_AP
        c = ws.cell(r, 7, f"=Peer_Comparison!I{pr}")
        fmt_cell(c, "pct", C.F_LINK)
        c = ws.cell(r, 8, f"=Peer_Comparison!K{pr}")
        fmt_cell(c, "rank", C.F_LINK)
        c.alignment = C.CENTER
        r += 1
    r += 1
    ap = "ASIANPAINT"
    T = lambda sym, code, col=LAST, f="0.0%": f'TEXT(Ratios!{col}{xm[(sym, code)]},"{f}")'  # noqa: E731
    paras = [
        ("Why Asian Paints comes out on top",
         f'="Returns. Asian Paints earned the highest ROE excluding one-offs ("&{T(ap, "ROE_ADJ")}&") and the highest '
         f'ROCE ("&{T(ap, "ROCE")}&") of the five in FY2026. JSW Dulux was next on both ("&{T("JSWDULUX", "ROE_ADJ")}&'
         f'" and "&{T("JSWDULUX", "ROCE")}&"); its reported ROE of "&{T("JSWDULUX", "ROE", f="0%")}&" is inflated by '
         f'the one-off gain on its slump sale."'),
        ("", f'="Margins. Its EBITDA margin of "&{T(ap, "EBITDAM")}&" was the highest (Indigo "&{T("INDIGOPNTS", "EBITDAM")}&'
             f'", Berger "&{T("BERGEPAINT", "EBITDAM")}&"). Gross margin of "&{T(ap, "GM")}&" ranks second to Indigo ("&'
             f'{T("INDIGOPNTS", "GM")}&"), so Asian Paints turns gross profit into operating profit more efficiently: '
             f'scale spreads advertising, distribution and overheads over a revenue base three times Berger\'s."'),
        ("", f'="DuPont. The 5-step split shows the ROE lead comes from operating margin: EBIT margin "&'
             f'TEXT(DuPont!{LAST}{dm[(ap, "D5_EBITM")]},"0.0%")&" vs "&TEXT(DuPont!{LAST}{dm[("BERGEPAINT", "D5_EBITM")]},"0.0%")&'
             f'" at Berger. Asset turnover is lower than Berger\'s ("&TEXT(DuPont!{LAST}{dm[(ap, "D3_AT")]},"0.00")&"x vs "&'
             f'TEXT(DuPont!{LAST}{dm[("BERGEPAINT", "D3_AT")]},"0.00")&"x) and leverage is modest (equity multiplier "&'
             f'TEXT(DuPont!{LAST}{dm[(ap, "D3_EM")]},"0.00")&"x vs "&TEXT(DuPont!{LAST}{dm[("BERGEPAINT", "D3_EM")]},"0.00")&'
             f'"x), so the lead is not bought with debt."'),
        ("", f'="Cash. Cash from operations was "&{T(ap, "CFOE", f="0%")}&" of EBITDA and the free-cash-flow margin '
             f'was "&{T(ap, "FCFM")}&", both the best of the group, after capex of Rs "&TEXT(Raw_Data!{LAST}'
             f'{xm["raw_capex_ap"]},"#,##0")&" cr."'),
        ("Where Asian Paints is weaker",
         f'="Working capital. Its cash conversion cycle of "&{T(ap, "CCC", f="0")}&" days ranks fourth: inventory '
         f'days are high ("&{T(ap, "INVD", f="0")}&") and payable days are the lowest of the five ("&{T(ap, "PAYD", f="0")}&'
         f'"), against "&{T("JSWDULUX", "CCC", f="0")}&" days at JSW Dulux."'),
        ("", f'="Trend. Returns have fallen from the FY2024 peak: ROE excluding one-offs went from "&'
             f'{T(ap, "ROE_ADJ", col="G")}&" in FY2024 to "&{T(ap, "ROE_ADJ")}&" in FY2026 and EBITDA margin from "&'
             f'{T(ap, "EBITDAM", col="G")}&" to "&{T(ap, "EBITDAM")}&". Revenue grew "&{T(ap, "REVG", col="G")}&", "&'
             f'{T(ap, "REVG", col="H")}&" and "&{T(ap, "REVG")}&" in FY2024-FY2026 as demand slowed and Birla Opus '
             f'entered, so the gap to peers has narrowed."'),
        ("What this means for the report",
         "Asian Paints is still the strongest business in the group on returns, margins and cash, which supports a "
         "quality premium. The investment debate is whether it can defend that lead as competition rises; the "
         "valuation (phase 2, from Project 3) decides whether the price already reflects it."),
    ]
    for head, f in paras:
        if head:
            ws.cell(r, 1, head).font = C.F_SUB
            r += 1
        c = ws.cell(r, 1, f)
        c.font = C.F_TXT
        c.alignment = C.WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        ws.row_dimensions[r].height = 48
        r += 1
    r += 1
    C.note(ws, r, 1, "All numbers above are live links or TEXT() formulas on the Ratios, DuPont and Peer_Comparison "
                     "sheets. Educational project, not investment advice.")
    C.set_widths(ws, {"A": 34, "B": 13, "C": 13, "D": 13, "E": 13, "F": 13, "G": 12, "H": 9})
    ws.freeze_panes = "A6"


# ----------------------------------------------------------------------------------------------- Cover
def build_cover(ws, xm: dict, pm: dict, cm: dict) -> None:
    ws.title = "Cover"
    ws["A1"] = "Asian Paints vs four listed peers: ratio analysis and peer benchmarking, FY2022-FY2026"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color="1F3864")
    ws["A2"] = ("Project 5 (equity research initiation on Asian Paints), part 1. Annual accounts to FY2026 "
                "(year to 31-Mar-2026); data downloaded 1-Nov-2026. All amounts Rs crore.")
    ws["A2"].font = C.F_NOTE
    C.para(ws, 4, 1, "Purpose: compare Asian Paints with Berger Paints, Kansai Nerolac, JSW Dulux (formerly Akzo "
                     "Nobel India) and Indigo Paints on profitability, liquidity, leverage and efficiency, explain ROE "
                     "with a 3-step and 5-step DuPont, and rank the five companies. The results feed the financial "
                     "analysis section of the initiation report.", ncols_merge=9, height=45)
    r = 6
    ws.cell(r, 1, "Key outputs").font = C.F_SUB
    r += 1
    hdr = ["Company", "ROE excl. one-offs FY26", "ROCE FY26", "EBITDA margin FY26", "Gross margin FY26",
           "Cash conversion cycle FY26 (days)", "Weighted rank FY26", "Weighted rank 5-yr", "Position (selected)"]
    C.style_header(ws, r, hdr, height=42)
    r += 1
    sr, posr = pm["score_r"], pm["pos_r"]
    for i, sym in enumerate(C.SYMS):
        ws.cell(r, 1, C.NAMES[sym]).font = C.F_BOLD if sym == "ASIANPAINT" else C.F_TXT
        for j, code in enumerate(["ROE_ADJ", "ROCE", "EBITDAM", "GM", "CCC"]):
            c = ws.cell(r, 2 + j, f"=Ratios!{LAST}{xm[(sym, code)]}")
            fmt_cell(c, C.RATIO_FMT[code], C.F_LINK)
        c = ws.cell(r, 7, f"=Peer_Comparison!{'DEFGH'[i]}{sr}")
        fmt_cell(c, "score", C.F_LINK)
        c = ws.cell(r, 8, f"=Peer_Comparison!{'IJKLM'[i]}{sr}")
        fmt_cell(c, "score", C.F_LINK)
        c = ws.cell(r, 9, f"=Peer_Comparison!D{pm[('sel', sym)]}")
        fmt_cell(c, "rank", C.F_LINK_B)
        c.alignment = C.CENTER
        if sym == "ASIANPAINT":
            for col in range(1, 10):
                ws.cell(r, col).fill = C.FILL_AP
        r += 1
    r += 1
    rows = [("Ranking basis selected (change on Peer_Comparison!D3)", f"={pm['basis']}"),
            ("Strongest company on that basis", f"={pm['winner']}"),
            ("Checks status (Checks sheet)", f"={cm['overall']}"),
            ("Checks passed", f'={cm["passed"]}&" of "&{cm["total"]}')]
    for lab, f in rows:
        ws.cell(r, 1, lab).font = C.F_BOLD
        c = ws.cell(r, 4, f)
        c.font = C.F_LINK_B
        if lab.startswith("Checks status"):
            add_pass_fail_format(ws, f"D{r}")
        r += 1
    r += 1
    ws.cell(r, 1, "How to use").font = C.F_SUB
    r += 1
    for t in ["1. Raw_Data holds every input (blue) with its source in column J. Change an input and all sheets "
              "recalculate.",
              "2. Ratios computes 24 ratios per company from building blocks (averages, EBIT, adjusted PAT).",
              "3. DuPont splits ROE into 3 and 5 factors; the product must equal ROE (Checks section 2).",
              "4. Peer_Comparison ranks the five companies for FY2026 and the 5-year average; the scorecard "
              "weights (yellow) are judgment and can be changed.",
              "5. Conclusion explains the result with live numbers; Checks must show OVERALL = PASS."]:
        C.para(ws, r, 1, t, ncols_merge=9)
        r += 1
    r += 1
    ws.cell(r, 1, "Colour legend").font = C.F_SUB
    r += 1
    for txt, font, fill in [("1,234  Input typed from a source", C.F_IN, None),
                            ("1,234  Formula", C.F_CALC, None),
                            ("1,234  Link to another sheet", C.F_LINK, None),
                            ("1,234  Judgment input (reason next to it)", C.F_IN, C.FILL_YEL),
                            ("Asian Paints row", C.F_TXT, C.FILL_AP)]:
        c = ws.cell(r, 1, txt)
        c.font = font
        if fill:
            c.fill = fill
        r += 1
    r += 1
    ws.cell(r, 1, "Sources").font = C.F_SUB
    r += 1
    for t in ["Screener.in consolidated pages and schedules API (statements, Rs crore): "
              "https://www.screener.in/company/<SYMBOL>/consolidated/",
              "Company results: NSE XBRL annual filings FY2021-FY2024 and Q4 FY2026 results PDFs (COGS lines, "
              "exceptional items, FY2025-26 cross-checks): https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
              "S&P Global Market Intelligence via stockanalysis.com (current assets/liabilities, cash and "
              "short-term investments, cross-checks): https://stockanalysis.com/quote/nse/<SYMBOL>/financials/",
              "Copies of every source file: source_data/ (index in source_data/README.md).",
              "Educational project, not investment advice."]:
        C.para(ws, r, 1, t, ncols_merge=9)
        r += 1
    C.set_widths(ws, {"A": 26, "B": 14, "C": 11, "D": 13, "E": 13, "F": 15, "G": 12, "H": 12, "I": 12})


def check_claims() -> None:
    """The Conclusion text makes ranking claims; confirm each one with the pandas engine before writing it."""
    inp = RE.load_inputs()
    res = RE.compute_all(inp)
    pt = RE.peer_table(res, "FY2026").set_index("code")

    def rank(code: str, name: str) -> int:
        return int(pt.loc[code, f"rank_{name}"])

    ap, bg = res["ASIANPAINT"], res["BERGEPAINT"]
    claims = {
        "AP #1 on ROE excl. one-offs and ROCE": rank("ROE_ADJ", "Asian Paints") == 1 and rank("ROCE", "Asian Paints") == 1,
        "JSW #2 on both": rank("ROE_ADJ", "JSW Dulux") == 2 and rank("ROCE", "JSW Dulux") == 2,
        "AP #1 EBITDA margin": rank("EBITDAM", "Asian Paints") == 1,
        "Indigo #1 and AP #2 gross margin": rank("GM", "Indigo Paints") == 1 and rank("GM", "Asian Paints") == 2,
        "AP #1 CFO/EBITDA and FCF margin": rank("CFOE", "Asian Paints") == 1 and rank("FCFM", "Asian Paints") == 1,
        "AP #4 CCC, #5 payable days": rank("CCC", "Asian Paints") == 4 and rank("PAYD", "Asian Paints") == 5,
        "AP EBIT margin above Berger, turnover below": (ap.loc["D5_EBITM", "FY2026"] > bg.loc["D5_EBITM", "FY2026"]
                                                       and ap.loc["AT", "FY2026"] < bg.loc["AT", "FY2026"]),
        "AP revenue about 3x Berger": 2.8 < inp["ASIANPAINT"].loc["REV", "FY2026"] / inp["BERGEPAINT"].loc["REV", "FY2026"] < 3.2,
        "AP ROE excl. one-offs lower in FY2026 than FY2024": ap.loc["ROE_ADJ", "FY2026"] < ap.loc["ROE_ADJ", "FY2024"],
        "AP strongest on FY2026 scorecard": RE.composite(RE.peer_table(res, "FY2026")).idxmin() == "Asian Paints",
    }
    bad = [k for k, ok in claims.items() if not ok]
    if bad:
        raise SystemExit("Conclusion claims no longer true: " + "; ".join(bad))
    print("conclusion claims verified:", len(claims))


def main() -> None:
    check_claims()
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    rm, days = build_raw(wb)
    xm = build_ratios(wb, rm, days)
    xm["raw_capex_ap"] = rm[("ASIANPAINT", "CAPEX")]
    dm = build_dupont(wb, rm, xm)
    pm = build_peer(wb, rm, xm)
    build_charts(wb, xm)
    build_conclusion(wb, xm, dm, pm)
    cm = build_checks(wb, rm, dm, pm)
    build_cover(cover, xm, pm, cm)
    # sheet order: Cover, Raw_Data, Ratios, DuPont, Peer_Comparison, Charts, Conclusion, Checks
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
    wb.save(C.OUTFILE)
    # save the row maps so verify_workbook.py can find every cell
    rows = []
    for (sym, code), rr in rm.items():
        rows.append({"sheet": "Raw_Data", "company": sym, "code": code, "row": rr})
    for k, rr in xm.items():
        if isinstance(k, tuple):
            rows.append({"sheet": "Ratios", "company": k[0], "code": k[1], "row": rr})
    for k, rr in dm.items():
        if isinstance(k, tuple) and k[0] in C.SYMS:
            rows.append({"sheet": "DuPont", "company": k[0], "code": k[1], "row": rr})
    for k, rr in pm.items():
        if isinstance(k, tuple) and k[0] in ("FY2026", "AVG5") and k[1] not in ("first", "last"):
            rows.append({"sheet": "Peer_Comparison", "company": k[0], "code": k[1], "row": rr})
    extra = {"score_r": pm["score_r"], "pos_r": pm["pos_r"]}
    for k, v in extra.items():
        rows.append({"sheet": "Peer_Comparison", "company": "", "code": k, "row": v})
    pd.DataFrame(rows).to_csv(Path(__file__).resolve().parent / "_cell_map.csv", index=False)
    print("saved", C.OUTFILE, "checks:", cm["n_rows"])


if __name__ == "__main__":
    main()
