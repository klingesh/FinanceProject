"""Regenerate every output of the project: validation, market analysis, figures and CSV files.

Usage (from the project folder):  python src/run_all.py
Runs offline from data/raw/. Writes figures/*.png, outputs/*.csv and data/nifty_options_2026-10-30.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

if __name__ == "__main__":
    matplotlib.use("Agg")  # file output only when run as a script; the notebook keeps its inline backend
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from options import analysis as A  # noqa: E402
from options import plots as P  # noqa: E402
from options.binomial import early_exercise_boundary  # noqa: E402
from options.black_scholes import bs_price  # noqa: E402
from options.hedging import hedge_experiment, simulate_delta_hedge  # noqa: E402
from options.market_data import apply_quote_filters, filter_summary, load_index_history, load_option_chains  # noqa: E402
from options.validation import check_row, convergence_study, print_checks, run_model_validation  # noqa: E402

RAW = ROOT / "data" / "raw"
FIG = ROOT / "figures"
OUT = ROOT / "outputs"
MONTHLY = pd.Timestamp("2026-11-23")
NEXT_MONTHLY = pd.Timestamp("2026-12-29")

TIDY_COLUMNS = [
    "snapshot_time", "expiry", "days", "T", "strike", "option_type", "bid", "ask", "mid", "spread", "rel_spread",
    "bid_qty", "ask_qty", "last", "volume", "open_interest", "iv_nse_pct", "underlying_value", "moneyness",
    "identifier", "f_oi", "f_quotes", "f_spread", "f_band", "usable",
]
IV_COLUMNS = [
    "expiry", "days", "T", "strike", "option_type", "F", "DF", "fwd_moneyness", "log_moneyness", "otm", "bid", "ask",
    "mid", "rel_spread", "open_interest", "volume", "iv", "iv_bid", "iv_ask", "iv_method", "iv_nse", "iv_spot_div", "iv_nse_replica",
]


def nearest_strike(strikes: pd.Series, level: float) -> float:
    """Listed strike closest to a level."""
    s = strikes.drop_duplicates().to_numpy(dtype=float)
    return float(s[np.argmin(np.abs(s - level))])


def run(verbose: bool = True) -> dict:
    """Run the full pipeline and return the main result objects."""
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    res: dict = {}

    # 1. Model validation ------------------------------------------------------------------
    val = run_model_validation()
    conv = convergence_study()
    conv.to_csv(OUT / "binomial_convergence.csv", index=False)
    plt.close(P.plot_convergence(conv, FIG / "binomial_convergence.png"))

    # 2. Market data -------------------------------------------------------------------------
    chain = apply_quote_filters(load_option_chains(RAW), A.SPOT_CLOSE)
    chain[TIDY_COLUMNS].to_csv(ROOT / "data" / "nifty_options_2026-10-30.csv", index=False)
    filt = filter_summary(chain)
    filt.to_csv(OUT / "quote_filter_summary.csv", index=False)

    # 3. Implied forwards ----------------------------------------------------------------------
    fwd = A.implied_forwards(chain, A.R_CONT, A.SPOT_CLOSE)
    fwd.to_csv(OUT / "implied_forwards.csv", index=False)
    f_m = fwd.set_index("expiry").loc[MONTHLY]

    # 4. Implied vols and the 23-Nov-2026 smile -----------------------------------------------
    r_nse, nse_tab = A.nse_iv_convention(chain)
    ivs = A.add_implied_vols(chain, fwd, A.R_CONT, A.SPOT_CLOSE, r_nse)
    usable = ivs[ivs["usable"]].copy()
    usable[IV_COLUMNS].to_csv(OUT / "implied_vols.csv", index=False)
    smile = A.otm_smile(ivs, MONTHLY)
    smile.to_csv(OUT / "smile_2026-11-23.csv", index=False)
    gap = A.call_put_iv_gap(ivs, MONTHLY)
    gap.to_csv(OUT / "call_put_iv_gap_2026-11-23.csv", index=False)
    plt.close(P.plot_smile(smile, gap, "23-Nov-2026", f_m["F"], A.SPOT_CLOSE, FIG / "vol_smile_2026-11-23.png"))
    atm_m = A.interp_iv(smile, 1.0)
    iv95, iv105 = A.interp_iv(smile, 0.95), A.interp_iv(smile, 1.05)
    iv90 = A.interp_iv(smile, 0.90)
    nse_atm = A.interp_iv(smile.assign(iv=smile["iv_nse"]), 1.0)
    usable["nse_diff"] = usable["iv"] - usable["iv_nse"]
    usable["replica_diff"] = usable["iv_nse_replica"] - usable["iv_nse"]

    # 5. Term structure, VIX-style variance, realised vol ------------------------------------
    ts = A.atm_term_structure(ivs, fwd)
    ts.to_csv(OUT / "atm_term_structure.csv", index=False)
    tsi = ts.set_index("expiry")
    atm30 = A.interpolate_vol_30d(tsi.loc[MONTHLY, "T"], tsi.loc[MONTHLY, "atm_iv"], tsi.loc[NEXT_MONTHLY, "T"], tsi.loc[NEXT_MONTHLY, "atm_iv"])
    mf30 = A.interpolate_vol_30d(tsi.loc[MONTHLY, "T"], tsi.loc[MONTHLY, "model_free_vol"], tsi.loc[NEXT_MONTHLY, "T"], tsi.loc[NEXT_MONTHLY, "model_free_vol"])
    dec1 = pd.Timestamp("2026-12-01")
    atm30_bracket = A.interpolate_vol_30d(tsi.loc[MONTHLY, "T"], tsi.loc[MONTHLY, "atm_iv"], tsi.loc[dec1, "T"], tsi.loc[dec1, "atm_iv"])
    vix_s = load_index_history(RAW / "IDX_INDIAVIX.csv")
    nifty = load_index_history(RAW / "IDX_NSEI.csv")
    vr = A.vix_vs_realised(vix_s, nifty)
    rv21 = float(vr["rv_trailing"].iloc[-1]) / 100
    vrp = (vr["vix"] - vr["rv_next"]).dropna()
    plt.close(P.plot_term_structure(ts, A.INDIA_VIX, atm30, mf30, rv21, FIG / "atm_iv_term_structure.png"))
    plt.close(P.plot_vix_history(vr, FIG / "vix_vs_realised_vol.png"))

    # 6. Greeks --------------------------------------------------------------------------------
    m_strikes = usable.loc[usable["expiry"] == MONTHLY, "strike"]
    k_atm = nearest_strike(m_strikes, f_m["F"])
    k_otm = nearest_strike(m_strikes, 0.95 * A.SPOT_CLOSE)
    contracts = [
        {"label": "ATM call", "expiry": MONTHLY, "strike": k_atm, "option_type": "C"},
        {"label": "ATM put", "expiry": MONTHLY, "strike": k_atm, "option_type": "P"},
        {"label": "5% OTM put", "expiry": MONTHLY, "strike": k_otm, "option_type": "P"},
    ]
    gt = A.greeks_table(contracts, ivs, fwd)
    gt.to_csv(OUT / "greeks_2026-11-23.csv", index=False)
    mats = []
    for exp in (pd.Timestamp("2026-11-03"), MONTHLY, NEXT_MONTHLY):
        mats.append({"label": f"{exp:%d-%b-%Y} ({int(tsi.loc[exp, 'days'])}d, IV {100 * tsi.loc[exp, 'atm_iv']:.1f}%)",
                     "T": tsi.loc[exp, "T"], "sigma": tsi.loc[exp, "atm_iv"], "q": A.DIV_YIELD_FACTSHEET})
    prof = A.greek_profiles(np.arange(21500.0, 24701.0, 10.0), k_atm, mats)
    prof.to_csv(OUT / "greek_profiles.csv", index=False)
    plt.close(P.plot_greek_profiles(prof, k_atm, A.SPOT_CLOSE, FIG / "greek_profiles.png"))

    # 7. Binomial vs BS on market contracts; American put illustration ------------------------
    q_m = float(f_m["q_implied"])
    bvb = A.binomial_vs_bs(smile, q_m)
    bvb.to_csv(OUT / "binomial_vs_bs_2026-11-23.csv", index=False)
    prem_strikes = np.arange(21500.0, 24751.0, 250.0)
    prem = A.american_put_premium(prem_strikes, smile, float(f_m["T"]), q_m)
    prem.to_csv(OUT / "american_put_premium_2026-11-23.csv", index=False)
    perpetual = 2 * A.R_CONT / (2 * A.R_CONT + atm_m**2)
    bnd = {}
    q_lab = f"q = {100 * A.DIV_YIELD_FACTSHEET:.2f}% (factsheet yield)"
    for qq, lab in ((0.0, "q = 0"), (A.DIV_YIELD_FACTSHEET, q_lab)):
        b = early_exercise_boundary(0.9 * k_atm, k_atm, 1.0, A.R_CONT, atm_m, qq, "put", N=5000)
        b["q"] = qq
        bnd[f"1-year put, {lab}"] = b
    pd.concat(bnd.values(), ignore_index=True).to_csv(OUT / "early_exercise_boundary.csv", index=False)
    plt.close(P.plot_early_exercise(bnd, perpetual, prem, A.SPOT_CLOSE, FIG / "early_exercise_boundary.png",
                                    title_left=f"American put boundary: K={k_atm:,.0f}, vol {100 * atm_m:.1f}%, r {100 * A.R_CONT:.2f}%",
                                    title_right=f"Early-exercise premium, 23-Nov-2026 terms ({int(f_m['days'])} days, q {100 * q_m:.2f}%)"))

    # 8. Delta hedging -------------------------------------------------------------------------
    T_m = float(f_m["T"])
    iv_atm_call = float(gt.loc[gt["label"] == "ATM call", "iv_own"].iloc[0])
    hedge = hedge_experiment(A.SPOT_CLOSE, k_atm, T_m, A.R_CONT, q_m, iv_atm_call, steps_list=(6, 12, 24, 48, 96, 192, 384))
    hedge_vol = hedge_experiment(A.SPOT_CLOSE, k_atm, T_m, A.R_CONT, q_m, iv_atm_call, steps_list=(24,), real_vols=(0.10, iv_atm_call, 0.18))
    hedge_all = pd.concat([hedge, hedge_vol[~np.isclose(hedge_vol["sigma_real"], iv_atm_call)]], ignore_index=True)
    hedge_all.to_csv(OUT / "delta_hedge_summary.csv", index=False)
    pnl = simulate_delta_hedge(A.SPOT_CLOSE, k_atm, T_m, A.R_CONT, q_m, iv_atm_call, None, 24, 20000, 42)
    plt.close(P.plot_hedging(pnl, hedge, float(hedge["premium_pts"].iloc[0]), FIG / "delta_hedge_pnl.png",
                             label=f"Short {k_atm:,.0f} call to 23-Nov-2026, 24 daily rebalances"))

    # 9. Market checks -------------------------------------------------------------------------
    mk = []
    uv = float(chain["chain_underlying"].iloc[0])
    mk.append(check_row("Market data", "Yahoo close equals NSE JSON underlyingValue", uv, "23,053.10", abs(uv - A.SPOT_CLOSE) < 0.005))
    dev = abs(f_m["F"] / A.NOV_FUTURES_CLOSE - 1)
    mk.append(check_row("Market data", "23-Nov parity forward vs NIFTY Nov-2026 futures close 23,101.40", float(f_m["F"]), "within 0.1%", dev < 0.001, f"difference {f_m['F'] - A.NOV_FUTURES_CLOSE:+.2f} pts"))
    overlap = fwd["F_bidask_high"] - fwd["F_bidask_low"]
    mk.append(check_row("Market data", "near-ATM synthetic-forward bid/ask bands overlap (no conversion/reversal arbitrage)", float(overlap.min()),
                        "> 0 for all 6 expiries", bool((overlap > 0).all()), f"narrowest overlap {overlap.min():.2f} pts"))
    otm_u = usable[usable["otm"]]
    n_nan_otm = int(otm_u["iv"].isna().sum())
    n_nan_itm = int(usable.loc[~usable["otm"], "iv"].isna().sum())
    mk.append(check_row("Market IV", f"OTM usable quotes with a valid implied vol ({len(otm_u)} quotes)", len(otm_u) - n_nan_otm, f"{len(otm_u)}", n_nan_otm == 0,
                        f"{n_nan_itm} of {int((~usable['otm']).sum())} ITM quotes have a mid below intrinsic value and get no IV"))
    valid = usable[usable["iv"].notna()]
    rep = float(np.abs(bs_price(A.SPOT_CLOSE, valid["strike"], valid["T"], A.R_CONT, valid["iv"], valid["q_implied"], valid["option_type"].eq("C").to_numpy()) - valid["mid"]).max())
    mk.append(check_row("Market IV", f"BSM at own IV (q = implied) reproduces the mid price ({len(valid)} quotes): max error", rep, "< 1e-6 pts", rep < 1e-6))
    near = gap[(gap["fwd_moneyness"] - 1).abs() <= 0.02]
    g_own, g_nse = float(near["gap_own"].abs().mean() * 100), float(near["gap_nse"].abs().mean() * 100)
    g_sd = float(near["gap_spot_div"].abs().mean() * 100)
    mk.append(check_row("Market IV", "23-Nov call vs put IV at same strike (within 2% of F): mean |gap|", g_own, "< 0.5 vol pts", g_own < 0.5, f"NSE field: {g_nse:.2f} vol pts"))
    lr_max = float(bvb["lr_minus_bs"].abs().max())
    crr_max = float(bvb["crr_minus_bs"].abs().max())
    med_spread = float(smile["ask"].sub(smile["bid"]).median())
    mk.append(check_row("Market trees", f"Leisen-Reimer N=501 vs BSM on {len(bvb)} 23-Nov contracts: max |diff|", lr_max, "< 0.01 pts", lr_max < 0.01))
    mk.append(check_row("Market trees", f"CRR N=1000 vs BSM on {len(bvb)} 23-Nov contracts: max |diff|", crr_max, f"< 5% of median spread ({0.05 * med_spread:.2f} pts)", crr_max < 0.05 * med_spread))
    rep_err = float(usable["replica_diff"].abs().median() * 100)
    mk.append(check_row("Market IV", f"NSE IV field reproduced with spot, q=0, r={100 * r_nse:.2f}%: median |diff|", rep_err, "< 0.05 vol pts", rep_err < 0.05))
    vix_gap = 100 * mf30 - A.INDIA_VIX
    mk.append(check_row("Market vol", "30-day model-free vol (23-Nov and 29-Dec strips) vs India VIX 15.30", 100 * mf30, "within 1 vol pt", abs(vix_gap) < 1.0, f"gap {vix_gap:+.2f} vol pts"))
    validation = pd.concat([val, pd.DataFrame(mk)], ignore_index=True)
    validation.to_csv(OUT / "validation_results.csv", index=False)

    # 10. Headline numbers ---------------------------------------------------------------------
    otm_row = gt[gt["label"] == "5% OTM put"].iloc[0]
    head = [
        ("spot_close", A.SPOT_CLOSE, "index points", "NIFTY 50 close 30-Oct-2026"),
        ("r_continuous", A.R_CONT, "decimal", "ln(1.0593)"),
        ("forward_23nov", f_m["F"], "index points", "parity-implied"),
        ("forward_minus_spot_23nov", f_m["F_minus_spot"], "index points", ""),
        ("carry_23nov", f_m["carry_b"], "decimal p.a.", "ln(F/S)/T"),
        ("q_implied_23nov", q_m, "decimal p.a.", "r - carry"),
        ("nov_futures_close", A.NOV_FUTURES_CLOSE, "index points", "Capital Market"),
        ("atm_iv_23nov", atm_m, "decimal", "interpolated at K = F"),
        ("nse_atm_iv_23nov", nse_atm, "decimal", "NSE field interpolated at K = F (OTM side)"),
        ("iv_90_23nov", iv90, "decimal", "K/F = 0.90"),
        ("iv_95_23nov", iv95, "decimal", "K/F = 0.95"),
        ("iv_105_23nov", iv105, "decimal", "K/F = 1.05"),
        ("smile_strike_range_23nov", f"{smile['strike'].min():.0f}-{smile['strike'].max():.0f}", "index points", "OTM quotes used"),
        ("skew_95_105_volpts", 100 * (iv95 - iv105), "vol points", ""),
        ("atm_iv_30d_monthlies", atm30, "decimal", "23-Nov and 29-Dec total variance interpolation"),
        ("atm_iv_30d_bracketing", atm30_bracket, "decimal", "23-Nov and 01-Dec"),
        ("model_free_vol_30d", mf30, "decimal", "VIX formula, 23-Nov and 29-Dec"),
        ("india_vix", A.INDIA_VIX / 100, "decimal", "Yahoo close"),
        ("realised_vol_21d", rv21, "decimal", "NIFTY close-to-close, to 30-Oct-2026"),
        ("vix_minus_next21d_rv_mean", float(vrp.mean()), "vol points", f"{vrp.index.min():%b-%Y} to {vrp.index.max():%b-%Y}"),
        ("vix_above_next21d_rv_share", float((vrp > 0).mean()), "share of days", ""),
        ("r_nse_fit", r_nse, "decimal", "rate reproducing NSE IV field"),
        ("mean_abs_iv_diff_own_vs_nse", float(usable["nse_diff"].abs().mean() * 100), "vol points", "all usable quotes"),
        ("atm_strike", k_atm, "index points", ""),
        ("otm_put_strike", k_otm, "index points", ""),
        ("otm_put_iv", float(otm_row["iv_own"]), "decimal", ""),
        ("n_usable_quotes", len(usable), "count", "after filters, all expiries"),
        ("n_valid_iv_quotes", int(usable["iv"].notna().sum()), "count", "usable quotes inside no-arbitrage bounds"),
        ("n_smile_quotes_23nov", len(smile), "count", ""),
        ("lr_max_diff_pts", lr_max, "index points", ""),
        ("crr_max_diff_pts", crr_max, "index points", ""),
        ("max_american_premium_pts", float(prem["early_exercise_premium"].max()), "index points", ""),
        ("hedge_std_daily_pts", float(hedge.loc[hedge["rebalances"] == 24, "std_pts"].iloc[0]), "index points", ""),
        ("hedge_mean_daily_pts", float(hedge.loc[hedge["rebalances"] == 24, "mean_pts"].iloc[0]), "index points", ""),
        ("call_premium_pts", float(hedge["premium_pts"].iloc[0]), "index points", "model premium at ATM call IV"),
        ("hedge_std_384_pts", float(hedge.loc[hedge["rebalances"] == 384, "std_pts"].iloc[0]), "index points", "384 rebalances"),
        ("hedge_mean_real10_pts", float(hedge_vol.loc[np.isclose(hedge_vol["sigma_real"], 0.10), "mean_pts"].iloc[0]), "index points", "realised vol 10%"),
        ("hedge_mean_real18_pts", float(hedge_vol.loc[np.isclose(hedge_vol["sigma_real"], 0.18), "mean_pts"].iloc[0]), "index points", "realised vol 18%"),
        ("cp_gap_own_volpts", g_own, "vol points", "mean |call IV - put IV|, strikes within 2% of F"),
        ("cp_gap_nse_volpts", g_nse, "vol points", "same, NSE field"),
        ("cp_gap_spot_div_volpts", g_sd, "vol points", f"same, spot with q = {100 * A.DIV_YIELD_FACTSHEET:.2f}% (factsheet)"),
        ("american_premium_23000_pts", float(prem.loc[prem["strike"] == 23000, "early_exercise_premium"].iloc[0]), "index points", "K = 23,000 put"),
        ("boundary_1y_q0_over_K", float(bnd["1-year put, q = 0"].dropna()["boundary_over_K"].iloc[0]), "ratio", "tau = 1 year"),
        ("boundary_1y_qdiv_over_K", float(bnd[f"1-year put, {q_lab}"].dropna()["boundary_over_K"].iloc[0]), "ratio",
         f"tau = 1 year, q = {100 * A.DIV_YIELD_FACTSHEET:.2f}%"),
        ("div_yield_factsheet", A.DIV_YIELD_FACTSHEET, "decimal", "NIFTY 50 factsheet, 30-Oct-2026"),
        ("perpetual_put_limit_q0", perpetual, "ratio", "2r/(2r+vol^2)"),
    ]
    headline = pd.DataFrame(head, columns=["key", "value", "unit", "note"])
    headline.to_csv(OUT / "headline_numbers.csv", index=False)

    res.update(validation=validation, conv=conv, chain=chain, filt=filt, fwd=fwd, ivs=ivs, usable=usable, smile=smile, gap=gap, ts=ts,
               gt=gt, prof=prof, bvb=bvb, prem=prem, bnd=bnd, hedge=hedge_all, pnl=pnl, vr=vr, headline=headline, nse_tab=nse_tab, r_nse=r_nse)
    if verbose:
        pd.set_option("display.width", 200)
        pd.set_option("display.max_columns", 30)
        print_checks(validation)
        print()
        print(filt.to_string(index=False))
        print()
        print(fwd[["expiry", "days", "F", "F_bidask_low", "F_bidask_high", "F_minus_spot", "carry_b", "q_implied", "pv_gap_points", "r_ols"]].to_string(index=False))
        print()
        print(ts.to_string(index=False))
        print()
        print(headline.to_string(index=False))
    return res


if __name__ == "__main__":
    out = run()
    n_fail = int((out["validation"]["status"] != "PASS").sum())
    sys.exit(1 if n_fail else 0)
