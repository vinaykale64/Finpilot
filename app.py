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
from finpilot.greeks import calculate_greeks, greeks_explanations, probability_of_profit, bs_option_value, implied_vol
from finpilot.watchlist import save_position, load_watchlist, delete_position, row_to_position
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


# ---------------------------------------------------------------------------
# Global styles
# ---------------------------------------------------------------------------
def _inject_styles():
    st.html("""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg:       #0a0a0b;
  --surface:  #111113;
  --border:   #1e1e22;
  --accent:   #f0b429;
  --up:       #00d97e;
  --down:     #ff4560;
  --muted:    #555566;
  --text:     #e8e8f0;
}

/* ---- Base ---- */
html, body, [data-testid="stAppViewContainer"] {
  background-color: var(--bg) !important;
  color: var(--text) !important;
}
[data-testid="stSidebar"] {
  background-color: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stHeader"] {
  background-color: var(--bg) !important;
}

/* ---- Tab bar ---- */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 1px solid var(--border) !important;
  gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
  padding: 8px 20px !important;
  border-radius: 0 !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  background: transparent !important;
  transition: color 0.15s, border-color 0.15s !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
  color: var(--text) !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--accent) !important;
  border-bottom: 2px solid var(--accent) !important;
  background: transparent !important;
}

/* ---- Buttons ---- */
[data-testid="stButton"] > button {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  color: var(--accent) !important;
  background: transparent !important;
  border: 1px solid var(--accent) !important;
  border-radius: 2px !important;
  padding: 6px 14px !important;
  transition: background 0.15s, color 0.15s !important;
}
[data-testid="stButton"] > button:hover {
  background: var(--accent) !important;
  color: #000 !important;
}

/* ---- Form inputs ---- */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] > div > div,
[data-testid="stDateInput"] input {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.85rem !important;
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 2px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
}

/* ---- Labels ---- */
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stDateInput"] label,
[data-testid="stRadio"] label {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.7rem !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
}

/* ---- Metrics ---- */
[data-testid="stMetric"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.65rem !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
}
[data-testid="stMetricValue"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 1.05rem !important;
  font-weight: 600 !important;
  color: var(--text) !important;
}
[data-testid="stMetricDelta"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.78rem !important;
}

/* ---- Containers / cards ---- */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
}

/* ---- Info / alert boxes ---- */
[data-testid="stAlert"] {
  background: #0f0f0a !important;
  border: 1px solid var(--accent) !important;
  border-left: 3px solid var(--accent) !important;
  border-radius: 2px !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.83rem !important;
  color: var(--text) !important;
}

/* ---- Expanders ---- */
[data-testid="stExpander"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
}
[data-testid="stExpander"] summary {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.72rem !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
}
[data-testid="stExpander"] summary:hover {
  color: var(--text) !important;
}

/* ---- Dividers ---- */
hr {
  border-color: var(--border) !important;
}

/* ---- Captions ---- */
[data-testid="stCaptionContainer"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 0.78rem !important;
  color: var(--muted) !important;
}

/* ---- Headings ---- */
h1, h2, h3 {
  font-family: 'Syne', sans-serif !important;
  letter-spacing: -0.01em !important;
  color: var(--text) !important;
}

/* ---- Section header utility class ---- */
.fp-section-header {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  padding-bottom: 7px;
  margin: 24px 0 14px;
}

/* ---- App header bar ---- */
.fp-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 18px 0 14px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}
.fp-header-logo {
  font-family: 'Syne', sans-serif;
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: var(--accent);
  text-transform: uppercase;
}
.fp-header-tagline {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  color: var(--muted);
  letter-spacing: 0.1em;
  margin-left: 16px;
}
.fp-header-date {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.68rem;
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

/* ---- Disclaimer banner ---- */
.fp-disclaimer {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.68rem;
  color: var(--muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid #333;
  border-radius: 2px;
  padding: 8px 14px;
  margin-bottom: 18px;
  line-height: 1.6;
}
</style>
""")

_inject_styles()

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
if "watchlist_just_analyzed" not in st.session_state:
    st.session_state.watchlist_just_analyzed = None  # ticker string or None


# ---------------------------------------------------------------------------
# Sidebar — lean version
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:1.1rem;font-weight:800;"
        "letter-spacing:0.1em;color:#f0b429;text-transform:uppercase;padding:8px 0 4px'>✈ Finpilot</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;"
        "color:#555566;letter-spacing:0.08em;padding-bottom:12px'>Know your options.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

