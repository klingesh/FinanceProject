"""Fetch Castrol India (NSE: CASTROLIND) STANDALONE financials from Screener.in.

Castrol India has no consolidated accounts, so this uses the standalone page
https://www.screener.in/company/CASTROLIND/ (not /consolidated/).

Saves to source_data/screener/ :
  CASTROLIND_standalone.html             raw page (audit trail)
  CASTROLIND_<section>.csv               quarters, profit-loss, balance-sheet, cash-flow, ratios (Rs crore)
  CASTROLIND_schedule_<section>_<parent>.json   line-item breakdowns from the schedules API
  screener_summary.json                  top ratios (market cap, price, 52w high/low ...), company id, fetch time

The snapshot in source_data/ was downloaded on 31-Oct-2026 (prices as of the 30-Oct-2026 close).
Re-running overwrites it with the current page.

Run:  python build/fetch_screener_standalone.py
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

SYMBOL = "CASTROLIND"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "source_data" / "screener"
OUT.mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130 Safari/537.36"
    )
}
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]
SCHEDULES = {
    "quarters": ["Sales", "Expenses", "Other Income", "Net Profit"],
    "profit-loss": ["Sales", "Expenses", "Other Income", "Net Profit"],
    "balance-sheet": ["Borrowings", "Other Liabilities", "Fixed Assets", "Other Assets", "Investments"],
    "cash-flow": [
        "Cash from Operating Activity",
        "Cash from Investing Activity",
        "Cash from Financing Activity",
    ],
}


def to_number(x: object) -> float | None:
    """Convert a Screener cell ('1,234', '12%', '') to float or None."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_section(soup: BeautifulSoup, sec_id: str) -> pd.DataFrame | None:
    """Parse one Screener data table into a tidy DataFrame (first column = item)."""
    sec = soup.find("section", id=sec_id)
    if sec is None:
        return None
    table = sec.find("table", class_=re.compile("data-table"))
    if table is None:
        return None
    df = pd.read_html(io.StringIO(str(table)))[0]
    df = df.rename(columns={df.columns[0]: "item"})
    df["item"] = (
        df["item"].astype(str).str.replace(r"\s*\+\s*$", "", regex=True).str.replace("\xa0", " ").str.strip()
    )
    df = df[df["item"].str.lower() != "raw pdf"]
    for c in df.columns[1:]:
        df[c] = df[c].map(to_number)
    return df


def parse_top_ratios(soup: BeautifulSoup) -> dict:
    """Return the 'top ratios' box (market cap, price, P/E ...)."""
    res: dict = {}
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
    url = f"https://www.screener.in/company/{SYMBOL}/"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    (OUT / f"{SYMBOL}_standalone.html").write_text(r.text, encoding="utf-8")
    soup = BeautifulSoup(r.text, "lxml")
    info: dict = {"url": url, "fetched_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}
    h1 = soup.find("h1")
    info["name"] = h1.get_text(strip=True) if h1 else SYMBOL
    info["top_ratios"] = parse_top_ratios(soup)
    for sec in SECTIONS:
        df = parse_section(soup, sec)
        if df is None:
            info[f"{sec}_shape"] = None
            continue
        df.to_csv(OUT / f"{SYMBOL}_{sec}.csv", index=False)
        info[f"{sec}_shape"] = list(df.shape)
        info[f"{sec}_columns"] = [str(c) for c in df.columns]
        info[f"{sec}_items"] = df["item"].tolist()
    m = re.search(r'data-company-id="(\d+)"', r.text)
    cid = m.group(1) if m else None
    info["company_id"] = cid
    # 'About' text and key points (business description)
    about = soup.find("div", class_=re.compile("about"))
    info["about"] = " ".join(about.get_text(" ", strip=True).split()) if about else None

    sched_log = {}
    if cid:
        for section, parents in SCHEDULES.items():
            for parent in parents:
                # Standalone schedules: omit the 'consolidated' parameter entirely
                # (tested 31-Oct-2026: '&consolidated=' / '=false' / '=true' return {} for CASTROLIND).
                api = (
                    f"https://www.screener.in/api/company/{cid}/schedules/"
                    f"?parent={quote(parent)}&section={section}"
                )
                try:
                    rr = requests.get(api, headers=UA, timeout=40)
                    ok = rr.status_code == 200
                    data = rr.json() if ok else None
                except Exception as exc:  # noqa: BLE001 - log and continue
                    ok, data = False, {"error": str(exc)}
                fname = f"{SYMBOL}_schedule_{section}_{parent.replace(' ', '_')}.json"
                (OUT / fname).write_text(json.dumps({"url": api, "data": data}, indent=2), encoding="utf-8")
                sched_log[f"{section}|{parent}"] = {"ok": ok, "keys": list(data.keys()) if isinstance(data, dict) else None}
                time.sleep(1.0)
    info["schedules"] = sched_log
    (OUT / "screener_summary.json").write_text(json.dumps({SYMBOL: info}, indent=2), encoding="utf-8")
    print("done", SYMBOL, "company_id", cid)
    for k, v in sched_log.items():
        print(k, v)


if __name__ == "__main__":
    main()
