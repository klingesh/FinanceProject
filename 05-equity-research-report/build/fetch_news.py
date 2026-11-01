"""Save copies of the news / industry pages cited in data/research_facts.json into source_data/news_and_macro/.

HTML pages are saved with <script>, <style>, <svg> and <noscript> blocks removed (the article text, headings and
links are kept) so the folder stays small. A comment at the top of each file records the URL and download time.
If a site blocks the download, a short .md note with the URL and a one-line summary is written instead.

Run: python build/fetch_news.py   (needs internet; everything else in the project runs offline)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "source_data" / "news_and_macro"
FACTS = ROOT / "data" / "research_facts.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
STRIP = re.compile(r"<(script|style|svg|noscript|iframe)\b[^>]*>.*?</\1\s*>", re.S | re.I)


def clean_html(text: str) -> str:
    """Remove script/style/svg blocks and collapse blank lines."""
    text = STRIP.sub("", text)
    text = re.sub(r"<link\b[^>]*rel=[\"']?(preload|stylesheet|prefetch|dns-prefetch|preconnect)[^>]*>", "", text, flags=re.I)
    return re.sub(r"\n\s*\n+", "\n", text)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    facts = json.loads(FACTS.read_text(encoding="utf-8"))["facts"]
    targets: dict[str, tuple[str, str]] = {}
    for f in facts:
        file = f.get("file", "")
        if file.startswith("source_data/news_and_macro/"):
            name = file.split("/")[-1]
            targets[name] = (f["url"], f["text"])
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
                      "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"})
    log = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for name, (url, summary) in sorted(targets.items()):
        dest = OUT / name
        if dest.exists() or dest.with_suffix(".md").exists():
            log.append(f"SKIP {name} (exists)")
            continue
        try:
            r = s.get(url, timeout=40)
            ok = r.status_code == 200 and len(r.content) > 2000
        except requests.RequestException as e:  # noqa: PERF203
            r, ok = None, False
            log.append(f"ERR  {name}: {e!r}")
        if ok and name.lower().endswith(".pdf"):
            dest.write_bytes(r.content)
            log.append(f"OK   {name}: {len(r.content)/1e3:.0f} KB (PDF, untouched)")
        elif ok:
            html = clean_html(r.text)
            head = f"<!-- Saved copy. Source: {url} | downloaded {stamp} | scripts/styles removed to save space -->\n"
            dest.write_text(head + html, encoding="utf-8")
            log.append(f"OK   {name}: {len(r.content)/1e3:.0f} KB raw -> {dest.stat().st_size/1e3:.0f} KB saved")
        else:
            code = getattr(r, "status_code", "n/a")
            note = (f"# {name}\n\nDownload blocked (HTTP {code}) on {stamp}.\n\n"
                    f"- URL: {url}\n- What it says (paraphrased): {summary}\n")
            dest.with_suffix(".md").write_text(note, encoding="utf-8")
            log.append(f"BLOCK {name}: HTTP {code} -> wrote {dest.with_suffix('.md').name}")
        time.sleep(1.0)
    (ROOT / "build" / "_news_download_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
