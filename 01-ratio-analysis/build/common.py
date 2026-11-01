"""Shared helpers for the Project 1 scripts: workbook layout and loaders.

The workbook TwoWheeler_Peer_Benchmark_FY2022-26.xlsx was built by the author in Excel. These scripts only READ it
(openpyxl, cached values saved by Excel); they never write to it.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "TwoWheeler_Peer_Benchmark_FY2022-26.xlsx"
SUMMARY_PDF = ROOT / "TwoWheeler_Peer_Benchmark_FY2022-26_Summary.pdf"
OUTPUTS = ROOT / "outputs"
FIGURES = ROOT / "figures"
SOURCE = ROOT / "source_data"

# (name used in the workbook, short name, Screener symbol, first Raw_Data column, first Ratios column)
COMPANIES = [
    ("Hero MotoCorp", "Hero", "HEROMOTOCO", "D", "B"),
    ("Bajaj Auto", "Bajaj", "BAJAJ-AUTO", "J", "G"),
    ("TVS Motor", "TVS", "TVSMOTOR", "P", "L"),
    ("Eicher Motors", "Eicher", "EICHERMOT", "V", "Q"),
]
RAW_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]  # FY2021 = opening balance sheet only
YEARS = [2022, 2023, 2024, 2025, 2026]

# Ratios sheet rows checked by the scripts: row -> (key, label, unit)
RATIO_ROWS = {
    5: ("gross_margin", "Gross margin", "%"),
    6: ("ebitda_margin", "EBITDA margin (ex other income)", "%"),
    7: ("net_margin", "Net profit margin", "%"),
    8: ("roe", "ROE (PAT / avg equity)", "%"),
    9: ("roa", "ROA (PAT / avg total assets)", "%"),
    10: ("roce_proxy", "ROCE proxy (EBIT / avg equity + borrowings)", "%"),
    16: ("int_cover_ebit", "Interest cover (EBIT / finance costs)", "x"),
    17: ("int_cover_ebitda", "Interest cover (EBITDA / finance costs)", "x"),
    19: ("asset_turnover", "Asset turnover", "x"),
    20: ("inventory_days", "Inventory days", "days"),
    21: ("receivable_days", "Receivable days", "days"),
    25: ("dupont_net_margin", "DuPont: net margin", "%"),
    26: ("dupont_asset_turnover", "DuPont: asset turnover", "x"),
    27: ("dupont_equity_multiplier", "DuPont: equity multiplier", "x"),
    28: ("dupont_roe", "DuPont ROE", "%"),
    46: ("de_proxy", "Debt-to-equity (borrowings / equity, ex leases)", "x"),
    47: ("cash_to_debt", "Cash and bank / borrowings", "x"),
    48: ("ebitda_margin_incl_oi", "EBITDA margin incl. other income", "%"),
    49: ("roce_incl_oi", "ROCE proxy incl. other income", "%"),
    50: ("oi_share_pbt", "Other income as % of PBT", "%"),
    52: ("net_margin_ex_oneoff", "Net margin ex one-off gains (approx.)", "%"),
    53: ("roe_ex_oneoff", "ROE ex one-off gains (approx.)", "%"),
}


def col_offset(col: str, k: int) -> str:
    return get_column_letter(column_index_from_string(col) + k)


def open_workbook(data_only: bool = True):
    return openpyxl.load_workbook(WORKBOOK, data_only=data_only)


def raw_codes(ws) -> dict[str, int]:
    """Map the codes in Raw_Data column A (REV, CM, PAT, ...) to their row numbers."""
    codes = {}
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, str) and v.isupper() and " " not in v and len(v) <= 10:
            codes.setdefault(v, r)
    return codes


def load_raw(wb) -> dict[tuple[str, int], dict[str, float | None]]:
    """Raw_Data inputs and formula rows by (company, fiscal year) -> {code: value}."""
    ws = wb["Raw_Data"]
    codes = raw_codes(ws)
    out = {}
    for name, _, _, first_col, _ in COMPANIES:
        for k, fy in enumerate(RAW_YEARS):
            col = col_offset(first_col, k)
            vals = {}
            for code, row in codes.items():
                v = ws[f"{col}{row}"].value
                vals[code] = float(v) if isinstance(v, (int, float)) else None
            out[(name, fy)] = vals
    return out


def load_ratios(wb) -> dict[tuple[str, int], dict[str, float | str | None]]:
    """Cached values of the Ratios sheet by (company, fiscal year) -> {key: value}."""
    ws = wb["Ratios"]
    out = {}
    for name, _, _, _, first_col in COMPANIES:
        for k, fy in enumerate(YEARS):
            col = col_offset(first_col, k)
            out[(name, fy)] = {key: ws[f"{col}{row}"].value for row, (key, _, _) in RATIO_ROWS.items()}
    return out
