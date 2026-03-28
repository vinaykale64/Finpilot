"""
Market data fetching via yfinance.
Provides current price, upcoming events, and options chain data.
"""
from datetime import date, timedelta
from typing import Optional, Union
import yfinance as yf
import pandas as pd

from .models import MarketEvent, OptionPosition, StockPosition

# FOMC meeting dates (last day of each meeting — decision day).
# Source: federalreserve.gov. Update annually.
_FOMC_DATES = [
    # 2025
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7),
    date(2025, 6, 18), date(2025, 7, 30), date(2025, 9, 17),
    date(2025, 10, 29), date(2025, 12, 10),
    # 2026
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
    date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
    date(2026, 10, 28), date(2026, 12, 9),
    # 2027 (preliminary — confirm at federalreserve.gov)
    date(2027, 1, 27), date(2027, 3, 17), date(2027, 5, 5),
    date(2027, 6, 16), date(2027, 7, 28), date(2027, 9, 15),
    date(2027, 10, 27), date(2027, 12, 8),
]


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
        known_earnings: list[date] = []
        try:
            ed = t.earnings_dates  # property, not callable
            if ed is not None and not ed.empty:
                for ts in ed.index:
                    try:
                        known_earnings.append(pd.Timestamp(ts).normalize().date())
                    except Exception:
                        continue
        except Exception:
            pass

        # Fallback: calendar dict (returns next confirmed date)
        if not known_earnings:
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    for d in cal.get("Earnings Date", []):
                        try:
                            known_earnings.append(pd.Timestamp(d).date())
                        except Exception:
                            continue
            except Exception:
                pass

        if known_earnings:
            known_earnings.sort()

            # Add any confirmed future dates
            for d in known_earnings:
                if today <= d <= horizon:
                    events.append(MarketEvent(
                        event_type="earnings",
                        date=d,
                        label=f"Earnings on {d.strftime('%b %d, %Y')}",
                    ))

            # Project forward quarterly from the latest known date
            # until we cover the full horizon
            latest = max(known_earnings)
            next_est = latest + timedelta(days=91)
            while next_est <= horizon:
                already_covered = any(
                    abs((next_est - e.date).days) <= 21
                    for e in events if e.event_type == "earnings"
                )
                if not already_covered:
                    events.append(MarketEvent(
                        event_type="earnings",
                        date=next_est,
                        label=f"Earnings ~{next_est.strftime('%b %d, %Y')} (est.)",
                    ))
                next_est += timedelta(days=91)

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

    # --- Fed meeting dates (hardcoded from FOMC calendar) ---
    for fomc_date in _FOMC_DATES:
        if today <= fomc_date <= horizon:
            events.append(MarketEvent(
                event_type="fed_meeting",
                date=fomc_date,
                label=f"Fed decision on {fomc_date.strftime('%b %d, %Y')}",
            ))

    events.sort(key=lambda e: e.date)
    return events


def fetch_stock_snapshot(ticker: str) -> dict:
    """
    Fetch key stock metrics for context: 52w range, beta, volume, valuation.
    Returns a dict — any field may be None if unavailable.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low":  info.get("fiftyTwoWeekLow"),
            "current_price": info.get("currentPrice"),
            "beta":          info.get("beta"),
            "forward_pe":    info.get("forwardPE"),
            "trailing_pe":   info.get("trailingPE"),
            "volume":        info.get("volume"),
            "avg_volume":    info.get("averageVolume"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth":  info.get("revenueGrowth"),
            "short_ratio":   info.get("shortRatio"),
            "market_cap":    info.get("marketCap"),
        }
    except Exception:
        return {}


def fetch_analyst_data(ticker: str) -> dict:
    """
    Fetch analyst consensus ratings and price targets.
    Returns a dict with keys: summary, price_targets, recent_changes.
    Any field may be None if unavailable.
    """
    try:
        t = yf.Ticker(ticker)
        result = {"summary": None, "price_targets": None, "recent_changes": None}

        # Ratings summary (current month)
        try:
            rec = t.recommendations_summary
            if rec is not None and not rec.empty:
                row = rec[rec["period"] == "0m"].iloc[0]
                result["summary"] = {
                    "strong_buy": int(row["strongBuy"]),
                    "buy": int(row["buy"]),
                    "hold": int(row["hold"]),
                    "sell": int(row["sell"]),
                    "strong_sell": int(row["strongSell"]),
                }
        except Exception:
            pass

        # Price targets
        try:
            pt = t.analyst_price_targets
            if pt and pt.get("mean"):
                result["price_targets"] = {
                    "current": round(pt["current"], 2),
                    "mean": round(pt["mean"], 2),
                    "high": round(pt["high"], 2),
                    "low": round(pt["low"], 2),
                    "median": round(pt["median"], 2),
                }
        except Exception:
            pass

        # Recent upgrades/downgrades (last 5)
        try:
            ud = t.upgrades_downgrades
            if ud is not None and not ud.empty:
                recent = ud.head(5).reset_index()
                changes = []
                for _, row in recent.iterrows():
                    changes.append({
                        "date": pd.Timestamp(row["GradeDate"]).date(),
                        "firm": row.get("Firm", ""),
                        "to_grade": row.get("ToGrade", ""),
                        "from_grade": row.get("FromGrade", ""),
                        "action": row.get("Action", ""),
                    })
                result["recent_changes"] = changes
        except Exception:
            pass

        return result
    except Exception:
        return {"summary": None, "price_targets": None, "recent_changes": None}


def fetch_strikes_for_expiry(ticker: str, expiry: date, option_type: str) -> list[float]:
    """Return sorted list of available strike prices for a given expiry and option type."""
    try:
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry.strftime("%Y-%m-%d"))
        df = chain.calls if option_type == "call" else chain.puts
        strikes = sorted(df["strike"].dropna().unique().tolist())
        return [float(s) for s in strikes]
    except Exception:
        return []


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
