"""Download Screener.in pages and line-item schedules for Asian Paints and four listed peers.

Saves, for every company:
  source_data/screener/raw/<SYM>_<consolidated|standalone>.html      raw page (audit copy)
  source_data/screener/schedules/<SYM>_<scope>_<section>_<parent>.json raw schedule JSON
  data/screener/<SYM>_<scope>_<section>.csv                             tidy tables (Rs crore, % rows as numbers)
  data/screener/<SYM>_<scope>_schedules.csv                             all schedule rows in long format
  data/screener/screener_summary.json                                   top ratios, company id, URLs, fetch time

Scope rule (stated in the README): consolidated for every company. Indigo Paints only has consolidated
accounts from FY2023 (after it bought 51% of Apple Chemie), so its standalone page is downloaded as well.

Run:  python build/fetch_screener.py
"""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "source_data" / "screener" / "raw"
SCHED = ROOT / "source_data" / "screener" / "schedules"
TIDY = ROOT / "data" / "screener"
for p in (RAW, SCHED, TIDY):
    p.mkdir(parents=True, exist_ok=True)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
COMPANIES = {
    "ASIANPAINT": "Asian Paints",
    "BERGEPAINT": "Berger Paints India",
    "KANSAINER": "Kansai Nerolac Paints",
    "JSWDULUX": "JSW Dulux (formerly Akzo Nobel India)",
    "INDIGOPNTS": "Indigo Paints",
}
# (symbol, scope) pairs to download. Standalone pages are kept for reference; schedules are pulled
# for the scope used in the ratio workbook.
PAGES = [(s, "consolidated") for s in COMPANIES] + [(s, "standalone") for s in COMPANIES]
SCHEDULE_SCOPES = {(s, "consolidated") for s in COMPANIES} | {("INDIGOPNTS", "standalone")}
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]
SCHEDULES = [
    ("profit-loss", "Sales"),
    ("profit-loss", "Expenses"),
    ("profit-loss", "Material Cost %"),
    ("profit-loss", "Other Income"),
    ("profit-loss", "Net Profit"),
    ("quarters", "Expenses"),
    ("quarters", "Other Income"),
    ("quarters", "Net Profit"),
    ("balance-sheet", "Borrowings"),
    ("balance-sheet", "Other Liabilities"),
    ("balance-sheet", "Fixed Assets"),
    ("balance-sheet", "Investments"),
    ("balance-sheet", "Other Assets"),
    ("balance-sheet", "Trade receivables"),
    ("cash-flow", "Cash from Operating Activity"),
    ("cash-flow", "Cash from Investing Activity"),
    ("cash-flow", "Cash from Financing Activity"),
]


def to_number(x):
    """Convert Screener text ('1,234', '12%', '') to float or None."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace(",", "").replace("%", "").replace("\xa0", "").strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def get(session: requests.Session, url: str, tries: int = 4) -> requests.Response:
    """GET with simple retry/back-off (Screener returns 429 when hit too fast)."""
    for k in range(tries):
        r = session.get(url, timeout=45)
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503):
            time.sleep(5 * (k + 1))
            continue
        return r
    return r


def parse_table(table) -> pd.DataFrame:
    df = pd.read_html(io.StringIO(str(table)))[0]
    df = df.rename(columns={df.columns[0]: "item"})
    df["item"] = (df["item"].astype(str).str.replace(r"\s*\+\s*$", "", regex=True)
                  .str.replace("\xa0", " ").str.strip())
    df = df[~df["item"].str.lower().isin(["raw pdf", "nan"])]
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]
    for c in df.columns[1:]:
        df[c] = df[c].map(to_number)
    return df


def parse_section(soup: BeautifulSoup, sec_id: str) -> list[pd.DataFrame]:
    sec = soup.find("section", id=sec_id)
    if sec is None:
        return []
    return [parse_table(t) for t in sec.find_all("table", class_=re.compile("data-table"))]


def parse_top_ratios(soup: BeautifulSoup) -> dict:
    res = {}
    ul = soup.find("ul", id="top-ratios")
    if ul is None:
        return res
    for li in ul.find_all("li"):
        name = li.find("span", class_="name")
        val = li.find("span", class_=re.compile("value"))
        if not name or not val:
            continue
        key = " ".join(name.get_text(" ", strip=True).split())
        txt = " ".join(val.get_text(" ", strip=True).split())
        nums = [to_number(n) for n in re.findall(r"[-\d,]+\.?\d*", txt)]
        res[key] = {"text": txt, "numbers": [n for n in nums if n is not None]}
    return res


def main() -> None:
    s = requests.Session()
    s.headers.update(UA)
    summary: dict = {}
    fetched = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    for sym, scope in PAGES:
        url = f"https://www.screener.in/company/{sym}/" + ("consolidated/" if scope == "consolidated" else "")
        r = get(s, url)
        r.raise_for_status()
        (RAW / f"{sym}_{scope}.html").write_text(r.text, encoding="utf-8")
        soup = BeautifulSoup(r.text, "lxml")
        info = {"name": COMPANIES[sym], "scope": scope, "url": url, "fetched": fetched}
        m = re.search(r'data-company-id="(\d+)"', r.text)
        info["company_id"] = m.group(1) if m else None
        info["top_ratios"] = parse_top_ratios(soup)
        for sec in SECTIONS:
            tabs = parse_section(soup, sec)
            if not tabs:
                continue
            tabs[0].to_csv(TIDY / f"{sym}_{scope}_{sec}.csv", index=False)
            info[f"{sec}_columns"] = [str(c) for c in tabs[0].columns]
        sh = parse_section(soup, "shareholding")
        for i, t in enumerate(sh[:2]):
            t.to_csv(TIDY / f"{sym}_{scope}_shareholding_{'quarterly' if i == 0 else 'yearly'}.csv", index=False)
        summary[f"{sym}_{scope}"] = info
        time.sleep(1.5)

        if (sym, scope) not in SCHEDULE_SCOPES or not info["company_id"]:
            continue
        rows = []
        for section, parent in SCHEDULES:
            api = (f"https://www.screener.in/api/company/{info['company_id']}/schedules/?parent={quote(parent)}"
                   f"&section={section}" + ("&consolidated=true" if scope == "consolidated" else ""))
            rr = get(s, api)
            try:
                js = rr.json()
            except ValueError:
                js = {"_error": rr.status_code, "_text": rr.text[:200]}
            fname = f"{sym}_{scope}_{section}_{re.sub(r'[^A-Za-z0-9]+', '_', parent).strip('_')}.json"
            (SCHED / fname).write_text(json.dumps({"url": api, "fetched": fetched, "data": js}, indent=1),
                                       encoding="utf-8")
            if isinstance(js, dict):
                for item, series in js.items():
                    if not isinstance(series, dict):
                        continue
                    for period, val in series.items():
                        if period in ("isExpandable", "setAttributes"):
                            continue
                        rows.append({"section": section, "parent": parent, "item": item,
                                     "period": period, "value": to_number(val), "raw": val})
            time.sleep(1.2)
        pd.DataFrame(rows).to_csv(TIDY / f"{sym}_{scope}_schedules.csv", index=False)

    (TIDY / "screener_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("done:", ", ".join(summary))


if __name__ == "__main__":
    main()
