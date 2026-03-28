from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Literal


@dataclass
class StockPosition:
    ticker: str
    shares: float
    cost_basis: float  # per share
    entry_date: Optional[date] = None

    @property
    def total_cost(self) -> float:
        return self.shares * self.cost_basis

    def pnl(self, current_price: float) -> float:
        return (current_price - self.cost_basis) * self.shares

    def pnl_pct(self, current_price: float) -> float:
        return (current_price - self.cost_basis) / self.cost_basis * 100


@dataclass
class OptionPosition:
    ticker: str
    option_type: Literal["call", "put"]
    position: Literal["long", "short"]
    strike: float
    expiry: date
    premium: float   # per share (multiply by 100 for contract cost)
    contracts: int

    @property
    def total_cost(self) -> float:
        # long = paid premium, short = received premium
        multiplier = 1 if self.position == "long" else -1
        return multiplier * self.premium * 100 * self.contracts

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry - date.today()).days

    def pnl(self, current_mark: float) -> float:
        if self.position == "long":
            return (current_mark - self.premium) * 100 * self.contracts
        else:
            return (self.premium - current_mark) * 100 * self.contracts

    def pnl_pct(self, current_mark: float) -> float:
        if self.premium == 0:
            return 0.0
        if self.position == "long":
            return (current_mark - self.premium) / self.premium * 100
        else:
            return (self.premium - current_mark) / self.premium * 100

    def breakeven_price(self) -> float:
        if self.option_type == "call":
            return self.strike + self.premium
        else:
            return self.strike - self.premium


@dataclass
class MarketEvent:
    event_type: Literal["earnings", "ex_dividend", "expiry", "fed_meeting"]
    date: date
    label: str  # human-readable description

    @property
    def days_away(self) -> int:
        return (self.date - date.today()).days

    @property
    def urgency(self) -> Literal["critical", "soon", "on_radar"]:
        if self.days_away <= 7:
            return "critical"
        elif self.days_away <= 30:
            return "soon"
        else:
            return "on_radar"


@dataclass
class RollCandidate:
    new_strike: float
    new_expiry: date
    new_premium: float       # mark price of the new option
    cost_to_close: float     # mark price of existing option (used for display only)
    roll_label: str          # plain-English label
    roll_type: Literal["same_strike_out", "better_strike", "credit_roll"]
    # Correctly signed: positive = net credit (you receive), negative = net debit (you pay).
    # Computed in rank_roll_candidates with position direction applied:
    #   long:  current_mark - new_mark  (sell to close, buy to open)
    #   short: new_mark - current_mark  (buy to close, sell to open)
    net_value: float = 0.0
    current_expiry: date = None       # original position expiry, used to compute extra_days
    original_premium: float = 0.0    # premium paid/received on the original position

    @property
    def net_debit_credit(self) -> float:
        """positive = you receive (credit), negative = you pay (debit)."""
        return self.net_value

    @property
    def extra_days(self) -> int:
        """Days gained over the current position's expiry, not from today."""
        if self.current_expiry:
            return (self.new_expiry - self.current_expiry).days
        return (self.new_expiry - date.today()).days

    def new_breakeven(self, option_type: str, position_dir: str) -> float:
        """
        All-in break-even accounting for total cash invested across the original
        position and the roll.

        Long:  total_invested = original_premium - current_mark + new_premium
                                (paid originally, received on close, paid to open new)
               long  call: new_strike + total_invested
               long  put:  new_strike - total_invested

        Short: total_received = original_premium - current_mark + new_premium
                                (received originally, paid to close, received to open new)
               short call: new_strike + total_received
               short put:  new_strike - total_received
        """
        if position_dir == "long":
            total = self.original_premium - self.cost_to_close + self.new_premium
            if option_type == "call":
                return self.new_strike + total
            else:
                return self.new_strike - total
        else:  # short
            total = self.original_premium - self.cost_to_close + self.new_premium
            if option_type == "call":
                return self.new_strike + total
            else:
                return self.new_strike - total


@dataclass
class Scenario:
    action_label: str           # plain-English title
    key_numbers: dict           # e.g. {"Net proceeds": "$1,240", "Gain": "+$240"}
    tradeoff: str               # one-line trade-off description
    narrative: str = ""         # filled in by LLM
    roll_candidate: Optional[RollCandidate] = None