# ---------------------------------------------------------------------------
# App header bar (main content area)
# ---------------------------------------------------------------------------
from datetime import datetime as _dt
st.markdown(
    f"""<div class="fp-header">
      <div>
        <span class="fp-header-logo">✈ Finpilot</span>
        <span class="fp-header-tagline">/ know your options</span>
      </div>
      <div class="fp-header-date">{_dt.today().strftime("%b %d, %Y")} &nbsp;·&nbsp; Live data</div>
    </div>
    <div class="fp-disclaimer">
      ⚠ Informational tool only. Nothing here constitutes financial advice, a recommendation
      to buy or sell, or a solicitation of any kind. Always do your own research and consult
      a qualified financial advisor.
    </div>""",
    unsafe_allow_html=True,
)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section_header(title: str):
    st.markdown(f"<div class='fp-section-header'>{title}</div>", unsafe_allow_html=True)


def render_event_pills(events: list):
    """Render upcoming events as a compact row of inline pills."""
    DETAIL = {
        "earnings":    "Prices can move sharply. IV often rises before, then drops after.",
        "ex_dividend": "Short call holders face early assignment risk around this date.",
        "fed_meeting": "Rate decisions move the whole market; raises option premiums.",
        "expiry":      "Option expires worthless after this date — act before then.",
    }
    URGENCY_LABEL = {"critical": "URGENT", "soon": "SOON", "on_radar": "UPCOMING"}

    pills = []
    for event in events:
        color = URGENCY_COLOR[event.urgency]
        icon = EVENT_ICON[event.event_type]
        label = URGENCY_LABEL[event.urgency]
        days = event.days_away
        days_str = f"{days}d" if days >= 0 else "today"
        pills.append(
            f"<span title='{DETAIL[event.event_type]}' style='"
            f"display:inline-flex;align-items:center;gap:5px;"
            f"font-family:IBM Plex Mono,monospace;font-size:0.67rem;font-weight:600;"
            f"letter-spacing:0.08em;text-transform:uppercase;"
            f"color:{color};background:{color}18;"
            f"border:1px solid {color}44;border-radius:2px;"
            f"padding:4px 9px;white-space:nowrap'>"
            f"{icon} {label} &nbsp;·&nbsp; {event.date.strftime('%b %d')} &nbsp;·&nbsp; {days_str}"
            f"</span>"
        )

    if pills:
        st.html(
            f"<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px'>"
            f"{''.join(pills)}</div>"
        )


