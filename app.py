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
    fetch_strikes_for_expiry,
    fetch_option_mark,
    fetch_events,
    fetch_options_chain_for_rolls,
    fetch_analyst_data,
    fetch_stock_snapshot,
    fetch_finviz_data,
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
    "fed_meeting": "🏦",
}

# Timeline — monochrome theme, distinct symbols per event type
EVENT_COLOR = {
    "earnings":    "#ffffff",
    "ex_dividend": "#aaaaaa",
    "expiry":      "#ffffff",
    "fed_meeting": "#666666",
}
EVENT_SYMBOL = {
    "earnings":    "square",
    "ex_dividend": "triangle-up",
    "expiry":      "circle",
    "fed_meeting": "diamond",
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
if "option_ticker_price" not in st.session_state:
    st.session_state.option_ticker_price = 200.0
if "option_strikes" not in st.session_state:
    st.session_state.option_strikes = []
if "option_selected_expiry" not in st.session_state:
    st.session_state.option_selected_expiry = None


# ---------------------------------------------------------------------------
# Sidebar — API key + model
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("✈️ Finpilot")
    st.caption("Know your options.")
    st.divider()

    st.caption(
        "⚠️ **Disclaimer:** Finpilot is an informational tool only. Nothing here constitutes "
        "financial advice, a recommendation to buy or sell, or a solicitation of any kind. "
        "All analysis is generated automatically and may not reflect current market conditions. "
        "Always do your own research and consult a qualified financial advisor."
    )



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
    elif event.event_type == "fed_meeting":
        detail = "Fed rate decisions can move the whole market. High uncertainty before the meeting often raises option prices."
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


def render_stock_snapshot(snapshot: dict, current_price: float):
    if not snapshot:
        return
    low = snapshot.get("week52_low")
    high = snapshot.get("week52_high")
    beta = snapshot.get("beta")
    vol = snapshot.get("volume")
    avg_vol = snapshot.get("avg_volume")
    fpe = snapshot.get("forward_pe")
    tpe = snapshot.get("trailing_pe")
    eg = snapshot.get("earnings_growth")
    rg = snapshot.get("revenue_growth")
    sr = snapshot.get("short_ratio")

    cols = st.columns(4)

    # 52-week range with mini progress bar
    with cols[0]:
        if low and high:
            pct = (current_price - low) / (high - low) * 100 if high != low else 50
            pct = max(0, min(100, pct))
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-bottom:2px'>52-week range</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div style='font-size:0.82em'>${low:,.0f} — ${high:,.0f}</div>"
                f"<div style='background:#333; border-radius:4px; height:6px; margin:4px 0'>"
                f"<div style='background:#00c57a; width:{pct:.0f}%; height:6px; border-radius:4px'></div></div>"
                f"<div style='font-size:0.75em; color:#888'>{pct:.0f}% of range</div>",
                unsafe_allow_html=True,
            )

    with cols[1]:
        if beta is not None:
            color = "#ffa500" if beta > 1.3 else "#00c57a" if beta < 0.8 else "#888"
            label = "high volatility" if beta > 1.3 else "low volatility" if beta < 0.8 else "avg volatility"
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-bottom:2px'>Beta</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:1.1em; font-weight:600'>{beta:.2f}</div>"
                        f"<div style='font-size:0.75em; color:{color}'>{label}</div>", unsafe_allow_html=True)
        if sr is not None:
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-top:6px'>Short ratio</div>"
                        f"<div style='font-size:0.9em'>{sr:.1f} days to cover</div>", unsafe_allow_html=True)

    with cols[2]:
        if vol and avg_vol:
            ratio = vol / avg_vol
            vol_color = "#ffa500" if ratio > 1.5 else "#888"
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-bottom:2px'>Volume</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:0.9em; font-weight:600; color:{vol_color}'>{ratio:.1f}x avg</div>"
                        f"<div style='font-size:0.75em; color:#888'>{vol/1e6:.1f}M vs {avg_vol/1e6:.1f}M avg</div>",
                        unsafe_allow_html=True)
        if eg is not None or rg is not None:
            parts = []
            if eg is not None: parts.append(f"EPS {eg*100:+.0f}%")
            if rg is not None: parts.append(f"Rev {rg*100:+.0f}%")
            g_color = "#00c57a" if (eg or 0) > 0 else "#ff4b4b"
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-top:6px'>YoY growth</div>"
                        f"<div style='font-size:0.9em; color:{g_color}'>{' · '.join(parts)}</div>",
                        unsafe_allow_html=True)

    with cols[3]:
        if fpe is not None:
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-bottom:2px'>Forward P/E</div>"
                        f"<div style='font-size:1.1em; font-weight:600'>{fpe:.1f}x</div>", unsafe_allow_html=True)
        if tpe is not None:
            st.markdown(f"<div style='font-size:0.75em; color:#888; margin-top:6px'>Trailing P/E</div>"
                        f"<div style='font-size:0.9em'>{tpe:.1f}x</div>", unsafe_allow_html=True)


