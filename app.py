"""
Finpilot — Know your options.
Streamlit app entry point.
"""
import os
import streamlit as st
from datetime import date, timedelta
from typing import Union
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

from finpilot.models import StockPosition, OptionPosition, MarketEvent, Scenario
from finpilot.fetcher import (
    fetch_current_price,
    fetch_expiry_dates,
    fetch_option_mark,
    fetch_events,
    fetch_options_chain_for_rolls,
)
from finpilot.rules import stock_scenarios, option_scenarios, rank_roll_candidates
from finpilot.llm import generate_all_narratives
from finpilot.greeks import calculate_greeks, greeks_explanations
import plotly.graph_objects as go
import yfinance as yf

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Finpilot",
    page_icon="✈️",
    layout="wide",
)

DEFAULT_LLM_MODEL = "anthropic/claude-sonnet-4-6"

URGENCY_COLOR = {
    "critical": "#ff4b4b",
    "soon": "#ffa500",
    "on_radar": "#4b9fff",
}

EVENT_ICON = {
    "earnings": "📊",
    "ex_dividend": "💵",
    "expiry": "⏰",
}

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "selected_model" not in st.session_state:
    st.session_state.selected_model = DEFAULT_LLM_MODEL
if "option_expiries" not in st.session_state:
    st.session_state.option_expiries = []   # list[date]
if "option_expiry_ticker" not in st.session_state:
    st.session_state.option_expiry_ticker = ""


