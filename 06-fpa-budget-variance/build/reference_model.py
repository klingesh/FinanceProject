"""Independent Python re-computation of the Vriddhi Foods FP&A model.

Used for two things: (1) tuning the fictional storyline before the workbook is
built, and (2) cross-checking the values Excel calculates from the workbook's
live formulas (see recalc_verify.py). It does not read the workbook.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

import inputs as I

L = [k for k, _ in I.LINES]
C = [k for k, _ in I.CHANNELS]
R = [k for k, _ in I.RMS]
F = [k for k, _ in I.FUNCS]
NM = len(I.MONTHS)


def _empty_drivers(n: int) -> dict:
    return {"n": n}


def budget_drivers() -> dict:
    B = I.BUDGET
    d = {"months": I.MONTHS}
    d["vol"] = {(l, c): [B["fy_volume"][l] * B["seasonality"][l][m] * B["channel_mix"][l][c] for m in range(NM)]
                for l in L for c in C}
    d["price"] = {l: [B["list_price"][l]] * NM for l in L}
    d["ts"] = {c: list(B["trade_spend"][c]) for c in C}
    d["rm"] = {r: list(B["rm_price"][r]) for r in R}
    d["other"] = {l: [B["other_ingr"][l]] * NM for l in L}
    d["pack"] = {l: [B["packaging"][l]] * NM for l in L}
    d["conv"] = {l: [B["conversion"][l]] * NM for l in L}
    d["freight_pct"] = [B["freight_pct"]] * NM
    d["oneoff"] = [0.0] * NM
    d["ap"] = list(B["ap"])
    d["hc"] = {f: list(B["headcount"][f]) for f in F}
    d["ctc"] = {f: [B["ctc"][f]] * NM for f in F}
    d["inc"] = {f: B["increment"][f] for f in F}
    d["inc_date"] = B["increment_date"]
    d["other_oh"] = list(B["other_oh"])
    d["da"] = list(B["da"])
    d["borr"] = list(B["borrowings"])
    d["rate"] = list(B["int_rate"])
    return d


def actual_drivers() -> dict:
    A = I.ACTUAL
    n = I.N_ACT
    d = {"months": I.MONTHS[:n]}
    av = I.actual_volumes()
    d["vol"] = {k: list(v) for k, v in av.items()}
    d["price"] = {l: list(A["list_price"][l]) for l in L}
    d["ts"] = {c: list(A["trade_spend"][c]) for c in C}
    d["rm"] = {r: list(A["rm_price"][r]) for r in R}
    d["other"] = {l: list(A["other_ingr"][l]) for l in L}
    d["pack"] = {l: list(A["packaging"][l]) for l in L}
    d["conv"] = {l: list(A["conversion"][l]) for l in L}
    d["freight_pct"] = list(A["freight_pct"])
    d["oneoff"] = list(A["freight_oneoff"])
    d["ap"] = list(A["ap"])
    d["hc"] = {f: list(A["headcount"][f]) for f in F}
    d["ctc"] = {f: [A["ctc"][f]] * n for f in F}
    d["inc"] = {f: I.BUDGET["increment"][f] for f in F}
    d["inc_date"] = A["increment_date"]
    d["other_oh"] = list(A["other_oh"])
    d["da"] = list(A["da"])
    d["borr"] = list(A["borrowings"])
    d["rate"] = list(A["int_rate"])
    return d


def forecast_drivers(case: int = 1) -> dict:
    """6+6: Apr-Sep actual drivers, Oct-Mar reforecast drivers (case 1/2/3)."""
    B, Fc = I.BUDGET, I.FORECAST
    a = actual_drivers()
    b = budget_drivers()
    n = I.N_ACT
    ov = {}
    for key, _lab, _u, base, down, up, start in I.CASE_OVERLAYS:
        val = (base, down, up)[case - 1]
        ov[key] = [val if (m >= n and I.MONTHS[m] >= start) else 0.0 for m in range(NM)]
    d = {"months": I.MONTHS}
    d["vol"] = {}
    for l in L:
        for c in C:
            row = list(a["vol"][(l, c)])
            for m in range(n, NM):
                line_vol = B["fy_volume"][l] * B["seasonality"][l][m] * (1 + Fc["vol_adj"][l][m - n])
                v = line_vol * Fc["mix"][l][c]
                if c == "GT":
                    v *= 1 + ov["gtvol"][m]
                row.append(v)
            d["vol"][(l, c)] = row
    d["price"] = {}
    for l in L:
        row = list(a["price"][l])
        for m in range(n, NM):
            p = B["list_price"][l] * (1 + Fc["price_chg"][l])
            if l == "BIS":
                p *= 1 + ov["bisprice"][m]
            row.append(p)
        d["price"][l] = row
    d["ts"] = {c: list(a["ts"][c]) + [B["trade_spend"][c][m] + Fc["ts_adj"][c] for m in range(n, NM)] for c in C}
    d["rm"] = {}
    for r in R:
        row = list(a["rm"][r]) + list(Fc["rm_price"][r])
        if r == "OIL":
            row = [row[m] + ov["oil"][m] for m in range(NM)]
        d["rm"][r] = row
    for key in ("other", "pack", "conv"):
        src = {"other": "other_ingr", "pack": "packaging", "conv": "conversion"}[key]
        d[key] = {l: list(a[key][l]) + [Fc[src][l]] * (NM - n) for l in L}
    d["freight_pct"] = list(a["freight_pct"]) + [Fc["freight_pct"]] * (NM - n)
    d["oneoff"] = list(a["oneoff"]) + [0.0] * (NM - n)
    d["ap"] = list(a["ap"]) + list(Fc["ap"])
    d["hc"] = {f: list(a["hc"][f]) + b["hc"][f][n:] for f in F}
    d["ctc"] = {f: list(a["ctc"][f]) + [I.ACTUAL["ctc"][f]] * (NM - n) for f in F}
    d["inc"] = {f: B["increment"][f] for f in F}
    d["inc_date"] = Fc["increment_date"]
    d["other_oh"] = list(a["other_oh"]) + b["other_oh"][n:]
    d["da"] = list(a["da"]) + b["da"][n:]
    d["borr"] = list(a["borr"]) + list(Fc["borrowings"])
    d["rate"] = list(a["rate"]) + list(Fc["int_rate"])
    return d


def run(d: dict) -> dict:
    """Compute monthly P&L arrays from a driver dict."""
    months = d["months"]
    n = len(months)
    cv = I.CONV
    o = {"months": months}
    vol_l = {l: np.array([sum(d["vol"][(l, c)][m] for c in C) for m in range(n)]) for l in L}
    gs_lc = {(l, c): np.array(d["vol"][(l, c)]) * np.array(d["price"][l]) * cv for l in L for c in C}
    ts_lc = {(l, c): gs_lc[(l, c)] * np.array(d["ts"][c]) for l in L for c in C}
    o["vol_l"] = vol_l
    o["vol_lc"] = {k: np.array(v) for k, v in d["vol"].items()}
    o["gs_lc"], o["ts_lc"] = gs_lc, ts_lc
    o["gs_l"] = {l: sum(gs_lc[(l, c)] for c in C) for l in L}
    o["ts_l"] = {l: sum(ts_lc[(l, c)] for c in C) for l in L}
    o["nr_l"] = {l: o["gs_l"][l] - o["ts_l"][l] for l in L}
    o["nr_c"] = {c: sum(gs_lc[(l, c)] - ts_lc[(l, c)] for l in L) for c in C}
    bom = I.BUDGET["bom"]
    o["mat_lr"] = {(l, r): vol_l[l] * bom[l][r] * np.array(d["rm"][r]) * cv for l in L for r in R}
    o["oth_l"] = {l: vol_l[l] * np.array(d["other"][l]) * cv for l in L}
    o["mat_l"] = {l: sum(o["mat_lr"][(l, r)] for r in R) + o["oth_l"][l] for l in L}
    o["pack_l"] = {l: vol_l[l] * np.array(d["pack"][l]) * cv for l in L}
    o["conv_l"] = {l: vol_l[l] * np.array(d["conv"][l]) * cv for l in L}
    o["gp_l"] = {l: o["nr_l"][l] - o["mat_l"][l] - o["pack_l"][l] - o["conv_l"][l] for l in L}
    o["rm_qty"] = {r: sum(vol_l[l] * bom[l][r] for l in L) for r in R}
    nr = sum(o["nr_l"].values())
    o["volume"] = sum(vol_l.values())
    o["gross_sales"] = sum(o["gs_l"].values())
    o["trade_spend"] = sum(o["ts_l"].values())
    o["net_revenue"] = nr
    o["material"] = sum(o["mat_l"].values())
    o["packaging"] = sum(o["pack_l"].values())
    o["conversion"] = sum(o["conv_l"].values())
    o["cogs"] = o["material"] + o["packaging"] + o["conversion"]
    o["gross_profit"] = nr - o["cogs"]
    o["freight"] = nr * np.array(d["freight_pct"]) + np.array(d["oneoff"])
    o["ap"] = np.array(d["ap"], dtype=float)
    emp = np.zeros(n)
    o["emp_f"] = {}
    for f in F:
        fac = np.array([1 + d["inc"][f] if months[m] >= d["inc_date"] else 1.0 for m in range(n)])
        o["emp_f"][f] = np.array(d["hc"][f]) * np.array(d["ctc"][f]) / 1200 * fac
        emp = emp + o["emp_f"][f]
    o["employee"] = emp
    o["other_oh"] = np.array(d["other_oh"], dtype=float)
    o["ebitda"] = o["gross_profit"] - o["freight"] - o["ap"] - o["employee"] - o["other_oh"]
    o["da"] = np.array(d["da"], dtype=float)
    o["ebit"] = o["ebitda"] - o["da"]
    o["interest"] = np.array(d["borr"]) * np.array(d["rate"]) / 12
    o["pbt"] = o["ebit"] - o["interest"]
    o["tax"] = o["pbt"] * I.TAX_RATE
    o["pat"] = o["pbt"] - o["tax"]
    return o


def agg(o: dict, sl: slice) -> dict:
    """Aggregate a run over a month slice."""
    s = lambda x: float(np.sum(x[sl]))
    a = {}
    for key in ("vol_l", "gs_l", "ts_l", "nr_l", "oth_l", "mat_l", "pack_l", "conv_l", "gp_l"):
        a[key] = {l: s(o[key][l]) for l in L}
    a["mat_lr"] = {k: s(v) for k, v in o["mat_lr"].items()}
    for key in ("volume", "gross_sales", "trade_spend", "net_revenue", "material", "packaging", "conversion",
                "cogs", "gross_profit", "freight", "ap", "employee", "other_oh", "ebitda", "da", "ebit",
                "interest", "pbt", "tax", "pat"):
        a[key] = s(o[key])
    return a


def bridges(A: dict, B: dict) -> dict:
    """Revenue PVM, gross-profit bridge and EBITDA bridge (A = actual/forecast, B = budget)."""
    Va, Vb = A["volume"], B["volume"]
    out = {"lines": {}}
    tot = dict(vol=0.0, mix=0.0, price=0.0, lp=0.0, tsr=0.0, gvol=0.0, gmix=0.0, mrate=0.0, pcrate=0.0)
    mr_rm = {r: 0.0 for r in R + ["OTH"]}
    for l in L:
        va, vb = A["vol_l"][l], B["vol_l"][l]
        sa, sb = va / Va, vb / Vb
        pa, pb = A["nr_l"][l] / va, B["nr_l"][l] / vb
        lpa, lpb = A["gs_l"][l] / va, B["gs_l"][l] / vb
        ta, tb = A["ts_l"][l] / A["gs_l"][l], B["ts_l"][l] / B["gs_l"][l]
        gpb = B["gp_l"][l] / vb
        vol = (Va - Vb) * sb * pb
        mix = (sa - sb) * Va * pb
        price = (pa - pb) * va
        lp = (lpa - lpb) * (1 - tb) * va
        tsr = lpa * (tb - ta) * va
        gvol = (Va - Vb) * sb * gpb
        gmix = (sa - sb) * Va * gpb
        mrate = -(A["mat_l"][l] / va - B["mat_l"][l] / vb) * va
        pcrate = -((A["pack_l"][l] + A["conv_l"][l]) / va - (B["pack_l"][l] + B["conv_l"][l]) / vb) * va
        for r in R:
            mr_rm[r] += -(A["mat_lr"][(l, r)] / va - B["mat_lr"][(l, r)] / vb) * va
        mr_rm["OTH"] += -(A["oth_l"][l] / va - B["oth_l"][l] / vb) * va
        out["lines"][l] = dict(vol=vol, mix=mix, price=price, lp=lp, tsr=tsr, var=A["nr_l"][l] - B["nr_l"][l])
        for k, v in dict(vol=vol, mix=mix, price=price, lp=lp, tsr=tsr, gvol=gvol, gmix=gmix, mrate=mrate, pcrate=pcrate).items():
            tot[k] += v
    out.update(tot)
    out["mr_rm"] = mr_rm
    out["nr_var"] = A["net_revenue"] - B["net_revenue"]
    out["gp_var"] = A["gross_profit"] - B["gross_profit"]
    eb = [("Volume", tot["gvol"]), ("Mix", tot["gmix"]), ("List price", tot["lp"]),
          ("Trade spend rate & channel mix", tot["tsr"]), ("Material rate", tot["mrate"]),
          ("Packaging & conversion rate", tot["pcrate"]), ("Freight", -(A["freight"] - B["freight"])),
          ("A&P", -(A["ap"] - B["ap"])), ("Employee cost", -(A["employee"] - B["employee"])),
          ("Other overheads", -(A["other_oh"] - B["other_oh"]))]
    out["ebitda_bridge"] = eb
    out["ebitda_var"] = A["ebitda"] - B["ebitda"]
    out["checks"] = {
        "pvm": out["vol"] + out["mix"] + out["price"] - out["nr_var"],
        "price_split": out["lp"] + out["tsr"] - out["price"],
        "gp": tot["gvol"] + tot["gmix"] + tot["price"] + tot["mrate"] + tot["pcrate"] - out["gp_var"],
        "mr_rm": sum(mr_rm.values()) - tot["mrate"],
        "ebitda": sum(v for _, v in eb) - out["ebitda_var"],
    }
    return out


def summary(case: int = 1) -> dict:
    b, a, f = run(budget_drivers()), run(actual_drivers()), run(forecast_drivers(case))
    h1 = slice(0, I.N_ACT)
    fy = slice(0, NM)
    return {"budget": b, "actual": a, "forecast": f,
            "bud_h1": agg(b, h1), "act_h1": agg(a, h1), "bud_fy": agg(b, fy), "fc_fy": agg(f, fy),
            "fc_h1": agg(f, h1)}


if __name__ == "__main__":
    S = summary(1)
    def line(name, key):
        bh, ah, bf, ff = S["bud_h1"][key], S["act_h1"][key], S["bud_fy"][key], S["fc_fy"][key]
        print(f"{name:<22}{bh:>10.2f}{ah:>10.2f}{ah-bh:>9.2f} | {bf:>10.2f}{ff:>10.2f}{ff-bf:>9.2f}")
    print(f"{'Rs crore':<22}{'H1 Bud':>10}{'H1 Act':>10}{'Var':>9} | {'FY Bud':>10}{'FY Fcst':>10}{'Var':>9}")
    for nm, k in [("Volume (t)", "volume"), ("Gross sales", "gross_sales"), ("Trade spend", "trade_spend"),
                  ("Net revenue", "net_revenue"), ("Material", "material"), ("Packaging", "packaging"),
                  ("Conversion", "conversion"), ("Gross profit", "gross_profit"), ("Freight", "freight"),
                  ("A&P", "ap"), ("Employee", "employee"), ("Other overheads", "other_oh"), ("EBITDA", "ebitda"),
                  ("D&A", "da"), ("Interest", "interest"), ("PBT", "pbt"), ("Tax", "tax"), ("PAT", "pat")]:
        line(nm, k)
    for lab, A_, B_ in (("H1", S["act_h1"], S["bud_h1"]), ("FY", S["fc_fy"], S["bud_fy"])):
        br = bridges(A_, B_)
        print(f"\n{lab} margins: GM bud {B_['gross_profit']/B_['net_revenue']:.2%} act {A_['gross_profit']/A_['net_revenue']:.2%}; "
              f"EBITDA% bud {B_['ebitda']/B_['net_revenue']:.2%} act {A_['ebitda']/A_['net_revenue']:.2%}")
        print(f"{lab} PVM: vol {br['vol']:.2f} mix {br['mix']:.2f} price {br['price']:.2f} (list {br['lp']:.2f}, ts {br['tsr']:.2f}) = {br['nr_var']:.2f}")
        for l in L:
            x = br["lines"][l]
            print(f"   {l}: var {x['var']:.2f} vol {x['vol']:.2f} mix {x['mix']:.2f} price {x['price']:.2f}")
        print(f"{lab} GP bridge: vol {br['gvol']:.2f} mix {br['gmix']:.2f} price {br['price']:.2f} mat {br['mrate']:.2f} pc {br['pcrate']:.2f} = {br['gp_var']:.2f}")
        print(f"{lab} material by RM: " + ", ".join(f"{k} {v:.2f}" for k, v in br["mr_rm"].items()))
        print(f"{lab} EBITDA bridge: " + ", ".join(f"{k} {v:.2f}" for k, v in br["ebitda_bridge"]) + f" = {br['ebitda_var']:.2f}")
        print(f"{lab} checks: " + ", ".join(f"{k} {v:.2e}" for k, v in br["checks"].items()))
    for case in (2, 3):
        Sx = summary(case)
        print(f"Case {case}: FY EBITDA {Sx['fc_fy']['ebitda']:.2f}, NR {Sx['fc_fy']['net_revenue']:.2f}")