def render_finviz(finviz: dict):
    if not finviz:
        return
    tech = finviz.get("technicals") or {}
    perf = finviz.get("performance") or {}
    news = finviz.get("news") or []

    # --- Technicals + Performance (collapsed by default) ---
    with st.expander("📊 Technicals & Performance", expanded=False):
        rsi = tech.get("rsi14")
        sma20 = tech.get("sma20_pct")
        sma50 = tech.get("sma50_pct")
        sma200 = tech.get("sma200_pct")
        vol_w = tech.get("volatility_w")
        vol_m = tech.get("volatility_m")

        if any(v is not None for v in [rsi, sma20, sma50, sma200]):
            st.markdown("**Technicals**")
            tcols = st.columns(5)
            with tcols[0]:
                if rsi is not None:
                    rsi_color = "#ff4b4b" if rsi > 70 else "#00c57a" if rsi < 30 else "#888"
                    rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
                    st.markdown(f"<div style='font-size:0.75em;color:#888'>RSI (14)</div>"
                                f"<div style='font-size:1.1em;font-weight:600;color:{rsi_color}'>{rsi:.1f}</div>"
                                f"<div style='font-size:0.75em;color:{rsi_color}'>{rsi_label}</div>",
                                unsafe_allow_html=True)
            for col, val, label in zip(tcols[1:4], [sma20, sma50, sma200], ["vs SMA20", "vs SMA50", "vs SMA200"]):
                with col:
                    if val is not None:
                        c = "#00c57a" if val >= 0 else "#ff4b4b"
                        st.markdown(f"<div style='font-size:0.75em;color:#888'>{label}</div>"
                                    f"<div style='font-size:1.0em;font-weight:600;color:{c}'>{val:+.1f}%</div>",
                                    unsafe_allow_html=True)
            with tcols[4]:
                if vol_w is not None and vol_m is not None:
                    st.markdown(f"<div style='font-size:0.75em;color:#888'>Volatility</div>"
                                f"<div style='font-size:0.85em'>1W: <b>{vol_w:.1f}%</b></div>"
                                f"<div style='font-size:0.85em'>1M: <b>{vol_m:.1f}%</b></div>",
                                unsafe_allow_html=True)

        perf_items = [
            ("1W",  perf.get("perf_week")),
            ("1M",  perf.get("perf_month")),
            ("3M",  perf.get("perf_quarter")),
            ("YTD", perf.get("perf_ytd")),
            ("1Y",  perf.get("perf_year")),
        ]
        if any(v is not None for _, v in perf_items):
            st.markdown("**Performance**")
            pcols = st.columns(5)
            for col, (label, val) in zip(pcols, perf_items):
                with col:
                    if val is not None:
                        c = "#00c57a" if val >= 0 else "#ff4b4b"
                        st.markdown(f"<div style='font-size:0.75em;color:#888'>{label}</div>"
                                    f"<div style='font-size:1.0em;font-weight:600;color:{c}'>{val:+.1f}%</div>",
                                    unsafe_allow_html=True)

    # News is rendered in the Timeline & News pane


