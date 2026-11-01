"""Build AsianPaints_Comps_Summary.pdf (3 pages) from the recalculated workbook.

All numbers are read from the values Excel cached in AsianPaints_Comps_and_DCF.xlsx, using the same readers as
build/make_outputs.py; the chart is figures/football_field.png. Run after build/make_outputs.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_outputs as mo  # noqa: E402

ROOT = mo.ROOT
PDF = ROOT / "AsianPaints_Comps_Summary.pdf"
BLUE = colors.HexColor("#1F4E78")
GREEN = colors.HexColor("#E2EFDA")
GREY = colors.HexColor("#BFBFBF")
LIGHT = colors.HexColor("#F2F2F2")

H1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=BLUE, spaceAfter=3)
H2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=BLUE, spaceBefore=7,
                    spaceAfter=3)
BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=8.8, leading=11.6, spaceAfter=4)
SMALL = ParagraphStyle("Small", fontName="Helvetica", fontSize=7.2, leading=9.2, textColor=colors.HexColor("#404040"))
CELL = ParagraphStyle("Cell", fontName="Helvetica", fontSize=7.6, leading=9.2)
HCELL = ParagraphStyle("HCell", fontName="Helvetica-Bold", fontSize=7.4, leading=8.8, textColor=colors.white)
BULLET = ParagraphStyle("Bullet", parent=BODY, leftIndent=10, bulletIndent=1, spaceAfter=2)
SRC = ParagraphStyle("Src", parent=SMALL, leftIndent=8, bulletIndent=0, spaceAfter=1)


def f0(v) -> str:
    return f"{v:,.0f}"


def fx(v, nd: int = 1) -> str:
    return f"{v:.{nd}f}x"


def fp(v, nd: int = 1, sign: bool = False) -> str:
    """v is a fraction."""
    return f"{100 * v:+.{nd}f}%" if sign else f"{100 * v:.{nd}f}%"


def table(data, widths, style_extra=(), header_rows: int = 1) -> Table:
    data = [[Paragraph(str(c), HCELL) if r < header_rows else c for c in row] for r, row in enumerate(data)]
    t = Table(data, colWidths=widths, repeatRows=header_rows)
    st = [("FONT", (0, header_rows), (-1, -1), "Helvetica", 7.6),
          ("BACKGROUND", (0, 0), (-1, header_rows - 1), BLUE),
          ("ALIGN", (1, header_rows), (-1, -1), "RIGHT"),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.25, GREY),
          ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    t.setStyle(TableStyle(st + list(style_extra)))
    return t


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#595959"))
    canvas.drawString(1.5 * cm, 1.0 * cm, "Asian Paints comps + DCF | Educational project, not investment advice. "
                                          "The author holds no position.")
    canvas.drawRightString(A4[0] - 1.5 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def main() -> None:
    wb = load_workbook(mo.XLSX, data_only=True)
    checks = mo.overall_checks(wb)
    assert checks[0] == "PASS", checks
    c = wb["Comps"]
    d = wb["DCF"]
    w = wb["WACC"]
    s = wb["Sensitivity"]
    ff = mo.football_field(wb)
    iv = mo.implied_values(wb)
    d1 = mo.drop_one(wb)
    fc = mo.dcf_forecast(wb).set_index("line_item")

    price = float(d["B65"].value)
    dcf_ps = float(d["B64"].value)
    wacc = float(w["B28"].value)
    g = float(d["B50"].value)
    g_mkt = float(d["B80"].value)
    rf = float(w["B5"].value)
    lo3, hi3 = float(s["B24"].value), float(s["B25"].value)
    ap = {k: c[f"{col}5"].value for k, col in
          [("ev_ebitda", "R"), ("pe", "S"), ("ev_sales", "T"), ("margin", "N"), ("roce", "P"), ("cagr", "O")]}
    med = {k: c[f"{col}14"].value for k, col in
           [("ev_ebitda", "R"), ("pe", "S"), ("ev_sales", "T"), ("margin", "N"), ("roce", "P"), ("cagr", "O")]}
    prem = {k: c[f"{col}17"].value for k, col in [("ev_ebitda", "R"), ("pe", "S"), ("ev_sales", "T")]}
    ffi = ff.set_index("method")
    pt = ffi.loc["Analyst price targets (low-high)"]
    wk = ffi.loc["52-week trading range"]
    ivi = iv.set_index("multiple")
    ev_e, pe_e, evs_e = ivi.loc["EV/EBITDA TTM"], ivi.loc["P/E TTM"], ivi.loc["EV/Sales TTM"]
    blend = float(wb["Football_Field"]["B15"].value)
    top_val = float(wb["Football_Field"]["B24"].value)
    pts = pd.read_csv(ROOT / "data" / "price_targets.csv").set_index("symbol")
    n_analysts = int(pts.loc["ASIANPAINT", "pt_analysts"])

    story = []
    # ------------------------------------------------------------------ page 1
    story.append(Paragraph("Asian Paints (NSE: ASIANPAINT): trading comparables and DCF", H1))
    story.append(Paragraph(
        f"Prices: 30-Oct-2026 close. Balance sheet: 30-Sep-2026. Rs crore unless stated. Source: "
        f"AsianPaints_Comps_and_DCF.xlsx (live formulas, recalculated in Excel; Checks sheet {checks[0]}, "
        f"{checks[1]}).", SMALL))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"At Rs {f0(price)}, Asian Paints trades at {fx(ap['ev_ebitda'])} TTM EV/EBITDA and {fx(ap['pe'])} TTM P/E, "
        f"a {fp(prem['ev_ebitda'], 0)} and {fp(prem['pe'], 0)} premium to the median of four listed paint peers "
        f"({fx(med['ev_ebitda'])} and {fx(med['pe'])}). The peer 25th-75th percentile multiples imply "
        f"Rs {f0(ev_e.implied_rs_per_share_at_p25)}-{f0(ev_e.implied_rs_per_share_at_p75)} per share on EV/EBITDA and "
        f"Rs {f0(pe_e.implied_rs_per_share_at_p25)}-{f0(pe_e.implied_rs_per_share_at_p75)} on P/E. A five-year FCFF DCF "
        f"(WACC {fp(wacc, 2)}, terminal growth {fp(g, 1)}) gives Rs {f0(dcf_ps)} per share, or Rs {f0(lo3)}-{f0(hi3)} "
        f"when WACC and g each move 0.5 pp. The price is above every valuation-based range and inside only the 52-week "
        f"range and the analyst target range. With the model's cash flows, the price requires free cash flow to grow "
        f"{fp(g_mkt, 1)} a year forever after FY2031, above the {fp(rf, 2)} risk-free rate.", BODY))

    key = [["Measure", "Value"],
           ["Share price, 30-Oct-2026 close (Yahoo Finance)", f"Rs {f0(price)}"],
           [f"DCF value per share (WACC {fp(wacc, 2)}, g {fp(g, 1)})",
            f"Rs {f0(dcf_ps)} ({fp(dcf_ps / price - 1, 0, True)} vs price)"],
           ["DCF range (WACC +/-0.5 pp, g +/-0.5 pp)", f"Rs {f0(lo3)} - {f0(hi3)}"],
           ["EV/EBITDA comps, peer 25th-75th (median)",
            f"Rs {f0(ev_e.implied_rs_per_share_at_p25)} - {f0(ev_e.implied_rs_per_share_at_p75)} "
            f"({f0(ev_e.implied_rs_per_share_at_median)})"],
           ["P/E comps, peer 25th-75th (median)",
            f"Rs {f0(pe_e.implied_rs_per_share_at_p25)} - {f0(pe_e.implied_rs_per_share_at_p75)} "
            f"({f0(pe_e.implied_rs_per_share_at_median)})"],
           ["EV/Sales comps, peer 25th-75th (median)",
            f"Rs {f0(evs_e.implied_rs_per_share_at_p25)} - {f0(evs_e.implied_rs_per_share_at_p75)} "
            f"({f0(evs_e.implied_rs_per_share_at_median)})"],
           [f"Analyst price targets, low - high (median), {n_analysts} analysts",
            f"Rs {f0(pt.low_rs)} - {f0(pt.high_rs)} ({f0(pt.mid_rs)})"],
           ["52-week range (intraday)", f"Rs {f0(wk.low_rs)} - {f0(wk.high_rs)}"],
           ["Perpetual FCFF growth after FY2031E implied by the price", fp(g_mkt, 2)]]
    story.append(table(key, [10.2 * cm, 7.6 * cm], [("BACKGROUND", (0, 2), (-1, 2), GREEN)]))

    story.append(Paragraph("Trading comparables (TTM, prices of 30-Oct-2026)", H2))
    hdr = ["Company", "TTM to", "Market cap", "EV", "EV/ EBITDA", "P/E", "EV/ Sales", "EV/EBITDA FY27E",
           "P/E FY27E", "EBITDA margin", "Revenue CAGR FY23-26", "ROCE FY26"]
    rows = [hdr]
    for r in range(5, 10):
        rows.append([c[f"A{r}"].value, c[f"B{r}"].value, f0(c[f"E{r}"].value), f0(c[f"I{r}"].value),
                     fx(c[f"R{r}"].value), fx(c[f"S{r}"].value), fx(c[f"T{r}"].value, 2), fx(c[f"V{r}"].value),
                     fx(c[f"W{r}"].value), fp(c[f"N{r}"].value), fp(c[f"O{r}"].value), fp(c[f"P{r}"].value)])
    rows.append(["Peer median (4 peers)", "", "", "", fx(c["R14"].value), fx(c["S14"].value), fx(c["T14"].value, 2),
                 fx(c["V14"].value), fx(c["W14"].value), fp(c["N14"].value), fp(c["O14"].value),
                 fp(c["P14"].value)])
    rows.append(["Asian Paints vs median", "", "", "", fp(c["R17"].value, 0, True), fp(c["S17"].value, 0, True),
                 fp(c["T17"].value, 0, True), fp(c["V17"].value, 0, True), fp(c["W17"].value, 0, True),
                 f"{100 * c['N17'].value:+.1f} pp", f"{100 * c['O17'].value:+.1f} pp",
                 f"{100 * c['P17'].value:+.1f} pp"])
    widths = [2.75, 1.25, 1.55, 1.55, 1.2, 1.1, 1.15, 1.35, 1.2, 1.3, 1.45, 1.15]
    story.append(table(rows, [x * cm for x in widths],
                       [("BACKGROUND", (0, 1), (-1, 1), GREEN), ("FONT", (0, 6), (-1, 7), "Helvetica-Bold", 7.6),
                        ("BACKGROUND", (0, 6), (-1, 7), LIGHT), ("ALIGN", (1, 1), (1, -1), "CENTER")]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "EV = market cap + borrowings + lease liabilities + minority interest - cash - liquid (current) investments. "
        "EBITDA is operating profit before other income (Ind AS 116, so leases count as debt). FY27E multiples use "
        "S&P Global consensus (EBITDA = consensus EBIT + TTM D&A). Berger, Kansai Nerolac and JSW Dulux reported Q2 FY27 "
        "after 30-Oct-2026, so their TTM ends Jun-2026 and their balance sheets are at 31-Mar-2026. Indigo Paints "
        "filed Q2 FY27 at 17:41 IST on 30-Oct-2026, after the close. JSW Dulux TTM profit excludes a Rs 1,578 cr "
        "after-tax exceptional gain; its 1:10 share split went ex on 22-Oct-2026. Peer statistics exclude Asian Paints.",
        SMALL))

    # ------------------------------------------------------------------ page 2
    story.append(PageBreak())
    story.append(Paragraph("Football field: value per share by method (Rs)", H2))
    img = ROOT / "figures" / "football_field.png"
    story.append(Image(str(img), width=17.8 * cm, height=17.8 * cm * 900 / 1575))
    story.append(Paragraph("Implied Asian Paints value per share from peer multiples", H2))
    rows = [["Multiple", "Peer 25th (x)", "Peer median (x)", "Peer 75th (x)", "Implied at 25th (Rs)",
             "Implied at median (Rs)", "Implied at 75th (Rs)", "Asian Paints multiple", "Median implied vs price"]]
    for _, r in iv.iterrows():
        nd = 2 if r.multiple.startswith("EV/Sales") else 1
        rows.append([r.multiple, fx(r.peer_p25_x, nd), fx(r.peer_median_x, nd), fx(r.peer_p75_x, nd),
                     f0(r.implied_rs_per_share_at_p25), f0(r.implied_rs_per_share_at_median),
                     f0(r.implied_rs_per_share_at_p75), fx(r.asian_paints_multiple_x, nd),
                     f"{r.median_implied_vs_price_pct:+.1f}%"])
    story.append(table(rows, [x * cm for x in [2.9, 1.7, 1.8, 1.7, 1.95, 2.05, 1.95, 1.85, 2.0]]))
    d1i = d1.set_index("case")
    lo_row, hi_row = d1i.loc["Lowest drop-one result"], d1i.loc["Highest drop-one result"]
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        f"EV-based values: (Asian Paints metric x peer multiple - debt incl. leases - minority interest + cash and liquid "
        f"investments) / 95.92 crore shares. With only four peers, dropping one at a time moves the EV/EBITDA median "
        f"between {fx(lo_row.median_ev_ebitda_ttm_x)} and {fx(hi_row.median_ev_ebitda_ttm_x)} "
        f"(Rs {f0(lo_row.implied_rs_per_share_ev_ebitda)}-{f0(hi_row.implied_rs_per_share_ev_ebitda)} per share); "
        f"the P/E median stays between {fx(lo_row.median_pe_ttm_x)} and {fx(hi_row.median_pe_ttm_x)}.", SMALL))
    story.append(Paragraph("Read-across", H2))
    bullets = [
        f"The share price (Rs {f0(price)}) is above every valuation-based bar. The highest of them, the 75th-percentile "
        f"EV/EBITDA value (Rs {f0(ev_e.implied_rs_per_share_at_p75)}), is {fp(-top_val, 0)} below the price.",
        f"Peer multiples undervalue the sector leader: Asian Paints has the highest TTM EBITDA margin "
        f"({fp(ap['margin'])} vs a {fp(med['margin'])} peer median) and ROCE ({fp(ap['roce'])} vs {fp(med['roce'])}), "
        f"so a premium is justified. The question is its size: {fp(prem['ev_ebitda'], 0)} on EV/EBITDA.",
        f"The DCF (Rs {f0(dcf_ps)}) sits {fp(-(dcf_ps / blend - 1), 0)} below the blended comps median "
        f"(Rs {f0(blend)}, average of the EV/EBITDA and P/E medians). The two methods do not overlap.",
        f"Analysts are closer to the market: the target range (Rs {f0(pt.low_rs)}-{f0(pt.high_rs)}) contains the "
        f"price and the median target (Rs {f0(pt.mid_rs)}) is {fp(pt.mid_rs / price - 1, 0, True)} above it.",
    ]
    for b in bullets:
        story.append(Paragraph(b, BULLET, bulletText="-"))

    # ------------------------------------------------------------------ page 3
    story.append(PageBreak())
    story.append(Paragraph("DCF: free cash flow to the firm (valuation date 30-Sep-2026)", H2))
    pers = ["FY2026A", "FY2027E", "FY2028E", "FY2029E", "FY2030E", "FY2031E"]
    lines = [("Revenue", "revenue_rs_cr", "cr"), ("Revenue growth", "revenue_growth_pct", "pct"),
             ("EBITDA", "ebitda_rs_cr", "cr"), ("EBITDA margin", "ebitda_margin_pct", "pct"),
             ("NOPAT = EBIT x (1 - 25.17%)", "nopat_rs_cr", "cr"), ("Capex", "capex_rs_cr", "cr"),
             ("New leases", "new_leases_rs_cr", "cr"),
             ("Increase in trade working capital", "increase_in_trade_working_capital_rs_cr", "cr"),
             ("FCFF", "fcff_rs_cr", "cr"), ("PAT attributable to owners", "pat_attributable_to_owners_rs_cr", "cr"),
             ("EPS (Rs)", "eps_rs", "eps"), ("Consensus EPS (Rs, S&P Global)", "consensus_eps_rs", "eps")]
    rows = [["Rs crore"] + pers]
    for label, key_, kind in lines:
        vals = []
        for p in pers:
            v = fc.loc[key_, p]
            if v is None or v != v:
                vals.append("")
            elif kind == "pct":
                vals.append(f"{v:.1f}%")
            elif kind == "eps":
                vals.append(f"{v:.2f}")
            else:
                vals.append(f0(v))
        rows.append([label] + vals)
    story.append(table(rows, [5.6 * cm] + [2.03 * cm] * 6,
                       [("FONT", (0, 9), (-1, 9), "Helvetica-Bold", 7.6), ("BACKGROUND", (0, 9), (-1, 9), LIGHT)]))
    story.append(Paragraph(
        "FY2027E = H1 FY2027 actual (filed 29-Oct-2026) + H2 FY2027E. Only H2 FY2027E and FY2028E-FY2031E are "
        "discounted, from 30-Sep-2026 to each 31-Mar. Drivers: H2 FY2027E revenue +15% vs H2 FY2026, then 8.0-8.5% a "
        "year; EBITDA margin 17.0% in H2 FY2027E, 18.5% in FY2028E and 19.0% after; capex 3.5-4.0% of revenue; new "
        "leases 1.0%; trade working capital 19% of revenue.", SMALL))

    wacc_rows = [["WACC (CAPM)", ""],
                 ["Risk-free rate (10-year G-sec, 30-Oct-2026)", fp(rf, 2)],
                 [f"Beta used (regression {w['B6'].value:.3f}, Blume {w['B7'].value:.2f}, peers {w['B8'].value:.2f})",
                  f"{w['B9'].value:.2f}"],
                 ["Equity risk premium", fp(w["B10"].value, 2)],
                 ["Cost of equity", fp(w["B11"].value, 2)],
                 ["After-tax cost of debt (rf + 1.0%, tax 25.17%)", fp(w["B21"].value, 2)],
                 ["Debt weight D / (D + E), market values", fp(w["B27"].value, 2)],
                 ["WACC", fp(wacc, 2)],
                 ["Terminal growth g", fp(g, 2)]]
    bridge = [["Valuation (Rs crore)", ""],
              ["PV of FCFF, H2 FY2027E-FY2031E", f0(d["B48"].value)],
              ["PV of terminal value (Gordon)", f0(d["B53"].value)],
              ["Enterprise value", f0(d["B54"].value)],
              ["+ Cash and investments", f0(d["B55"].value + d["B56"].value + d["B57"].value)],
              ["- Borrowings and lease liabilities", f0(d["B58"].value + d["B59"].value)],
              ["- Minority interest", f0(d["B60"].value)],
              ["Equity value", f0(d["B62"].value)],
              ["Value per share (Rs, 95.92 cr shares)", f"{d['B64'].value:,.2f}"]]
    t1 = table(wacc_rows, [6.4 * cm, 2.0 * cm], [("FONT", (0, 7), (-1, 7), "Helvetica-Bold", 7.6)])
    t2 = table(bridge, [5.5 * cm, 2.1 * cm], [("FONT", (0, 8), (-1, 8), "Helvetica-Bold", 7.6),
                                             ("BACKGROUND", (0, 8), (-1, 8), GREEN)])
    story.append(Spacer(1, 4))
    story.append(Table([[t1, t2]], colWidths=[9.0 * cm, 8.4 * cm],
                       style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(Paragraph(
        f"Terminal value is {fp(d['B70'].value, 0)} of EV and equals {fx(d['B72'].value)} FY2031E EBITDA. Using the "
        f"peer median EV/EBITDA ({fx(d['B73'].value)}) as an exit multiple instead would give Rs {f0(d['B76'].value)} "
        f"per share, which implies {fp(d['B77'].value, 1)} perpetual growth.", SMALL))

    story.append(Paragraph("Sensitivity: DCF value per share (Rs), WACC down, terminal growth across", H2))
    grid = [["WACC \\ g"] + [fp(s[f"{col}6"].value, 1) for col in "CDEFG"]]
    for r in range(7, 12):
        grid.append([fp(s[f"B{r}"].value, 2)] + [f0(s[f"{col}{r}"].value) for col in "CDEFG"])
    story.append(table(grid, [2.4 * cm] + [1.8 * cm] * 5,
                       [("BACKGROUND", (3, 3), (3, 3), GREEN), ("FONT", (3, 3), (3, 3), "Helvetica-Bold", 7.6),
                        ("BOX", (2, 2), (4, 4), 0.9, BLUE), ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 7.6)]))

    story.append(Paragraph("Interpretation", H2))
    story.append(Paragraph(
        f"The comps and the DCF answer different questions. Comps say Asian Paints is expensive relative to its listed "
        f"peers, but the peers are smaller and less profitable, so their multiples are a floor rather than a fair "
        f"value. The DCF says the price needs more than this model's five years of 8-8.5% growth: at a {fp(wacc, 2)} "
        f"WACC the price implies {fp(g_mkt, 1)} FCFF growth forever, while a common rule caps perpetual growth at the "
        f"risk-free rate ({fp(rf, 2)}). The market is paying for a long run of growth from brand, distribution and "
        f"pricing power. The risks to that view are raw-material inflation, which cut the Q2 FY27 consolidated PBDIT "
        f"margin to 15.6% (down 202 bp, press release), and competition from Birla Opus (Grasim) and JSW Dulux; "
        f"management's outlook says competitive intensity remains elevated.", BODY))

    story.append(Paragraph("Sources (downloaded 1-Nov-2026; copies in source_data/)", H2))
    srcs = [
        "Asian Paints Q2 FY27 results and press release (NSE, 29-Oct-2026): https://nsearchives.nseindia.com/corporate/"
        "ASIANPAINT_29102026140213_OutcomeofBM29102026signed.pdf",
        "Asian Paints Q2 FY27 investor presentation (NSE): https://nsearchives.nseindia.com/corporate/"
        "ASIANPAINT_29102026164544_SEIntimation_Investor_Presentation_Q2FY26-27pdfsigned.pdf",
        "Financial statements: Screener.in, https://www.screener.in/company/&lt;SYMBOL&gt;/consolidated/ ; consensus, "
        "price targets and statistics: S&amp;P Global via https://stockanalysis.com/quote/nse/&lt;SYMBOL&gt;/",
        "Prices: Yahoo Finance via yfinance (ASIANPAINT.NS, BERGEPAINT.NS, KANSAINER.NS, JSWDULUX.NS, INDIGOPNTS.NS, "
        "^NSEI), daily closes to 30-Oct-2026",
        "10-year G-sec 7.41%: Reuters via ETBFSI (30-Oct-2026), https://bfsi.economictimes.indiatimes.com/articles/"
        "india-bonds-buckle-for-fourth-straight-month-on-oils-climb/135363689 ; Trading Economics, "
        "https://tradingeconomics.com/india/government-bond-yield",
        "Country risk premium (memo): Damodaran, Jan-2026, https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/"
        "ctryprem.html",
    ]
    for x in srcs:
        story.append(Paragraph(x, SRC, bulletText="-"))

    doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.3 * cm,
                            bottomMargin=1.5 * cm, title="Asian Paints: comparable company analysis and DCF",
                            author="Finance portfolio, Project 3")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"saved {PDF} ({PDF.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