def _stat_tile(label: str, value: str, sub: str = "", value_color: str = "var(--text)") -> str:
    """Return HTML for a single stat tile used in snapshot/technicals grids."""
    sub_html = (
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.7rem;"
        f"color:var(--muted);margin-top:3px'>{sub}</div>"
    ) if sub else ""
    return (
        f"<div style='padding:10px 14px;background:var(--surface);"
        f"border:1px solid var(--border);border-radius:2px'>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.62rem;"
        f"letter-spacing:0.12em;text-transform:uppercase;color:var(--muted);margin-bottom:5px'>{label}</div>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.92rem;"
        f"font-weight:600;color:{value_color}'>{value}</div>"
        f"{sub_html}</div>"
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

    tiles = []

    if low and high:
        pct = (current_price - low) / (high - low) * 100 if high != low else 50
        pct = max(0, min(100, pct))
        bar = (
            f"<div style='background:var(--border);border-radius:1px;height:4px;margin:6px 0 3px'>"
            f"<div style='background:var(--up);width:{pct:.0f}%;height:4px;border-radius:1px'></div></div>"
            f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;color:var(--muted)'>"
            f"&#36;{low:,.0f} &nbsp;—&nbsp; &#36;{high:,.0f} &nbsp;·&nbsp; {pct:.0f}% of range</div>"
        )
        tiles.append(
            f"<div style='padding:10px 14px;background:var(--surface);"
            f"border:1px solid var(--border);border-radius:2px'>"
            f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.62rem;"
            f"letter-spacing:0.12em;text-transform:uppercase;color:var(--muted);margin-bottom:5px'>52-Week Range</div>"
            f"{bar}</div>"
        )

    if beta is not None:
        b_color = "var(--accent)" if beta > 1.3 else "var(--up)" if beta < 0.8 else "var(--muted)"
        b_label = "High vol" if beta > 1.3 else "Low vol" if beta < 0.8 else "Avg vol"
        tiles.append(_stat_tile("Beta", f"{beta:.2f}", b_label, b_color))

    if vol and avg_vol:
        ratio = vol / avg_vol
        v_color = "var(--accent)" if ratio > 1.5 else "var(--muted)"
        tiles.append(_stat_tile("Volume", f"{ratio:.1f}x avg", f"{vol/1e6:.1f}M vs {avg_vol/1e6:.1f}M", v_color))

    if eg is not None or rg is not None:
        parts = []
        if eg is not None: parts.append(f"EPS {eg*100:+.0f}%")
        if rg is not None: parts.append(f"Rev {rg*100:+.0f}%")
        g_color = "var(--up)" if (eg or 0) > 0 else "var(--down)"
        tiles.append(_stat_tile("YoY Growth", " · ".join(parts), value_color=g_color))

    if fpe is not None:
        tiles.append(_stat_tile("Forward P/E", f"{fpe:.1f}x", f"Trailing {tpe:.1f}x" if tpe else ""))

    if sr is not None:
        tiles.append(_stat_tile("Short Ratio", f"{sr:.1f}d", "days to cover"))

    if tiles:
        cols_html = "".join(
            f"<div style='flex:1;min-width:140px'>{t}</div>" for t in tiles
        )
        st.html(
            f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px'>{cols_html}</div>"
        )


def render_finviz(finviz: dict):
    if not finviz:
        return
    tech = finviz.get("technicals") or {}
    perf = finviz.get("performance") or {}

    with st.expander("Technicals & Performance", expanded=False):
        rsi = tech.get("rsi14")
        sma20 = tech.get("sma20_pct")
        sma50 = tech.get("sma50_pct")
        sma200 = tech.get("sma200_pct")
        vol_w = tech.get("volatility_w")
        vol_m = tech.get("volatility_m")

        tech_tiles = []
        if rsi is not None:
            rsi_color = "var(--down)" if rsi > 70 else "var(--up)" if rsi < 30 else "var(--muted)"
            rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
            tech_tiles.append(_stat_tile("RSI (14)", f"{rsi:.1f}", rsi_label, rsi_color))
        for val, label in [(sma20, "vs SMA20"), (sma50, "vs SMA50"), (sma200, "vs SMA200")]:
            if val is not None:
                c = "var(--up)" if val >= 0 else "var(--down)"
                tech_tiles.append(_stat_tile(label, f"{val:+.1f}%", value_color=c))
        if vol_w is not None and vol_m is not None:
            tech_tiles.append(_stat_tile("Volatility", f"{vol_w:.1f}%", f"1M: {vol_m:.1f}%"))

        perf_items = [
            ("1W",  perf.get("perf_week")),
            ("1M",  perf.get("perf_month")),
            ("3M",  perf.get("perf_quarter")),
            ("YTD", perf.get("perf_ytd")),
            ("1Y",  perf.get("perf_year")),
        ]
        perf_tiles = []
        for label, val in perf_items:
            if val is not None:
                c = "var(--up)" if val >= 0 else "var(--down)"
                perf_tiles.append(_stat_tile(label, f"{val:+.1f}%", value_color=c))

        all_tiles = tech_tiles + perf_tiles
        if all_tiles:
            cols_html = "".join(
                f"<div style='flex:1;min-width:100px'>{t}</div>" for t in all_tiles
            )
            st.html(
                f"<div style='display:flex;flex-wrap:wrap;gap:8px'>{cols_html}</div>"
            )

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


def render_position_summary(items: list):
    """
    Render a horizontal terminal-style stat bar.
    items: list of (label, value, is_pnl) where is_pnl colors the cell green/red.
    """
    cells = []
    for label, value, is_pnl in items:
        if is_pnl:
            is_pos = not str(value).startswith("-") and "(-" not in str(value)
            val_color = "var(--up)" if is_pos else "var(--down)"
            bg = "rgba(0,217,126,0.07)" if is_pos else "rgba(255,69,96,0.07)"
            border_top = f"2px solid {val_color}"
        else:
            val_color = "var(--text)"
            bg = "var(--surface)"
            border_top = "2px solid var(--border)"

        cells.append(
            f"<div style='flex:1;min-width:0;padding:10px 14px;background:{bg};"
            f"border-top:{border_top};border-right:1px solid var(--border)'>"
            f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.62rem;"
            f"letter-spacing:0.14em;text-transform:uppercase;color:var(--muted);"
            f"margin-bottom:5px'>{label}</div>"
            f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.92rem;"
            f"font-weight:600;color:{val_color};white-space:nowrap;overflow:hidden;"
            f"text-overflow:ellipsis'>{value}</div>"
            f"</div>"
        )

    st.html(
        f"<div style='display:flex;border:1px solid var(--border);border-right:none;"
        f"border-radius:2px;margin-bottom:18px;overflow:hidden'>"
        f"{''.join(cells)}</div>"
    )


def render_scenario_card(scenario: Scenario, index: int):
    accent = index == 0
    left_border = "3px solid var(--accent)" if accent else "3px solid var(--border)"
    num_color = "var(--accent)" if accent else "var(--muted)"

    kn_rows = "".join(
        f"<tr>"
        f"<td style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;letter-spacing:0.08em;"
        f"text-transform:uppercase;color:var(--muted);padding:3px 20px 3px 0;white-space:nowrap'>{label}</td>"
        f"<td style='font-family:IBM Plex Mono,monospace;font-size:0.88rem;font-weight:600;"
        f"color:var(--text);padding:3px 0;white-space:nowrap'>{value}</td>"
        f"</tr>"
        for label, value in scenario.key_numbers.items()
    )

    tradeoff = scenario.tradeoff.replace("$", "&#36;")
    narrative = scenario.narrative.replace("$", "&#36;") if scenario.narrative else ""
    narrative_block = (
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.78rem;line-height:1.65;"
        f"color:var(--muted);margin-top:6px'>{narrative}</div>"
    ) if narrative else ""

    st.html(
        f"<div style='border:1px solid var(--border);border-left:{left_border};"
        f"border-radius:2px;padding:16px 18px;margin-bottom:10px;background:var(--surface)'>"

        f"<div style='display:flex;align-items:baseline;gap:10px;margin-bottom:12px'>"
        f"<span style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;font-weight:600;"
        f"color:{num_color};letter-spacing:0.12em'>{index+1:02d}</span>"
        f"<span style='font-family:Syne,sans-serif;font-size:1.0rem;font-weight:700;"
        f"letter-spacing:0.02em;color:var(--text);text-transform:uppercase'>{scenario.action_label}</span>"
        f"</div>"

        f"<table style='border-collapse:collapse;margin-bottom:12px'>{kn_rows}</table>"

        f"<div style='border-top:1px solid var(--border);padding-top:10px'>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.78rem;line-height:1.65;"
        f"color:#8888aa'>{tradeoff}</div>"
        f"{narrative_block}"
        f"</div>"

        f"</div>"
    )


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
            result["current_price"],
            result["events"],
            OPENROUTER_KEY,
            st.session_state.selected_model,
            result.get("analyst"),
            result.get("snapshot"),
            result.get("finviz"),
            current_mark=result.get("current_mark"),
            greeks=result.get("greeks"),
        )

    return result


