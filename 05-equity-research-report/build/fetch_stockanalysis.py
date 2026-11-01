"""Download stockanalysis.com (S&P Global Market Intelligence data) pages for the five paint companies.

Saves raw HTML to source_data/stockanalysis/raw/ and every parsed table to data/stockanalysis/<SYM>_<page>_t<i>.csv.
Units on the statement pages are millions of INR (the page states "Financials in millions INR").

Run:  python build/fetch_stockanalysis.py
"""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "source_data" / "stockanalysis" / "raw"
TIDY = ROOT / "data" / "stockanalysis"
RAW.mkdir(parents=True, exist_ok=True)
TIDY.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
SYMBOLS = ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "JSWDULUX", "INDIGOPNTS"]
PAGES = {
    "income": "financials/income-statement/",
    "balance": "financials/balance-sheet/",
    "cashflow": "financials/cash-flow-statement/",
    "ratios": "financials/ratios/",
    "statistics": "statistics/",
    "forecast": "forecast/",
    "dividend": "dividend/",
}


def flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" | ".join(str(x) for x in c if not str(x).startswith("Unnamed")) for c in df.columns]
    else:
        df.columns = [str(c) for c in df.columns]
    return df


def main() -> None:
    s = requests.Session()
    s.headers.update(UA)
    meta = {}
    fetched = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    for sym in SYMBOLS:
        for key, page in PAGES.items():
            url = f"https://stockanalysis.com/quote/nse/{sym}/{page}"
            r = s.get(url, timeout=45)
            info = {"url": url, "final_url": r.url, "status": r.status_code, "fetched": fetched}
            if r.status_code != 200:
                meta[f"{sym}_{key}"] = info
                time.sleep(1.5)
                continue
            (RAW / f"{sym}_{key}.html").write_text(r.text, encoding="utf-8")
            m = re.search(r"Financials in ([^.<]+)\.", r.text)
            info["unit_note"] = m.group(0) if m else None
            m = re.search(r"Updated ([A-Z][a-z]{2} \d{1,2}, \d{4})", r.text)
            info["updated"] = m.group(1) if m else None
            try:
                tables = pd.read_html(io.StringIO(r.text))
            except ValueError:
                tables = []
            info["n_tables"] = len(tables)
            for i, t in enumerate(tables):
                flatten_cols(t).to_csv(TIDY / f"{sym}_{key}_t{i}.csv", index=False)
            meta[f"{sym}_{key}"] = info
            time.sleep(1.5)
    (TIDY / "stockanalysis_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("done", len(meta))


if __name__ == "__main__":
    main()