def render_timeline(events: list, end_date: date, end_label: str):
    """Horizontal timeline from today to end_date with event markers."""
    today = date.today()
    total_days = max((end_date - today).days, 1)

    fig = go.Figure()
    fig.add_shape(
        type="line",
        x0=today, x1=end_date, y0=0, y1=0,
        line=dict(color="#555555", width=2),
    )
    fig.add_trace(go.Scatter(
        x=[today], y=[0],
        mode="markers+text",
        marker=dict(size=12, color="#ffffff", symbol="circle"),
        text=["Today"], textposition="top center",
        textfont=dict(size=11, color="#aaaaaa"),
        hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[end_date], y=[0],
        mode="markers+text",
        marker=dict(size=12, color="#ffffff", symbol="circle"),
        text=[f"{end_label}<br>{end_date.strftime('%b %d')}"], textposition="top center",
        textfont=dict(size=11, color="#aaaaaa"),
        hoverinfo="skip", showlegend=False,
    ))

    non_expiry_events = [e for e in events if e.event_type != "expiry"]
    for i, event in enumerate(non_expiry_events):
        color = EVENT_COLOR.get(event.event_type, "#888888")
        symbol = EVENT_SYMBOL.get(event.event_type, "circle")
        icon = EVENT_ICON.get(event.event_type, "•")
        y_pos = 0.6 if i % 2 == 0 else -0.6
        text_pos = "top center" if y_pos > 0 else "bottom center"

        fig.add_shape(
            type="line",
            x0=event.date, x1=event.date, y0=0, y1=y_pos * 0.85,
            line=dict(color="#444444", width=1, dash="dot"),
        )
        fig.add_trace(go.Scatter(
            x=[event.date], y=[y_pos],
            mode="markers+text",
            marker=dict(size=10, color=color, symbol=symbol,
                        line=dict(color="#666666", width=1)),
            text=[f"{icon} {event.date.strftime('%b %d')}"],
            textposition=text_pos,
            textfont=dict(size=10, color="#aaaaaa"),
            hovertemplate=f"<b>{event.label}</b><extra></extra>",
            showlegend=False,
        ))

    days_left = (end_date - today).days
    fig.update_layout(
        height=160,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(
            range=[today - timedelta(days=total_days * 0.03),
                   end_date + timedelta(days=total_days * 0.03)],
            showgrid=False, zeroline=False, showticklabels=False,
            rangebreaks=[dict(bounds=["sat", "mon"])],
        ),
        yaxis=dict(range=[-1.3, 1.3], showgrid=False,
                   zeroline=False, showticklabels=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="closest",
        annotations=[dict(
            x=end_date, y=-1.2,
            text=f"{days_left} days",
            showarrow=False, font=dict(size=11, color="#888"),
            xanchor="center",
        )],
    )
    st.plotly_chart(fig, use_container_width=True)


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
            st.caption(scenario.narrative.replace("$", r"\$"))


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
        analyst = fetch_analyst_data(position.ticker)
        snapshot = fetch_stock_snapshot(position.ticker)
        finviz = fetch_finviz_data(position.ticker)
        result.update({
            "current_price": current_price,
            "current_mark": None,
            "events": events,
            "scenarios": scenarios,
            "analyst": analyst,
            "snapshot": snapshot,
            "finviz": finviz,
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

        analyst = fetch_analyst_data(position.ticker)
        snapshot = fetch_stock_snapshot(position.ticker)
        finviz = fetch_finviz_data(position.ticker)
        result.update({
            "current_price": current_price,
            "current_mark": current_mark,
            "events": events,
            "roll_candidates": roll_candidates,
            "scenarios": scenarios,
            "greeks": greeks,
            "snapshot": snapshot,
            "finviz": finviz,
            "iv_source": "live" if iv else "estimated",
            "analyst": analyst,
        })

    result["overall_analysis"] = ""
    if OPENROUTER_KEY:
        result["scenarios"], result["overall_analysis"] = generate_all_narratives(
            result["scenarios"],
            position,
            result["current_mark"] if isinstance(position, OptionPosition) else result["current_price"],
            result["events"],
            OPENROUTER_KEY,
            st.session_state.selected_model,
            result.get("analyst"),
            result.get("snapshot"),
            result.get("finviz"),
        )

    return result


# ---------------------------------------------------------------------------
# Main — Header
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Add Position form
# ---------------------------------------------------------------------------
tab_stock, tab_option = st.tabs(["📈 STOCKS", "🎯 OPTIONS"])

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
                    price = fetch_current_price(o_ticker_load) or 200.0
                    st.session_state.option_expiries = expiries
                    st.session_state.option_expiry_ticker = o_ticker_load
                    st.session_state.option_ticker_price = float(price)

    # Step 2 — expiry + type selectors (outside form so strikes can update dynamically)
    if st.session_state.option_expiries and st.session_state.option_expiry_ticker == o_ticker_load:
        pre_col1, pre_col2 = st.columns(2)
        with pre_col1:
            o_type = st.selectbox("Option Type", ["Call", "Put"], key="o_type").lower()
        with pre_col2:
            expiry_options = st.session_state.option_expiries
            expiry_labels = [e.strftime("%b %d, %Y") for e in expiry_options]
            o_expiry_idx = st.selectbox("Expiry date", range(len(expiry_labels)), format_func=lambda i: expiry_labels[i], key="o_expiry_idx")

        o_expiry = expiry_options[o_expiry_idx]

        # Fetch strikes whenever expiry or type changes
        cache_key = (o_ticker_load, o_expiry, o_type)
        if st.session_state.option_selected_expiry != cache_key:
            with st.spinner("Loading strikes..."):
                strikes = fetch_strikes_for_expiry(o_ticker_load, o_expiry, o_type)
                st.session_state.option_strikes = strikes
                st.session_state.option_selected_expiry = cache_key

        # Step 3 — main form
        with st.form("option_form"):
            col1, col2 = st.columns(2)
            with col1:
                strikes_available = st.session_state.option_strikes
                current_price = st.session_state.option_ticker_price
                # Default to strike closest to current price
                if strikes_available:
                    closest_idx = min(range(len(strikes_available)), key=lambda i: abs(strikes_available[i] - current_price))
                    o_strike = st.selectbox(
                        "Strike price ($)",
                        strikes_available,
                        index=closest_idx,
                        format_func=lambda s: f"${s:,.2f}",
                    )
                else:
                    o_strike = st.number_input("Strike price ($)", min_value=0.01, value=current_price, step=0.50)
                o_position = "long"
            with col2:
                o_premium = st.number_input(
                    "Premium paid per share ($)",
                    min_value=0.01, value=5.00, step=0.05,
                    help="The price per share you paid. Multiply by 100 for total contract cost.",
                )
                o_contracts = st.number_input("Number of contracts", min_value=1, value=1, step=1)

            submitted_option = st.form_submit_button("Fetch & Analyze", use_container_width=True)

        if submitted_option:
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

    # --- Greeks (options only) ---
    # --- Pane 1: Stock snapshot + Technicals + Analyst ratings ---
    snapshot = entry.get("snapshot", {})
    finviz = entry.get("finviz", {})
    analyst = entry.get("analyst", {})
    pt = analyst.get("price_targets") if analyst else None
    summary = analyst.get("summary") if analyst else None
    changes = analyst.get("recent_changes") if analyst else None

    if snapshot or finviz or pt or summary or changes:
        with st.expander("📊 Market context", expanded=False):
            if snapshot:
                render_stock_snapshot(snapshot, current_price)
            if finviz:
                render_finviz(finviz)
            if pt or summary or changes:
                st.markdown("**Analyst ratings**")
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    if summary:
                        total = summary["strong_buy"] + summary["buy"] + summary["hold"] + summary["sell"] + summary["strong_sell"]
                        bullish = summary["strong_buy"] + summary["buy"]
                        rows = "".join([
                            f"<tr><td style='color:#00c57a; padding:2px 10px 2px 0'>Strong Buy</td><td style='font-weight:600'>{summary['strong_buy']}</td></tr>",
                            f"<tr><td style='color:#7ec87e; padding:2px 10px 2px 0'>Buy</td><td style='font-weight:600'>{summary['buy']}</td></tr>",
                            f"<tr><td style='color:#888; padding:2px 10px 2px 0'>Hold</td><td style='font-weight:600'>{summary['hold']}</td></tr>",
                            f"<tr><td style='color:#ffa07a; padding:2px 10px 2px 0'>Sell</td><td style='font-weight:600'>{summary['sell']}</td></tr>",
                            f"<tr><td style='color:#ff4b4b; padding:2px 10px 2px 0'>Strong Sell</td><td style='font-weight:600'>{summary['strong_sell']}</td></tr>",
                        ])
                        st.markdown(
                            f"<div style='font-size:0.85em; margin-bottom:4px; color:#aaa'>{bullish}/{total} analysts bullish</div>"
                            f"<table style='border-collapse:collapse; font-size:0.9em'>{rows}</table>",
                            unsafe_allow_html=True,
                        )
                with col_b:
                    if pt:
                        upside = ((pt["mean"] - current_price) / current_price * 100)
                        upside_color = "#00c57a" if upside >= 0 else "#ff4b4b"
                        rows = "".join([
                            f"<tr><td style='color:#888; padding:2px 10px 2px 0'>Mean target</td><td style='font-weight:600'>${pt['mean']:,.2f} <span style='color:{upside_color}; font-size:0.85em'>({upside:+.1f}%)</span></td></tr>",
                            f"<tr><td style='color:#888; padding:2px 10px 2px 0'>Median target</td><td style='font-weight:600'>${pt['median']:,.2f}</td></tr>",
                            f"<tr><td style='color:#888; padding:2px 10px 2px 0'>High target</td><td style='font-weight:600'>${pt['high']:,.2f}</td></tr>",
                            f"<tr><td style='color:#888; padding:2px 10px 2px 0'>Low target</td><td style='font-weight:600'>${pt['low']:,.2f}</td></tr>",
                        ])
                        st.markdown(
                            f"<table style='border-collapse:collapse; font-size:0.9em'>{rows}</table>",
                            unsafe_allow_html=True,
                        )
                    if changes:
                        st.markdown("<div style='font-size:0.8em; color:#aaa; margin-top:10px'>Recent actions</div>", unsafe_allow_html=True)
                        for c in changes[:4]:
                            action_color = "#00c57a" if c["action"] in ("upgrade", "init") else "#ffa500" if c["action"] == "main" else "#ff4b4b"
                            st.markdown(
                                f"<div style='font-size:0.82em; margin:2px 0'>"
                                f"<span style='color:{action_color}'>●</span> "
                                f"<strong>{c['firm']}</strong> — {c['to_grade']}"
                                f"{'  ← ' + c['from_grade'] if c['from_grade'] else ''}"
                                f" <span style='color:#666'>({c['date'].strftime('%b %d')})</span></div>",
                                unsafe_allow_html=True,
                            )

    # --- Pane 2: Timeline + News ---
    with st.expander("🗓️ Timeline & News", expanded=False):
        if isinstance(pos, OptionPosition):
            render_timeline(events, pos.expiry, "Expiry")
        else:
            stock_horizon = date.today() + timedelta(days=365)
            render_timeline(events, stock_horizon, "1 year out")
        finviz_news = entry.get("finviz", {}).get("news", [])
        if finviz_news:
            st.markdown("**Recent news**")
            for item in finviz_news:
                date_str = item["date"].strftime("%b %d") if hasattr(item.get("date"), "strftime") else ""
                source = item.get("source", "")
                title = item.get("title", "")
                link = item.get("link", "")
                title_html = f"<a href='{link}' target='_blank' style='color:#ccc;text-decoration:none'>{title}</a>" if link else title
                st.markdown(
                    f"<div style='font-size:0.83em;margin:3px 0;padding:4px 0;border-bottom:1px solid #222'>"
                    f"<span style='color:#555'>{date_str} · {source}</span><br>{title_html}</div>",
                    unsafe_allow_html=True,
                )

    # --- Position Greeks (options only, collapsed) ---
    if isinstance(pos, OptionPosition) and entry.get("greeks"):
        g = entry["greeks"]
        iv_note = "" if entry.get("iv_source") == "live" else " *(IV estimated at 35%)*"
        with st.expander(f"🔢 Position Greeks{iv_note}", expanded=False):
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

    # --- Scenarios ---
    st.markdown("### Your options")
    if not OPENROUTER_KEY:
        st.caption("💡 Add OPENROUTER_API_KEY to your .env file to get AI explanations.")

    overall = entry.get("overall_analysis", "")
    if overall:
        st.info(overall.replace("$", r"\$"), icon="💬")

    for i, scenario in enumerate(scenarios):
        render_scenario_card(scenario, i)