# ---------------------------------------------------------------------------
# Sidebar — API key + model
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("✈️ Finpilot")
    st.caption("Know your options.")
    st.divider()

    if OPENROUTER_KEY:
        st.success("OpenRouter key loaded ✓")
    else:
        st.warning("No OPENROUTER_API_KEY found in .env — AI explanations disabled.")



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_event_banner(event: MarketEvent):
    color = URGENCY_COLOR[event.urgency]
    icon = EVENT_ICON[event.event_type]
    urgency_label = {"critical": "URGENT", "soon": "SOON", "on_radar": "UPCOMING"}[event.urgency]

    if event.event_type == "earnings":
        detail = "Stock prices can move sharply. Options often get more expensive before earnings, then drop right after."
    elif event.event_type == "ex_dividend":
        detail = "If you're short a call option, early assignment risk increases around this date."
    else:
        detail = "After this date the option has no value — decisions become urgent."

    st.markdown(
        f"""<div style="border-left: 4px solid {color}; padding: 6px 10px; margin: 3px 0;
                        background: {color}18; border-radius: 4px; font-size: 0.85em;">
            <strong style="color:{color}">{icon} {urgency_label}: {event.label}</strong><br>
            <span style="color:#888">{detail}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def render_scenario_card(scenario: Scenario, index: int):
    with st.container(border=True):
        st.markdown(f"**{index + 1}. {scenario.action_label}**")

        # Key numbers — vertical layout avoids truncation
        kn_lines = "".join(
            f"<tr><td style='color:#888; padding: 2px 12px 2px 0; white-space:nowrap'>{label}</td>"
            f"<td style='font-weight:600; padding: 2px 0'>{value}</td></tr>"
            for label, value in scenario.key_numbers.items()
        )
        st.markdown(
            f"<table style='border-collapse:collapse; margin: 4px 0 6px 0; font-size:0.9em'>{kn_lines}</table>",
            unsafe_allow_html=True,
        )

        st.markdown("**Analysis**")
        tradeoff_safe = scenario.tradeoff.replace("$", r"\$")
        st.caption(tradeoff_safe)
        if scenario.narrative:
            st.info(scenario.narrative.replace("$", r"\$"), icon="💬")


def analyze_position(position: Union[StockPosition, OptionPosition]) -> dict:
    """Run full analysis pipeline for a position."""
    result = {"position": position, "error": None}

    if isinstance(position, StockPosition):
        current_price = fetch_current_price(position.ticker)
        if not current_price:
            result["error"] = f"Could not fetch price for {position.ticker.upper()}."
            return result
        events = fetch_events(position.ticker, position)
        scenarios = stock_scenarios(position, current_price, events)
        result.update({
            "current_price": current_price,
            "current_mark": None,
            "events": events,
            "scenarios": scenarios,
        })

    else:
        current_price = fetch_current_price(position.ticker)
        if not current_price:
            result["error"] = f"Could not fetch price for {position.ticker.upper()}."
            return result

        current_mark = fetch_option_mark(
            position.ticker, position.option_type, position.strike, position.expiry
        )
        if current_mark is None:
            current_mark = 0.01  # fallback — nearly worthless

        events = fetch_events(position.ticker, position)
        chain_df = fetch_options_chain_for_rolls(position.ticker, position, current_price)
        roll_candidates = rank_roll_candidates(position, current_mark, chain_df)

        # Greeks — compute BEFORE scenarios so theta can be passed in
        iv = None
        try:
            import yfinance as yf
            t = yf.Ticker(position.ticker)
            chain = t.option_chain(position.expiry.strftime("%Y-%m-%d"))
            df = chain.calls if position.option_type == "call" else chain.puts
            row = df[df["strike"] == position.strike]
            if row.empty:
                idx = (df["strike"] - position.strike).abs().idxmin()
                row = df.loc[[idx]]
            if not row.empty:
                iv = float(row["impliedVolatility"].iloc[0])
        except Exception:
            pass

        greeks = calculate_greeks(
            option_type=position.option_type,
            position_dir=position.position,
            S=current_price,
            K=position.strike,
            expiry=position.expiry,
            iv=iv or 0.35,
            contracts=position.contracts,
        )

        # Use Black-Scholes theta if available, else fall back to linear estimate
        theta_per_day = abs(greeks.theta) if greeks else None
        scenarios = option_scenarios(position, current_mark, current_price, events, roll_candidates, theta_per_day)

        result.update({
            "current_price": current_price,
            "current_mark": current_mark,
            "events": events,
            "roll_candidates": roll_candidates,
            "scenarios": scenarios,
            "greeks": greeks,
            "iv_source": "live" if iv else "estimated",
        })

    if OPENROUTER_KEY:
        result["scenarios"] = generate_all_narratives(
            result["scenarios"],
            position,
            result["current_mark"] if isinstance(position, OptionPosition) else result["current_price"],
            result["events"],
            OPENROUTER_KEY,
            st.session_state.selected_model,
        )

    return result


# ---------------------------------------------------------------------------
# Main — Header
# ---------------------------------------------------------------------------
st.title("✈️ Finpilot")
st.caption("Enter your position and see your options — in plain English.")

with st.expander("⚠️ Disclaimer", expanded=False):
    st.warning(
        "Finpilot is an informational tool only. Nothing on this app constitutes financial advice, "
        "a recommendation to buy or sell any security, or a solicitation of any kind. "
        "All analysis is generated automatically and may not reflect current market conditions. "
        "Always do your own research and consult a qualified financial advisor before making investment decisions."
    )

st.divider()

# ---------------------------------------------------------------------------
# Add Position form
# ---------------------------------------------------------------------------
st.subheader("Analyze a position")
tab_stock, tab_option = st.tabs(["📈 Stock", "🎯 Option"])

with tab_stock:
    with st.form("stock_form"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            s_ticker = st.text_input("Ticker", value="GOOG").upper().strip()
        with col2:
            s_shares = st.number_input("Number of shares", min_value=0.01, value=1.0, step=1.0)
        with col3:
            s_cost = st.number_input("Price you paid per share ($)", min_value=0.01, value=300.0, step=0.01)
        with col4:
            s_entry = st.date_input("Entry date (optional)", value=None)

        submitted_stock = st.form_submit_button("Fetch & Analyze", use_container_width=True)

    if submitted_stock:
        if not s_ticker:
            st.error("Please enter a ticker symbol.")
        else:
            with st.spinner(f"Fetching data for {s_ticker}..."):
                position = StockPosition(
                    ticker=s_ticker,
                    shares=s_shares,
                    cost_basis=s_cost,
                    entry_date=s_entry,
                )
                result = analyze_position(position)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.session_state.result = result
                    st.rerun()

with tab_option:
    # Step 1 — load expiry dates for a ticker (outside the form so it can rerender)
    exp_col1, exp_col2 = st.columns([2, 1])
    with exp_col1:
        o_ticker_load = st.text_input(
            "Ticker", value="GOOG", key="o_ticker_load"
        ).upper().strip()
    with exp_col2:
        st.write("")  # vertical alignment nudge
        st.write("")
        load_expiries = st.button("Load expiry dates", use_container_width=True)

    if load_expiries:
        if not o_ticker_load:
            st.error("Enter a ticker first.")
        else:
            with st.spinner(f"Fetching expiry dates for {o_ticker_load}..."):
                expiries = fetch_expiry_dates(o_ticker_load)
                if not expiries:
                    st.error(f"No option expiry dates found for {o_ticker_load}.")
                else:
                    st.session_state.option_expiries = expiries
                    st.session_state.option_expiry_ticker = o_ticker_load

    # Step 2 — rest of the form (shown once expiries are loaded)
    if st.session_state.option_expiries and st.session_state.option_expiry_ticker == o_ticker_load:
        with st.form("option_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                o_type = st.selectbox("Call or Put", ["call", "put"])
                o_position = st.selectbox("Long (bought) or Short (sold)", ["long", "short"])
            with col2:
                o_strike = st.number_input("Strike price ($)", min_value=0.01, value=200.0, step=0.50)
                expiry_options = st.session_state.option_expiries
                expiry_labels = [e.strftime("%b %d, %Y") for e in expiry_options]
                o_expiry_idx = st.selectbox("Expiry date", range(len(expiry_labels)), format_func=lambda i: expiry_labels[i])
            with col3:
                o_premium = st.number_input(
                    "Premium paid per share ($)",
                    min_value=0.01, value=5.00, step=0.05,
                    help="The price per share you paid/received. Multiply by 100 for total contract cost.",
                )
                o_contracts = st.number_input("Number of contracts", min_value=1, value=1, step=1)

            submitted_option = st.form_submit_button("Fetch & Analyze", use_container_width=True)

        if submitted_option:
            o_expiry = expiry_options[o_expiry_idx]
            with st.spinner(f"Fetching data for {o_ticker_load} options..."):
                position = OptionPosition(
                    ticker=o_ticker_load,
                    option_type=o_type,
                    position=o_position,
                    strike=o_strike,
                    expiry=o_expiry,
                    premium=o_premium,
                    contracts=int(o_contracts),
                )
                result = analyze_position(position)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.session_state.result = result
                    st.rerun()
    elif not st.session_state.option_expiries:
        st.caption("Enter a ticker and click **Load expiry dates** to continue.")


# ---------------------------------------------------------------------------
# Analysis result — single current position
# ---------------------------------------------------------------------------
st.divider()

if st.session_state.result is None:
    st.info("No position analyzed yet. Add one above to get started.")
else:
    entry = st.session_state.result
    pos = entry["position"]
    current_price = entry["current_price"]
    events = entry["events"]
    scenarios = entry["scenarios"]
    ticker = pos.ticker.upper()

    # --- Position summary ---
    if isinstance(pos, StockPosition):
        pnl = pos.pnl(current_price)
        pnl_pct = pos.pnl_pct(current_price)
        sign = "+" if pnl >= 0 else ""

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Ticker", ticker)
        col2.metric("Type", "Stock")
        col3.metric("You paid", f"${pos.cost_basis:,.2f}/share")
        col4.metric("Current price", f"${current_price:,.2f}")
        col5.metric("Your P&L", f"{sign}${abs(pnl):,.2f}", delta=f"{sign}{pnl_pct:.1f}%")

    else:
        current_mark = entry["current_mark"]
        pnl = pos.pnl(current_mark)
        pnl_pct = pos.pnl_pct(current_mark)
        sign = "+" if pnl >= 0 else ""

        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        col1.metric("Ticker", ticker)
        col2.metric("Type", f"{pos.position.title()} {pos.option_type.title()}")
        col3.metric("Strike", f"${pos.strike:,.2f}")
        col4.metric("Expires", pos.expiry.strftime("%b %d, %Y"))
        col5.metric("Stock price now", f"${current_price:,.2f}")
        col6.metric("Option value now", f"${current_mark:,.2f}/share")
        col7.metric("Your P&L", f"{sign}${abs(pnl):,.2f}", delta=f"{sign}{pnl_pct:.1f}%")

    # --- Stock price chart (stocks only) ---
    if isinstance(pos, StockPosition):
        today = date.today()
        range_options = ["1W", "1M", "3M", "YTD", "1Y"]
        selected_range = st.radio(
            "Range", range_options, index=0,
            horizontal=True, label_visibility="collapsed",
            key="stock_chart_range",
        )

        # Fetch hourly for short ranges, daily for longer ones
        use_hourly = selected_range in ("1W", "1M")
        range_start = {
            "1W":  today - timedelta(weeks=1),
            "1M":  today - timedelta(days=30),
            "3M":  today - timedelta(days=90),
            "YTD": date(today.year, 1, 1),
            "1Y":  today - timedelta(days=365),
        }
        cutoff = range_start[selected_range]

        with st.spinner(f"Loading {ticker} price history..."):
            try:
                t = yf.Ticker(pos.ticker)
                if use_hourly:
                    hist = t.history(
                        start=cutoff.strftime("%Y-%m-%d"),
                        interval="1h",
                    )
                else:
                    hist = t.history(
                        start=cutoff.strftime("%Y-%m-%d"),
                        interval="1d",
                    )
            except Exception:
                hist = None

        if hist is not None and not hist.empty:
            if use_hourly:
                hover_fmt = "%{x|%b %d, %I:%M %p}<br>Price: <b>$%{y:.2f}</b><extra></extra>"
                xaxis_cfg = dict(
                    rangebreaks=[
                        dict(bounds=["sat", "mon"]),          # hide weekends
                        dict(bounds=[20, 4], pattern="hour"), # hide overnight hours
                    ],
                )
            else:
                hover_fmt = "%{x|%b %d, %Y}<br>Price: <b>$%{y:.2f}</b><extra></extra>"
                xaxis_cfg = dict(
                    rangebreaks=[
                        dict(bounds=["sat", "mon"]),  # hide weekends
                    ],
                )

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist.index,
                y=hist["Close"],
                mode="lines",
                name=ticker,
                line=dict(color="#00c57a", width=2),
                hovertemplate=hover_fmt,
            ))
            fig.add_hline(
                y=pos.cost_basis,
                line_dash="dash",
                line_color="#ffa500",
                annotation_text=f"You paid \${pos.cost_basis:,.2f}",
                annotation_position="bottom right",
            )
            fig.update_layout(
                title=dict(text=f"{ticker} stock price", font=dict(size=13)),
                xaxis_title=None,
                yaxis_title="Price ($)",
                height=280,
                margin=dict(l=0, r=0, t=36, b=0),
                hovermode="x unified",
                yaxis=dict(tickprefix="$"),
                xaxis=xaxis_cfg,
            )
            st.plotly_chart(fig, use_container_width=True)

    # --- Events ---
    if events:
        with st.expander(f"📅 Upcoming events ({len(events)})", expanded=True):
            for event in events:
                render_event_banner(event)

    # --- Greeks (options only) ---
    if isinstance(pos, OptionPosition) and entry.get("greeks"):
        g = entry["greeks"]
        iv_note = "" if entry.get("iv_source") == "live" else " *(IV estimated at 35% — live data unavailable)*"
        st.markdown(f"### Position Greeks{iv_note}")
        explanations = greeks_explanations(g, pos.option_type, pos.position, ticker)

        greek_rows = [
            ("Delta",  f"{g.delta:+.4f}",  explanations["Delta"]),
            ("Gamma",  f"{g.gamma:+.4f}",  explanations["Gamma"]),
            ("Theta",  f"${g.theta:+,.2f}/day", explanations["Theta"]),
            ("Vega",   f"${g.vega:+,.2f} per 1% IV", explanations["Vega"]),
            ("Rho",    f"${g.rho:+,.2f} per 1% rate", explanations["Rho"]),
        ]
        table_rows = "".join(
            f"<tr>"
            f"<td style='font-weight:700; padding:5px 14px 5px 0; white-space:nowrap'>{name}</td>"
            f"<td style='font-family:monospace; padding:5px 14px 5px 0; white-space:nowrap'>{value}</td>"
            f"<td style='color:#888; padding:5px 0; font-size:0.88em'>{explanation}</td>"
            f"</tr>"
            for name, value, explanation in greek_rows
        )
        st.markdown(
            f"<table style='border-collapse:collapse; width:100%; margin-bottom:8px'>{table_rows}</table>",
            unsafe_allow_html=True,
        )
        st.divider()

    # --- Scenarios ---
    st.markdown("### Your options")
    if not OPENROUTER_KEY:
        st.caption("💡 Add OPENROUTER_API_KEY to your .env file to get AI explanations.")

    for i, scenario in enumerate(scenarios):
        render_scenario_card(scenario, i)
