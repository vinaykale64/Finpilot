"""
Market data fetching via yfinance.
Provides current price, upcoming events, and options chain data.
"""
from datetime import date, timedelta
from typing import Optional, Union
import yfinance as yf
import pandas as pd

from .models import MarketEvent, OptionPosition, StockPosition


def fetch_current_price(ticker: str) -> Optional[float]:
    """Return the latest market price for a ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = info.last_price
        if price and price > 0:
            return float(price)
        # fallback: last close
        hist = t.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception:
        return None


def fetch_option_mark(ticker: str, option_type: str, strike: float, expiry: date) -> Optional[float]:
    """Return the current mark price (mid of bid/ask) for a specific option contract."""
    try:
        t = yf.Ticker(ticker)
        expiry_str = expiry.strftime("%Y-%m-%d")
        chain = t.option_chain(expiry_str)
        df = chain.calls if option_type == "call" else chain.puts
        row = df[df["strike"] == strike]
        if row.empty:
            # find closest strike
            idx = (df["strike"] - strike).abs().idxmin()
            row = df.loc[[idx]]
        if row.empty:
            return None
        bid = row["bid"].iloc[0]
        ask = row["ask"].iloc[0]
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2, 4)
        return float(row["lastPrice"].iloc[0])
    except Exception:
        return None


def fetch_events(
    ticker: str,
    position: Union[StockPosition, OptionPosition],
) -> list[MarketEvent]:
    """
    Fetch all relevant market events within the event horizon:
    - Stocks: up to 12 months from today
    - Options: up to the expiry date
    """
    today = date.today()
    if isinstance(position, OptionPosition):
        horizon = position.expiry
    else:
        horizon = today + timedelta(days=365)

    events: list[MarketEvent] = []

    try:
        t = yf.Ticker(ticker)
        info = t.info

        # --- Earnings dates ---
        cal = t.calendar
        if cal is not None and not cal.empty:
            # yfinance returns a DataFrame with dates as columns
            for col in cal.columns:
                try:
                    earnings_date = pd.Timestamp(col).date()
                except Exception:
                    continue
                if today <= earnings_date <= horizon:
                    events.append(MarketEvent(
                        event_type="earnings",
                        date=earnings_date,
                        label=f"Earnings on {earnings_date.strftime('%b %d, %Y')}",
                    ))

        # --- Ex-dividend date ---
        ex_div_raw = info.get("exDividendDate")
        if ex_div_raw:
            try:
                ex_div = pd.Timestamp(ex_div_raw, unit="s").date()
                if today <= ex_div <= horizon:
                    events.append(MarketEvent(
                        event_type="ex_dividend",
                        date=ex_div,
                        label=f"Ex-dividend on {ex_div.strftime('%b %d, %Y')}",
                    ))
            except Exception:
                pass

        # --- Option expiry as an event ---
        if isinstance(position, OptionPosition):
            events.append(MarketEvent(
                event_type="expiry",
                date=position.expiry,
                label=f"Option expires on {position.expiry.strftime('%b %d, %Y')}",
            ))

    except Exception:
        pass

    events.sort(key=lambda e: e.date)
    return events


def fetch_expiry_dates(ticker: str) -> list[date]:
    """Return available option expiry dates for a ticker, sorted ascending."""
    try:
        t = yf.Ticker(ticker)
        expiries = t.options  # tuple of "YYYY-MM-DD" strings
        if not expiries:
            return []
        today = date.today()
        return sorted([date.fromisoformat(e) for e in expiries if date.fromisoformat(e) > today])
    except Exception:
        return []


def fetch_options_chain_for_rolls(
    ticker: str,
    current_position: OptionPosition,
    current_price: float,
) -> pd.DataFrame:
    """
    Fetch options chain data needed for roll analysis.
    Returns a DataFrame of candidates beyond current expiry,
    within ±20% of current price, with sufficient liquidity.
    """
    try:
        t = yf.Ticker(ticker)
        all_expiries = t.options  # tuple of expiry strings "YYYY-MM-DD"
        if not all_expiries:
            return pd.DataFrame()

        min_new_expiry = current_position.expiry + timedelta(days=14)
        price_low = current_price * 0.80
        price_high = current_price * 1.20

        rows = []
        for expiry_str in all_expiries:
            expiry_date = date.fromisoformat(expiry_str)
            if expiry_date < min_new_expiry:
                continue

            try:
                chain = t.option_chain(expiry_str)
                df = chain.calls if current_position.option_type == "call" else chain.puts
            except Exception:
                continue

            df = df[
                (df["strike"] >= price_low) &
                (df["strike"] <= price_high) &
                (df["openInterest"] > 100) &
                (df["bid"] > 0)
            ].copy()

            if df.empty:
                continue

            df["expiry"] = expiry_date
            df["mark"] = (df["bid"] + df["ask"]) / 2
            rows.append(df[["strike", "expiry", "mark", "bid", "ask", "openInterest", "impliedVolatility"]])

        if not rows:
            return pd.DataFrame()

        return pd.concat(rows, ignore_index=True)

    except Exception:
        return pd.DataFrame()
