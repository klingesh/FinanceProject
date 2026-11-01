"""Download the companies' own annual results in XBRL from NSE and extract the cost-of-goods-sold lines.

Why: gross margin needs raw-material cost INCLUDING purchases of traded goods. Screener's expense schedule only
shows "Raw material cost" and "Change in inventory" (no purchases line), and its total is 11-15% of revenue
below the audited figure for Asian Paints. The XBRL file that each company files with NSE alongside its
annual (Q4) results has the audited lines: cost of materials consumed, purchases of stock-in-trade and
changes in inventories. These are the numbers used for gross margin in the workbook.

Saves
  source_data/nse/xbrl/<SYM>_financial_results_annual.json   NSE list of annual filings (with XBRL links)
  source_data/nse/xbrl/<SYM>_FY<year>_<scope>.xml             untouched XBRL files
  data/xbrl_annual.csv                                       tidy values in Rs crore (one row per company-year)

Run:  python build/fetch_xbrl.py
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
XDIR = ROOT / "source_data" / "nse" / "xbrl"
XDIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
}
# NSE symbol(s) to try for each company (JSW Dulux traded as AKZOINDIA before the 2026 rename)
SYMBOLS = {"ASIANPAINT": ["ASIANPAINT"], "BERGEPAINT": ["BERGEPAINT"], "KANSAINER": ["KANSAINER"],
           "JSWDULUX": ["JSWDULUX", "AKZOINDIA"], "INDIGOPNTS": ["INDIGOPNTS"]}
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
TAGS = {
    "REV": "RevenueFromOperations",
    "MAT": "CostOfMaterialsConsumed",
    "PUR": "PurchasesOfStockInTrade",
    "CHG": "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade",
    "EMP": "EmployeeBenefitExpense",
    "OTHEXP": "OtherExpenses",
    "FIN": "FinanceCosts",
    "DEP": "DepreciationDepletionAndAmortisationExpense",
    "OTHINC": "OtherIncome",
    "EXC": "ExceptionalItemsBeforeTax",
    "PBT": "ProfitBeforeTax",
    "PAT": "ProfitLossForPeriod",
    "PATOWN": "ProfitOrLossAttributableToOwnersOfParent",
}
BS_TAGS = {"TA": "Assets", "CA": "CurrentAssets", "CL": "CurrentLiabilities", "INV": "Inventories",
           "EQOWN": "EquityAttributableToOwnersOfParent", "EQ": "Equity"}


def scope_wanted(sym: str, fy: int) -> str:
    """Indigo Paints had no subsidiary until FY2024 (51% of Apple Chemie India), so FY2021-FY2023 are standalone."""
    return "Non-Consolidated" if (sym == "INDIGOPNTS" and fy <= 2023) else "Consolidated"


def fy_of(to_date: str) -> int | None:
    m = re.match(r"\d{2}-Mar-(\d{4})$", to_date or "")
    return int(m.group(1)) if m else None


def parse_xbrl(txt: str) -> dict:
    """Return full-year flows and year-end balances in Rs crore.

    Context ids in these NSE files: 'FourD' = year to date (full year in a Q4/annual filing), 'OneD' = the quarter,
    'OneI' = balance-sheet date. Where 'FourD' is missing the larger of the duration values is taken."""
    out = {}
    for code, tag in TAGS.items():
        vals = {m.group(1): float(m.group(2)) for m in
                re.finditer(rf"<in-bse-fin:{tag}\b[^>]*contextRef=\"([^\"]+)\"[^>]*>(-?[\d.]+)<", txt)}
        v = vals.get("FourD")
        if v is None and vals:
            v = max(vals.values(), key=abs) if code != "CHG" else list(vals.values())[-1]
        out[code] = None if v is None else v / 1e7
    for code, tag in BS_TAGS.items():
        m = re.search(rf"<in-bse-fin:{tag}\b[^>]*contextRef=\"OneI\"[^>]*>(-?[\d.]+)<", txt)
        out[code] = float(m.group(1)) / 1e7 if m else None
    m = re.search(r"<in-bse-fin:LevelOfRoundingUsedInFinancialStatements\b[^>]*>([^<]+)<", txt)
    out["rounding_note"] = m.group(1) if m else ""
    return out


def main() -> None:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", timeout=30)
    rows, log = [], []
    for sym, cands in SYMBOLS.items():
        filings = []
        for c in cands:
            url = f"https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol={c}&period=Annual"
            r = s.get(url, timeout=40)
            try:
                js = r.json()
            except ValueError:
                log.append(f"{sym}/{c}: not JSON ({r.status_code})")
                continue
            lst = js if isinstance(js, list) else js.get("data", [])
            (XDIR / f"{c}_financial_results_annual.json").write_text(json.dumps(lst, indent=1), encoding="utf-8")
            log.append(f"{sym}/{c}: {len(lst)} annual filings listed ({url})")
            filings.extend(lst)
            time.sleep(1.2)
        for fy in YEARS:
            want = scope_wanted(sym, fy)
            cand = [f for f in filings if fy_of(f.get("toDate")) == fy and f.get("consolidated") == want
                    and str(f.get("xbrl", "")).endswith(".xml") and f.get("audited") == "Audited"]
            if not cand:
                # FY2025 onwards NSE moved results to the 'Integrated Filing' format, which this API does not list;
                # those years are read from the Q4 FY2026 results PDFs instead (data/company_reported_fy25_fy26.csv).
                log.append(f"{sym} FY{fy}: no {want} XBRL filing listed")
                continue
            # the latest filing for the year (restated/revised filings come later)
            cand.sort(key=lambda f: pd.to_datetime(f.get("filingDate"), format="%d-%b-%Y %H:%M", errors="coerce"))
            f = cand[-1]
            fname = XDIR / f"{sym}_FY{fy}_{'consolidated' if want == 'Consolidated' else 'standalone'}.xml"
            if not fname.exists():
                rr = s.get(f["xbrl"], timeout=60)
                if rr.status_code != 200 or b"<" not in rr.content[:200]:
                    log.append(f"{sym} FY{fy}: download failed {rr.status_code}")
                    continue
                fname.write_bytes(rr.content)
                time.sleep(1.2)
            vals = parse_xbrl(fname.read_text(encoding="utf-8", errors="ignore"))
            cogs = None
            if vals["MAT"] is not None:
                cogs = vals["MAT"] + (vals["PUR"] or 0.0) + (vals["CHG"] or 0.0)
            rows.append({"company": sym, "fiscal_year": f"FY{fy}", "scope": want, "filing_date": f.get("filingDate"),
                         "xbrl_url": f["xbrl"], "file": fname.relative_to(ROOT).as_posix(), **vals, "COGS": cogs})
            log.append(f"{sym} FY{fy}: {want} filed {f.get('filingDate')} rev {vals['REV']:.2f} cogs {cogs:.2f}")
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data" / "xbrl_annual.csv", index=False)
    (ROOT / "build" / "_xbrl_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
