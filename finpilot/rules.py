"""
Rule engine: evaluates position state and generates scenarios.
All labels and trade-offs are in plain English — no jargon.
"""
from typing import Union
import pandas as pd

from .models import (
    MarketEvent,
    OptionPosition,
    RollCandidate,
    Scenario,
    StockPosition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_dollar(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:,.2f}"


def _fmt_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _has_imminent_earnings(events: list[MarketEvent]) -> bool:
    return any(e.event_type == "earnings" and e.days_away <= 5 for e in events)


# ---------------------------------------------------------------------------
# Stock scenarios
# ---------------------------------------------------------------------------

def stock_scenarios(
    position: StockPosition,
    current_price: float,
    events: list[MarketEvent],
) -> list[Scenario]:
    pnl = position.pnl(current_price)
    pnl_pct = position.pnl_pct(current_price)
    in_profit = pnl >= 0
    near_breakeven = abs(pnl_pct) <= 2.0
    imminent_earnings = _has_imminent_earnings(events)

    scenarios: list[Scenario] = []

    if in_profit and not near_breakeven:
        # --- In Profit ---
        net_proceeds = current_price * position.shares
        scenarios.append(Scenario(
            action_label="Lock in your gains — sell everything",
            key_numbers={
                "You'd receive": f"${net_proceeds:,.2f}",
                "Your gain": _fmt_dollar(pnl),
                "Return": _fmt_pct(pnl_pct),
            },
            tradeoff="You walk away with the profit, but give up any future upside.",
        ))

        half_gain = pnl / 2
        scenarios.append(Scenario(
            action_label="Sell half, keep the rest",
            key_numbers={
                "You'd receive": f"${(net_proceeds / 2):,.2f}",
                "Locked-in gain": _fmt_dollar(half_gain),
                "Remaining shares": f"{position.shares / 2:,.0f}",
            },
            tradeoff="You secure some profit while staying in if the stock keeps climbing.",
        ))

        reversal_loss = position.pnl(position.cost_basis * 0.90)
        scenarios.append(Scenario(
            action_label="Hold and let it run",
            key_numbers={
                "Current gain": _fmt_dollar(pnl),
                "If it drops 10% from here": _fmt_dollar((current_price * 0.9 - position.cost_basis) * position.shares),
                "Your break-even price": f"${position.cost_basis:,.2f}",
            },
            tradeoff="You keep upside exposure, but gains can shrink if the stock pulls back.",
        ))

        new_avg = (position.total_cost + current_price * position.shares) / (position.shares * 2)
        scenarios.append(Scenario(
            action_label="Buy more shares",
            key_numbers={
                "New average price you'd pay": f"${new_avg:,.2f}",
                "New break-even": f"${new_avg:,.2f}",
                "Extra cost": f"${current_price * position.shares:,.2f}",
            },
            tradeoff="Doubles your exposure — bigger gain if it keeps going up, bigger loss if it reverses.",
        ))

        if imminent_earnings:
            scenarios.append(Scenario(
                action_label="Sell before earnings to protect your gain",
                key_numbers={
                    "You'd lock in": _fmt_dollar(pnl),
                    "Earnings in": f"{next(e.days_away for e in events if e.event_type == 'earnings' and e.days_away <= 5)} days",
                },
                tradeoff="You avoid the risk of the stock dropping on the earnings report, but miss out if it pops.",
            ))

    elif not in_profit and not near_breakeven:
        # --- At Loss ---
        recovery_needed_pct = (position.cost_basis - current_price) / current_price * 100
        new_avg_if_double = (position.total_cost + current_price * position.shares) / (position.shares * 2)

        scenarios.append(Scenario(
            action_label="Sell now and stop the bleeding",
            key_numbers={
                "You'd receive": f"${current_price * position.shares:,.2f}",
                "Your loss": _fmt_dollar(pnl),
                "Loss %": _fmt_pct(pnl_pct),
            },
            tradeoff="You take the loss now and free up your cash. Potential upside: tax benefit on the loss.",
        ))

        scenarios.append(Scenario(
            action_label="Buy more to lower your average cost",
            key_numbers={
                "New average price": f"${new_avg_if_double:,.2f}",
                "Stock needs to reach": f"${new_avg_if_double:,.2f} to break even",
                "Extra cash needed": f"${current_price * position.shares:,.2f}",
            },
            tradeoff="Lowers the price you need to recover — but you're putting more money into a losing position.",
        ))

        scenarios.append(Scenario(
            action_label="Hold and wait for recovery",
            key_numbers={
                "Stock needs to rise": f"{recovery_needed_pct:.1f}% to get back to what you paid",
                "Your break-even price": f"${position.cost_basis:,.2f}",
                "Current loss": _fmt_dollar(pnl),
            },
            tradeoff="No extra cost, but your money is tied up and the stock could keep falling.",
        ))

        stop_level = current_price * 0.93
        scenarios.append(Scenario(
            action_label="Set a floor — decide your exit price now",
            key_numbers={
                "Suggested stop price": f"${stop_level:,.2f} (7% below current)",
                "Max additional loss if triggered": _fmt_dollar((stop_level - position.cost_basis) * position.shares),
            },
            tradeoff="Limits how much worse it can get. You stay in for recovery but have a safety net.",
        ))

    else:
        # --- Near Breakeven ---
        scenarios.append(Scenario(
            action_label="Sell and walk away flat",
            key_numbers={
                "You'd receive": f"${current_price * position.shares:,.2f}",
                "Gain/Loss": _fmt_dollar(pnl),
            },
            tradeoff="You recover almost all of your money with minimal loss or gain.",
        ))

        scenarios.append(Scenario(
            action_label="Hold — you're close to breakeven",
            key_numbers={
                "Your break-even price": f"${position.cost_basis:,.2f}",
                "Current price": f"${current_price:,.2f}",
                "Difference": _fmt_dollar(pnl),
            },
            tradeoff="Small move either way determines your outcome. Low-stakes moment to decide direction.",
        ))

    return scenarios


# ---------------------------------------------------------------------------
# Roll trade-off copy
# ---------------------------------------------------------------------------

def _roll_tradeoff(
    candidate: RollCandidate,
    net: float,
    net_per_contract: float,
    new_be: float,
    current_price: float,
    position: OptionPosition,
) -> str:
    if net > 0:
        return (
            f"You collect ${abs(net):,.2f}/share (${net_per_contract:,.2f} total) to extend the trade — "
            f"rare and usually worth considering. Stock needs to reach ${new_be:,.2f} to recover everything "
            f"({((new_be / current_price - 1) * 100):+.1f}% from current ${current_price:,.2f})."
        )

    pct_to_be = (new_be / current_price - 1) * 100
    itm = (
        (position.option_type == "call" and candidate.new_strike < current_price) or
        (position.option_type == "put" and candidate.new_strike > current_price)
    )
    strike_context = (
        f"The new ${candidate.new_strike:,.2f} strike is in the money (stock is at ${current_price:,.2f})."
        if itm
        else f"The new ${candidate.new_strike:,.2f} strike is still out of the money (stock is at ${current_price:,.2f})."
    )
    return (
        f"You pay ${abs(net):,.2f}/share (${net_per_contract:,.2f} total) to roll. "
        f"{strike_context} "
        f"Stock needs to reach ${new_be:,.2f} to recover everything ({pct_to_be:+.1f}% from here)."
    )


# ---------------------------------------------------------------------------
# Options scenarios
# ---------------------------------------------------------------------------

def option_scenarios(
    position: OptionPosition,
    current_mark: float,
    current_price: float,
    events: list[MarketEvent],
    roll_candidates: list[RollCandidate],
    theta_per_day: float = None,
) -> list[Scenario]:
    pnl = position.pnl(current_mark)
    pnl_pct = position.pnl_pct(current_mark)
    in_profit = pnl >= 0
    dte = position.days_to_expiry
    expiring_soon = dte <= 7
    imminent_earnings = _has_imminent_earnings(events)
    breakeven = position.breakeven_price()
    contract_value = current_mark * 100 * position.contracts
    # Use Black-Scholes theta if provided, else fall back to linear estimate
    daily_decay = theta_per_day if theta_per_day is not None else (current_mark / max(dte, 1)) * 100 * position.contracts

    scenarios: list[Scenario] = []

    if position.position == "long":
        # Sell now
        scenarios.append(Scenario(
            action_label="Sell the option now" if in_profit else "Sell now and limit the damage",
            key_numbers={
                "You'd receive": f"${contract_value:,.2f}",
                "Your P&L": _fmt_dollar(pnl),
                "Return on premium": _fmt_pct(pnl_pct),
            },
            tradeoff="Locks in your current result — profit or partial recovery — and ends the risk." if in_profit
                     else "Cuts your loss before it gets worse. The option still has some value today.",
        ))

        # Hold to expiry
        scenarios.append(Scenario(
            action_label="Hold to expiry",
            key_numbers={
                "Stock must reach by expiry": f"${breakeven:,.2f}",
                "Days remaining": str(dte),
                "Daily time cost": f"~${daily_decay:,.2f}/day",
            },
            tradeoff="Maximum upside potential, but time is working against you — the option loses value daily.",
        ))

        # Sell partial
        if position.contracts > 1:
            half = position.contracts // 2
            partial_value = current_mark * 100 * half
            scenarios.append(Scenario(
                action_label="Sell half your contracts",
                key_numbers={
                    "Proceeds from partial sale": f"${partial_value:,.2f}",
                    "Contracts remaining": str(position.contracts - half),
                },
                tradeoff="Reduces risk and recovers some cash while keeping upside exposure with remaining contracts.",
            ))

        # Earnings warning scenario
        if imminent_earnings:
            earnings_event = next(e for e in events if e.event_type == "earnings" and e.days_away <= 5)
            scenarios.append(Scenario(
                action_label="Close before earnings (important)",
                key_numbers={
                    "Earnings in": f"{earnings_event.days_away} days",
                    "Current option value": f"${contract_value:,.2f}",
                },
                tradeoff="Option prices often drop sharply right after earnings — even when the stock moves your way. Selling before locks in the current inflated value.",
            ))

        if expiring_soon and not in_profit:
            scenarios.append(Scenario(
                action_label="Close now to recover what's left",
                key_numbers={
                    "Days to expiry": str(dte),
                    "Current value": f"${contract_value:,.2f}",
                    "Value at expiry if OTM": "$0.00",
                },
                tradeoff="With little time left and out of the money, selling now recovers something. Waiting risks it expiring worthless.",
            ))

    else:
        # Short position
        cost_to_close = current_mark * 100 * position.contracts
        max_profit = position.premium * 100 * position.contracts

        scenarios.append(Scenario(
            action_label="Buy it back and close the position",
            key_numbers={
                "Cost to close": f"${cost_to_close:,.2f}",
                "Your P&L": _fmt_dollar(pnl),
                "Return on premium received": _fmt_pct(pnl_pct),
            },
            tradeoff="Ends your obligation and locks in current profit. Eliminates the risk of the trade moving against you.",
        ))

        scenarios.append(Scenario(
            action_label="Hold to expiry and keep the full premium",
            key_numbers={
                "Maximum profit (if expires worthless)": f"${max_profit:,.2f}",
                "Days remaining": str(dte),
                "Break-even price": f"${breakeven:,.2f}",
            },
            tradeoff="Keeps maximum profit potential — but you remain at risk if the stock moves past your break-even.",
        ))

        if imminent_earnings:
            earnings_event = next(e for e in events if e.event_type == "earnings" and e.days_away <= 5)
            scenarios.append(Scenario(
                action_label="Close before earnings to remove the risk",
                key_numbers={
                    "Earnings in": f"{earnings_event.days_away} days",
                    "Cost to close now": f"${cost_to_close:,.2f}",
                    "Profit locked in": _fmt_dollar(pnl),
                },
                tradeoff="Earnings can cause large sudden moves. Closing now removes the chance of an unexpected loss.",
            ))

    # Roll scenarios (for both long and short)
    for candidate in roll_candidates[:3]:
        net = candidate.net_debit_credit  # positive=credit, negative=debit
        net_per_contract = abs(net) * 100 * position.contracts
        net_label = (
            f"You collect ${abs(net):,.2f}/share (${net_per_contract:,.2f} total)"
            if net > 0
            else f"You pay ${abs(net):,.2f}/share (${net_per_contract:,.2f} total)"
        )
        # New cost basis = total invested per share after the roll
        # Long:  original premium paid + roll debit (or minus roll credit)
        # Short: original premium received + roll credit (or minus roll debit)
        new_cost_basis_per_share = position.premium - net  # net positive=credit reduces basis
        new_cost_basis_total = abs(new_cost_basis_per_share) * 100 * position.contracts
        cost_basis_label = (
            f"${new_cost_basis_per_share:,.2f}/share (${new_cost_basis_total:,.2f} total)"
        )
        new_be = candidate.new_breakeven(position.option_type, position.position)
        scenarios.append(Scenario(
            action_label=candidate.roll_label,
            key_numbers={
                "New strike": f"${candidate.new_strike:,.2f}",
                "New expiry": candidate.new_expiry.strftime("%b %d, %Y"),
                "Net additional cost / credit": net_label,
                "New cost basis": cost_basis_label,
                "All-in break-even": f"${new_be:,.2f}",
                "Extra time gained": f"{candidate.extra_days} days beyond current expiry",
            },
            tradeoff=_roll_tradeoff(candidate, net, net_per_contract, new_be, current_price, position),
            roll_candidate=candidate,
        ))

    return scenarios


# ---------------------------------------------------------------------------
# Roll candidate ranking
# ---------------------------------------------------------------------------

def rank_roll_candidates(
    position: OptionPosition,
    current_mark: float,
    chain_df: pd.DataFrame,
) -> list[RollCandidate]:
    """
    From the raw options chain DataFrame, compute roll math and return
    ranked RollCandidate objects (up to 3).
    """
    if chain_df.empty:
        return []

    cost_to_close = current_mark  # per share, position direction handled below
    candidates: list[RollCandidate] = []

    for _, row in chain_df.iterrows():
        new_strike = float(row["strike"])
        new_expiry = row["expiry"]
        new_mark = float(row["mark"])

        if position.position == "long":
            # long: close = sell current (receive current_mark), open = buy new (pay new_mark)
            net = current_mark - new_mark  # positive = net credit, negative = net debit
        else:
            # short: close = buy back current (pay current_mark), open = sell new (receive new_mark)
            net = new_mark - current_mark

        # Determine roll type and label
        same_strike = abs(new_strike - position.strike) < 0.01
        is_credit = net > 0

        # "Better" strike means directionally more favorable:
        #   long call  → lower strike (need stock to travel less)
        #   long put   → higher strike (need stock to fall less)
        #   short call → higher strike (more buffer before being tested)
        #   short put  → lower strike (more buffer before being tested)
        if position.position == "long" and position.option_type == "call":
            is_better_strike = new_strike < position.strike
        elif position.position == "long" and position.option_type == "put":
            is_better_strike = new_strike > position.strike
        elif position.position == "short" and position.option_type == "call":
            is_better_strike = new_strike > position.strike
        else:  # short put
            is_better_strike = new_strike < position.strike

        if is_credit:
            roll_type = "credit_roll"
            label = "Move out and get paid to do it"
        elif same_strike:
            roll_type = "same_strike_out"
            label = "Buy more time at the same target price"
        elif is_better_strike:
            roll_type = "better_strike"
            label = "Move to a more reachable price, pay a fee"
        else:
            # Worse strike direction — skip this candidate
            continue

        candidates.append(RollCandidate(
            new_strike=new_strike,
            new_expiry=new_expiry,
            new_premium=new_mark,
            cost_to_close=cost_to_close,
            roll_label=label,
            roll_type=roll_type,
            net_value=net,  # correctly signed: positive=credit, negative=debit
            current_expiry=position.expiry,
            original_premium=position.premium,
        ))

    # Rank: credit rolls first, then same-strike, then better-strike
    # Deduplicate: one per roll type, pick best candidate within each type
    want_lower_breakeven = (
        (position.position == "long" and position.option_type == "call") or
        (position.position == "short" and position.option_type == "put")
    )

    ranked: list[RollCandidate] = []
    for preferred_type in ("credit_roll", "same_strike_out", "better_strike"):
        pool = [c for c in candidates if c.roll_type == preferred_type]
        if not pool:
            continue
        if preferred_type == "better_strike":
            # Pick the candidate with the most favorable all-in break-even
            key_fn = lambda c: c.new_breakeven(position.option_type, position.position)
            best = min(pool, key=key_fn) if want_lower_breakeven else max(pool, key=key_fn)
        else:
            # credit/same-strike: pick the one with most credit or least debit
            best = max(pool, key=lambda c: c.net_value)
        ranked.append(best)

    return ranked[:3]