# ---------------------------------------------------------------------------
# Main — Header
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Add Position form
# ---------------------------------------------------------------------------
tab_stock, tab_option, tab_watchlist = st.tabs(["📈 STOCKS", "🎯 OPTIONS", "📋 SAVED ANALYSIS"])

# ---------------------------------------------------------------------------
# Analysis result — rendered inside the appropriate tab
# ---------------------------------------------------------------------------
with tab_stock:
    st.divider()
    if st.session_state.result is None or not isinstance(st.session_state.result["position"], StockPosition):
        st.info("No stock position analyzed yet. Enter details above to get started.")

with tab_option:
    st.divider()
    if st.session_state.result is None or not isinstance(st.session_state.result["position"], OptionPosition):
        st.info("No option position analyzed yet. Enter details above to get started.")

if st.session_state.result is not None:
    _res_pos = st.session_state.result["position"]
    _res_tab = tab_stock if isinstance(_res_pos, StockPosition) else tab_option
    with _res_tab:
        entry = st.session_state.result
        pos = entry["position"]
        current_price = entry["current_price"]
        events = entry["events"]
        scenarios = entry["scenarios"]
        ticker = pos.ticker.upper()

        # --- Save to watchlist ---
        col_save, _ = st.columns([1, 5])
        with col_save:
            if st.button("🔖 Save analysis", use_container_width=True):
                if isinstance(pos, StockPosition):
                    _save_pnl = pos.pnl(current_price)
                    _save_pnl_pct = pos.pnl_pct(current_price)
                else:
                    _save_pnl = pos.pnl(entry.get("current_mark", 0))
                    _save_pnl_pct = pos.pnl_pct(entry.get("current_mark", 0))
                if save_position(pos, pnl=_save_pnl, pnl_pct=_save_pnl_pct, overall_analysis=entry.get("overall_analysis", "")):
                    st.success("Saved!")
                else:
                    st.error("Could not save — check Google Sheets config.")

        # --- Position summary ---
        if isinstance(pos, StockPosition):
            pnl = pos.pnl(current_price)
            pnl_pct = pos.pnl_pct(current_price)
            sign = "+" if pnl >= 0 else ""
            render_position_summary([
                ("Ticker",        ticker,                                False),
                ("Type",          "Stock",                               False),
                ("You paid",      f"${pos.cost_basis:,.2f} / share",    False),
                ("Current price", f"${current_price:,.2f}",             False),
                ("P&L",           f"{sign}${abs(pnl):,.2f} ({sign}{pnl_pct:.1f}%)", True),
            ])

        else:
            current_mark = entry["current_mark"]
            pnl = pos.pnl(current_mark)
            pnl_pct = pos.pnl_pct(current_mark)
            sign = "+" if pnl >= 0 else ""
            _iv = (entry["greeks"].iv / 100.0) if entry.get("greeks") else 0.35
            _pop = probability_of_profit(pos.option_type, current_price, pos.strike, _iv, pos.expiry)
            render_position_summary([
                ("Ticker",        ticker,                                                    False),
                ("Type",          f"{pos.position.title()} {pos.option_type.title()}",      False),
                ("Strike",        f"${pos.strike:,.2f}",                                   False),
                ("Expires",       pos.expiry.strftime("%b %d, %Y"),                        False),
                ("Stock price",   f"${current_price:,.2f}",                                False),
                ("Option value",  f"${current_mark:,.2f} / share",                        False),
                ("P&L",           f"{sign}${abs(pnl):,.2f} ({sign}{pnl_pct:.1f}%)",       True),
                ("Prob. profit",  f"{_pop:.1f}%" if _pop is not None else "—",             False),
            ])

        # --- Option value vs stock price chart (options only) ---
        if isinstance(pos, OptionPosition) and entry.get("greeks"):
            # Calibrate IV from actual current_mark so the curve passes through the real market price
            _current_mark = entry.get("current_mark") or 0
            _iv_chart = implied_vol(pos.option_type, current_price, pos.strike, _current_mark, pos.expiry) \
                if _current_mark > 0 else entry["greeks"].iv / 100.0
            lo = min(current_price, pos.strike) * 0.75
            hi = max(current_price, pos.strike) * 1.25
            steps = 200
            step_size = (hi - lo) / steps
            s_range = [lo + i * step_size for i in range(steps + 1)]

            values = [bs_option_value(pos.option_type, s, pos.strike, _iv_chart, pos.expiry) for s in s_range]
            expiry_payoff = [
                max(0.0, s - pos.strike) if pos.option_type == "call" else max(0.0, pos.strike - s)
                for s in s_range
            ]

            # Find break-even: stock price where value today crosses cost basis
            be_stock = None
            for i in range(len(values) - 1):
                v0, v1 = values[i], values[i + 1]
                if v0 is None or v1 is None:
                    continue
                if (v0 - pos.premium) * (v1 - pos.premium) <= 0:
                    # Linear interpolation
                    t = (pos.premium - v0) / (v1 - v0) if v1 != v0 else 0
                    be_stock = s_range[i] + t * (s_range[i + 1] - s_range[i])
                    break

            fig_ov = go.Figure()
            fig_ov.add_trace(go.Scatter(
                x=s_range, y=expiry_payoff,
                mode="lines", name="Value at expiry",
                line=dict(color="#7b9fff", width=1.5, dash="dot"),
                hovertemplate="Stock $%{x:.2f}<br>At expiry: <b>$%{y:.2f}</b><extra></extra>",
            ))
            fig_ov.add_trace(go.Scatter(
                x=s_range, y=values,
                mode="lines", name="Value today (BS)",
                line=dict(color="#00c57a", width=2),
                hovertemplate="Stock $%{x:.2f}<br>Value today: <b>$%{y:.2f}</b><extra></extra>",
            ))
            fig_ov.add_hline(
                y=pos.premium,
                line_dash="dash", line_color="#ffa500",
                annotation_text=f"Cost basis ${pos.premium:,.2f}",
                annotation_position="top left",
            )
            fig_ov.add_vline(
                x=current_price,
                line_dash="dash", line_color="#888",
                annotation_text=f"Now ${current_price:,.2f}",
                annotation_position="top right",
            )
            if be_stock is not None:
                fig_ov.add_vline(
                    x=be_stock,
                    line_dash="solid", line_color="#ffa500",
                    annotation_text=f"B/E ${be_stock:,.2f}",
                    annotation_position="bottom right",
                )
            fig_ov.update_layout(
                title=dict(text=f"Option value vs {ticker} stock price  ·  δ = {entry['greeks'].delta:+.2f}", font=dict(size=13)),
                xaxis_title="Stock price ($)", yaxis_title="Option value ($)",
                height=280,
                margin=dict(l=0, r=0, t=36, b=0),
                hovermode="x unified",
                xaxis=dict(tickprefix="$"),
                yaxis=dict(tickprefix="$"),
                legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
            )
            st.plotly_chart(fig_ov, use_container_width=True)

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

        # --- Pane 1: Stock snapshot + Technicals + Analyst ratings ---
        snapshot = entry.get("snapshot", {})
        finviz = entry.get("finviz", {})
        analyst = entry.get("analyst", {})
        pt = analyst.get("price_targets") if analyst else None
        summary = analyst.get("summary") if analyst else None
        changes = analyst.get("recent_changes") if analyst else None

        if snapshot or finviz or pt or summary or changes:
            with st.expander("Market Context", expanded=False):
                if snapshot:
                    render_stock_snapshot(snapshot, current_price)
                if finviz:
                    render_finviz(finviz)
                if pt or summary or changes:
                    section_header("Analyst Ratings")
                    col_a, col_b = st.columns([1, 1])
                    with col_a:
                        if summary:
                            total = summary["strong_buy"] + summary["buy"] + summary["hold"] + summary["sell"] + summary["strong_sell"]
                            bullish = summary["strong_buy"] + summary["buy"]
                            rating_rows = "".join([
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:var(--up);padding:3px 14px 3px 0'>Strong Buy</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>{summary['strong_buy']}</td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:var(--up);padding:3px 14px 3px 0'>Buy</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>{summary['buy']}</td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:var(--muted);padding:3px 14px 3px 0'>Hold</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>{summary['hold']}</td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:var(--down);padding:3px 14px 3px 0'>Sell</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>{summary['sell']}</td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:var(--down);padding:3px 14px 3px 0'>Strong Sell</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>{summary['strong_sell']}</td></tr>",
                            ])
                            st.html(
                                f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;"
                                f"letter-spacing:0.08em;color:var(--muted);margin-bottom:8px'>"
                                f"{bullish}/{total} analysts bullish</div>"
                                f"<table style='border-collapse:collapse'>{rating_rows}</table>"
                            )
                    with col_b:
                        if pt:
                            upside = ((pt["mean"] - current_price) / current_price * 100)
                            u_color = "var(--up)" if upside >= 0 else "var(--down)"
                            pt_rows = "".join([
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--muted);padding:3px 14px 3px 0'>Mean</td>"
                                f"<td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>&#36;{pt['mean']:,.2f} <span style='color:{u_color};font-size:0.8em'>({upside:+.1f}%)</span></td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--muted);padding:3px 14px 3px 0'>Median</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>&#36;{pt['median']:,.2f}</td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--muted);padding:3px 14px 3px 0'>High</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>&#36;{pt['high']:,.2f}</td></tr>",
                                f"<tr><td style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--muted);padding:3px 14px 3px 0'>Low</td><td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;color:var(--text)'>&#36;{pt['low']:,.2f}</td></tr>",
                            ])
                            st.html(f"<table style='border-collapse:collapse;margin-bottom:12px'>{pt_rows}</table>")
                        if changes:
                            change_items = []
                            for c in changes[:4]:
                                a_color = "var(--up)" if c["action"] in ("upgrade", "init") else "var(--accent)" if c["action"] == "main" else "var(--down)"
                                from_str = f" ← {c['from_grade']}" if c['from_grade'] else ""
                                change_items.append(
                                    f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;"
                                    f"padding:4px 0;border-bottom:1px solid var(--border)'>"
                                    f"<span style='color:{a_color};margin-right:6px'>▸</span>"
                                    f"<span style='color:var(--text);font-weight:600'>{c['firm']}</span>"
                                    f"<span style='color:var(--muted)'> — {c['to_grade']}{from_str}"
                                    f" &nbsp;·&nbsp; {c['date'].strftime('%b %d')}</span></div>"
                                )
                            st.html(
                                f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.62rem;"
                                f"letter-spacing:0.12em;text-transform:uppercase;color:var(--muted);margin-bottom:6px'>"
                                f"Recent Actions</div>"
                                f"{''.join(change_items)}"
                            )

        # --- Pane 2: Timeline + News ---
        with st.expander("🗓️ Timeline & News", expanded=False):
            render_event_pills(events)
            if isinstance(pos, OptionPosition):
                render_timeline(events, pos.expiry, "Expiry")
            else:
                stock_horizon = date.today() + timedelta(days=365)
                render_timeline(events, stock_horizon, "1 year out")
            finviz_news = entry.get("finviz", {}).get("news", [])
            if finviz_news:
                section_header("Recent News")
                news_items = []
                for item in finviz_news:
                    date_str = item["date"].strftime("%b %d") if hasattr(item.get("date"), "strftime") else ""
                    source = item.get("source", "")
                    title = item.get("title", "")
                    link = item.get("link", "")
                    title_html = (
                        f"<a href='{link}' target='_blank' style='color:var(--text);text-decoration:none;"
                        f"font-family:IBM Plex Mono,monospace;font-size:0.78rem;line-height:1.5'>{title}</a>"
                        if link else
                        f"<span style='font-family:IBM Plex Mono,monospace;font-size:0.78rem;color:var(--text)'>{title}</span>"
                    )
                    news_items.append(
                        f"<div style='padding:7px 0;border-bottom:1px solid var(--border)'>"
                        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.63rem;"
                        f"letter-spacing:0.08em;color:var(--muted);margin-bottom:3px'>"
                        f"{date_str} &nbsp;·&nbsp; {source}</div>"
                        f"{title_html}</div>"
                    )
                st.html(f"<div>{''.join(news_items)}</div>")

        # --- Position Greeks (options only, collapsed) ---
        if isinstance(pos, OptionPosition) and entry.get("greeks"):
            g = entry["greeks"]
            iv_note = "" if entry.get("iv_source") == "live" else " *(IV estimated at 35%)*"
            with st.expander(f"Position Greeks{iv_note}", expanded=False):
                explanations = greeks_explanations(g, pos.option_type, pos.position, ticker)
                greek_rows = [
                    ("Delta",  f"{g.delta:+.4f}",  explanations["Delta"]),
                    ("Gamma",  f"{g.gamma:+.4f}",  explanations["Gamma"]),
                    ("Theta",  f"&#36;{g.theta:+,.2f}/day", explanations["Theta"]),
                    ("Vega",   f"&#36;{g.vega:+,.2f} per 1% IV", explanations["Vega"]),
                    ("Rho",    f"&#36;{g.rho:+,.2f} per 1% rate", explanations["Rho"]),
                ]
                table_rows = "".join(
                    f"<tr>"
                    f"<td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;font-weight:600;"
                    f"letter-spacing:0.06em;color:var(--text);padding:5px 16px 5px 0;white-space:nowrap'>{name}</td>"
                    f"<td style='font-family:IBM Plex Mono,monospace;font-size:0.82rem;font-weight:600;"
                    f"color:var(--accent);padding:5px 16px 5px 0;white-space:nowrap'>{value}</td>"
                    f"<td style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;"
                    f"color:var(--muted);padding:5px 0;line-height:1.5'>{explanation}</td>"
                    f"</tr>"
                    for name, value, explanation in greek_rows
                )
                st.html(
                    f"<table style='border-collapse:collapse;width:100%'>{table_rows}</table>"
                )

        # --- Scenarios ---
        section_header("Your options")
        if not OPENROUTER_KEY:
            st.caption("Add OPENROUTER_API_KEY to .env to enable AI explanations.")

        overall = entry.get("overall_analysis", "")
        if overall:
            st.markdown(
                f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.8rem;"
                f"line-height:1.65;color:#b0b0c0;background:#0f0f0a;"
                f"border:1px solid #1e1e22;border-top:2px solid #f0b429;"
                f"border-radius:2px;padding:12px 16px;margin-bottom:16px'>"
                f"<div style='font-size:0.62rem;letter-spacing:0.15em;color:#555566;"
                f"text-transform:uppercase;margin-bottom:8px'>AI Briefing</div>"
                f"{overall.replace('$', r'&#36;')}</div>",
                unsafe_allow_html=True,
            )

        for i, scenario in enumerate(scenarios):
            render_scenario_card(scenario, i)

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
# Watchlist tab
# ---------------------------------------------------------------------------
with tab_watchlist:
    section_header("Saved Analysis")
    if st.session_state.watchlist_just_analyzed:
        _analyzed_ticker = st.session_state.watchlist_just_analyzed
        _tab_name = "OPTIONS" if st.session_state.result and isinstance(st.session_state.result["position"], OptionPosition) else "STOCKS"
        st.success(f"Analysis for **{_analyzed_ticker}** is ready — switch to the **{_tab_name}** tab to see it.")
        st.session_state.watchlist_just_analyzed = None
    rows = load_watchlist()

    if not rows:
        st.html(
            "<div style='font-family:IBM Plex Mono,monospace;font-size:0.8rem;color:var(--muted);"
            "border:1px solid var(--border);border-radius:2px;padding:20px 18px'>"
            "No saved analyses yet. Analyze a position and click Save Analysis.</div>"
        )
    else:
        for i, row in enumerate(rows):
            pos_type = row.get("type", "")
            ticker = row.get("ticker", "")
            saved_at = row.get("saved_at", "")
            pnl_val = row.get("pnl", "")
            pnl_pct_val = row.get("pnl_pct", "")
            summary = row.get("overall_analysis", "")

            if pos_type == "stock":
                meta = f"Stock &nbsp;·&nbsp; {row.get('shares_contracts')} shares &nbsp;·&nbsp; cost &#36;{row.get('cost_basis_premium')}"
            else:
                meta = (f"{row.get('option_type','').upper()} &nbsp;·&nbsp; "
                        f"Strike &#36;{row.get('strike')} &nbsp;·&nbsp; "
                        f"Exp {row.get('expiry')} &nbsp;·&nbsp; "
                        f"{row.get('shares_contracts')} contract(s) &nbsp;·&nbsp; &#36;{row.get('cost_basis_premium')} premium")

            # P&L color
            pnl_color = "var(--muted)"
            if pnl_val:
                pnl_color = "var(--down)" if str(pnl_val).startswith("-") or "(-" in str(pnl_pct_val) else "var(--up)"
            pnl_html = (
                f"<span style='color:{pnl_color};font-weight:600'>{pnl_val}</span>"
                f"<span style='color:{pnl_color};font-size:0.85em'> ({pnl_pct_val})</span>"
            ) if pnl_val else ""

            summary_html = (
                f"<div style='font-size:0.75rem;color:var(--muted);font-style:italic;"
                f"margin-top:6px;line-height:1.55;border-top:1px solid var(--border);padding-top:7px'>"
                f"{summary.replace('$', '&#36;')}</div>"
            ) if summary else ""

            with st.container():
                st.html(
                    f"<div style='border:1px solid var(--border);border-left:3px solid var(--border);"
                    f"border-radius:2px;padding:14px 16px 10px;background:var(--surface);margin-bottom:2px'>"
                    f"<div style='display:flex;align-items:baseline;gap:10px;margin-bottom:4px'>"
                    f"<span style='font-family:Syne,sans-serif;font-size:1.05rem;font-weight:700;"
                    f"color:var(--text)'>{ticker}</span>"
                    f"<span style='font-family:IBM Plex Mono,monospace;font-size:0.68rem;"
                    f"color:var(--muted);letter-spacing:0.06em'>{meta}</span>"
                    f"</div>"
                    f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;"
                    f"color:var(--muted);margin-bottom:2px'>"
                    f"Saved {saved_at}"
                    f"{'&nbsp;&nbsp;·&nbsp;&nbsp;' + pnl_html if pnl_html else ''}"
                    f"</div>"
                    f"{summary_html}"
                    f"</div>"
                )
                col_analyze, col_delete, _ = st.columns([1, 1, 6])
                with col_analyze:
                    if st.button("Re-analyze", key=f"analyze_{i}", use_container_width=True):
                        position = row_to_position(row)
                        if position:
                            with st.spinner(f"Analyzing {ticker}..."):
                                result = analyze_position(position)
                            if result.get("error"):
                                st.error(result["error"])
                            else:
                                st.session_state.result = result
                                st.session_state.watchlist_just_analyzed = ticker
                                st.rerun()
                        else:
                            st.error("Could not parse saved position.")
                with col_delete:
                    if st.button("Delete", key=f"delete_{i}", use_container_width=True):
                        if delete_position(i + 1):
                            st.rerun()
                        else:
                            st.error("Could not delete.")
                st.html("<div style='margin-bottom:8px'></div>")
