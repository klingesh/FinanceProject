"""Option pricing toolkit: Black-Scholes-Merton, Black-76, implied volatility and binomial trees.

Modules
- black_scholes: BSM / Black-76 prices, Greeks and put-call parity helpers
- implied_vol:   Newton-Raphson implied volatility with a Brent fallback
- binomial:      CRR and Leisen-Reimer trees, tree Greeks, American early-exercise boundary
- market_data:   load and clean the NSE NIFTY option-chain snapshots
- analysis:      market application (implied forwards, smiles, term structure, Greeks tables)
- hedging:       delta-hedging simulation under geometric Brownian motion
- validation:    textbook and numerical checks that print PASS/FAIL
- plots:         matplotlib figures used in the README
"""
from .black_scholes import (
    black76_price,
    black76_vega,
    bs_delta,
    bs_gamma,
    bs_greeks,
    bs_price,
    bs_rho,
    bs_theta,
    bs_vega,
    call_from_put,
    carry_from_forward,
    d1_d2,
    dividend_yield_from_forward,
    forward_from_parity,
    forward_price,
    parity_residual,
    put_from_call,
)
from .binomial import (
    binomial_greeks,
    binomial_price,
    binomial_price_two_step_average,
    crr_params,
    early_exercise_boundary,
    lr_params,
)
from .implied_vol import implied_vol, implied_vol_black76, price_bounds

__all__ = [
    "black76_price",
    "black76_vega",
    "bs_delta",
    "bs_gamma",
    "bs_greeks",
    "bs_price",
    "bs_rho",
    "bs_theta",
    "bs_vega",
    "call_from_put",
    "carry_from_forward",
    "d1_d2",
    "dividend_yield_from_forward",
    "forward_from_parity",
    "forward_price",
    "parity_residual",
    "put_from_call",
    "binomial_greeks",
    "binomial_price",
    "binomial_price_two_step_average",
    "crr_params",
    "early_exercise_boundary",
    "lr_params",
    "implied_vol",
    "implied_vol_black76",
    "price_bounds",
]
