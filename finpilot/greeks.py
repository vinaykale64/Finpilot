"""
Black-Scholes Greeks calculator.
Uses only math/numpy — no additional dependencies.
Risk-free rate is approximated at 4.5% (US 10Y Treasury proxy).
"""
import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

RISK_FREE_RATE = 0.045  # ~current US 10Y


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@dataclass
class Greeks:
    delta: float    # $ change in option per $1 move in stock
    gamma: float    # rate of change of delta per $1 move
    theta: float    # $ lost per calendar day (time decay)
    vega: float     # $ change per 1% rise in implied volatility
    rho: float      # $ change per 1% rise in interest rates
    iv: float       # implied volatility used (as a decimal, e.g. 0.35 = 35%)


def calculate_greeks(
    option_type: str,        # "call" or "put"
    position_dir: str,       # "long" or "short"
    S: float,                # current stock price
    K: float,                # strike price
    expiry: date,            # expiry date
    iv: float,               # implied volatility as decimal (e.g. 0.35)
    contracts: int = 1,
) -> Optional[Greeks]:
    """
    Compute Black-Scholes Greeks scaled to the full position.
    Returns None if inputs are invalid (e.g. expired, zero IV).
    """
    T = (expiry - date.today()).days / 365.0
    if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
        return None

    r = RISK_FREE_RATE
    sigma = iv

    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
    except (ValueError, ZeroDivisionError):
        return None

    nd1  = _norm_cdf(d1)
    nd2  = _norm_cdf(d2)
    nnd1 = _norm_cdf(-d1)
    nnd2 = _norm_cdf(-d2)
    npd1 = _norm_pdf(d1)
    disc = math.exp(-r * T)

    if option_type == "call":
        delta = nd1
        theta_annual = (
            -(S * npd1 * sigma) / (2 * math.sqrt(T))
            - r * K * disc * nd2
        )
        rho_annual = K * T * disc * nd2
    else:  # put
        delta = nd1 - 1.0
        theta_annual = (
            -(S * npd1 * sigma) / (2 * math.sqrt(T))
            + r * K * disc * nnd2
        )
        rho_annual = -K * T * disc * nnd2

    gamma = npd1 / (S * sigma * math.sqrt(T))
    vega_annual = S * npd1 * math.sqrt(T)

    # Scale to per-share, per-day / per-1%-change units
    theta_daily = theta_annual / 365.0         # $ per day per share
    vega_pct    = vega_annual / 100.0          # $ per 1% IV change per share
    rho_pct     = rho_annual / 100.0           # $ per 1% rate change per share

    # Scale to full position (1 contract = 100 shares)
    scale = 100 * contracts
    sign = 1 if position_dir == "long" else -1

    return Greeks(
        delta=round(sign * delta, 4),
        gamma=round(sign * gamma, 4),          # always positive for long, negative for short
        theta=round(sign * theta_daily * scale, 2),   # $ per day, full position
        vega=round(sign * vega_pct * scale, 2),       # $ per 1% IV, full position
        rho=round(sign * rho_pct * scale, 2),         # $ per 1% rate, full position
        iv=round(iv * 100, 1),                        # store as percentage e.g. 35.0
    )


# Plain-English explanations keyed to position direction
def greeks_explanations(g: Greeks, option_type: str, position_dir: str, ticker: str) -> dict[str, str]:
    direction = "up" if option_type == "call" else "down"
    delta_abs = abs(g.delta)

    return {
        "Delta": (
            f"For every $1 {ticker} moves {direction}, your position gains ~${delta_abs * 100:.0f} "
            f"(delta {g.delta:+.2f} per share)."
            if position_dir == "long"
            else f"For every $1 {ticker} moves {direction}, your position loses ~${delta_abs * 100:.0f} "
            f"(delta {g.delta:+.2f} per share)."
        ),
        "Gamma": (
            f"Your delta is {'accelerating' if abs(g.gamma) > 0.005 else 'fairly stable'} — "
            f"as {ticker} moves, each $1 changes your delta by {abs(g.gamma):.4f}."
        ),
        "Theta": (
            f"{'You lose' if g.theta < 0 else 'You gain'} ~${abs(g.theta):,.2f}/day "
            f"just from time passing, even if {ticker} doesn't move."
        ),
        "Vega": (
            f"If implied volatility (IV — the market's expectation of how much the stock will swing) "
            f"rises 1%, your position {'gains' if g.vega > 0 else 'loses'} "
            f"~${abs(g.vega):,.2f}. {'High IV benefits you.' if g.vega > 0 else 'High IV hurts you.'}"
        ),
        "Rho": (
            f"If interest rates rise 1%, your position {'gains' if g.rho > 0 else 'loses'} "
            f"~${abs(g.rho):,.2f}. Usually the smallest factor for short-dated options."
        ),
    }
