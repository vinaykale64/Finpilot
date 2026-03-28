# Finpilot — CLAUDE.md

## Project overview

Finpilot is a Streamlit web app for retail traders. Users enter a stock or single-leg option position and receive plain-English guidance on how to manage it. The app fetches live market data, runs a rule-based scenario engine, computes Black-Scholes Greeks, and generates narratives via Claude (through OpenRouter).

## Architecture

```
app.py                  — Streamlit entry point, UI rendering, analysis pipeline
finpilot/
  models.py             — Dataclasses: StockPosition, OptionPosition, MarketEvent, RollCandidate, Scenario, Greeks
  fetcher.py            — yfinance wrappers: prices, option chains, expiry dates, strikes, events, analyst data, snapshot
  rules.py              — Scenario engine: stock_scenarios(), option_scenarios(), rank_roll_candidates()
  greeks.py             — Black-Scholes Greeks calculator (math only, no extra deps)
  llm.py                — OpenRouter/Claude narrative generation
```

## Running the app

```bash
source .venv/bin/activate
streamlit run app.py
```

Runs on http://localhost:8501 by default.

## Environment setup

Copy `.env` and fill in your key:

```
OPENROUTER_API_KEY=your_key_here
```

The app reads this at startup via `python-dotenv`. No key = AI narratives disabled, rule-based analysis still works.

## Key design decisions

- **No persistent storage** — all state lives in `st.session_state` for the current browser session only.
- **Single position view** — analyzing a new position replaces the previous result, no accumulation.
- **No multi-leg options** — single-leg only for now; multi-leg is a future milestone.
- **Options are long-only** — `position` is hardcoded to `"long"`. Short options removed from UI.
- **No portfolio view** — individual positions only; portfolio aggregation is a future milestone.
- **LLM model** — hardcoded to `anthropic/claude-sonnet-4-6` via OpenRouter. Do not add a model selector dropdown.
- **Single LLM call** — `generate_all_narratives()` makes one call covering all scenarios, returning `(scenarios, overall_analysis)`. Do not revert to per-scenario calls.
- **Option form is three-step** — ticker → load expiries → select expiry+type (outside form, triggers strike fetch) → fill strike+premium+contracts in form.
- **Strike selectbox** — loaded from live options chain for the selected expiry/type, defaults to strike closest to current price. Do not replace with a free-form number input.
- **Stock chart** — shown for stock positions only, not options. Uses hourly data for 1W/1M, daily for 3M/YTD/1Y. Weekend/overnight gaps hidden via Plotly `rangebreaks`.
- **Dollar signs in Streamlit** — always escape with `.replace("$", r"\$")` before passing to `st.caption`, `st.info`, or any markdown-rendered component to prevent LaTeX rendering.
- **Greeks computed before scenarios** — `calculate_greeks()` is called first so `theta_per_day` can be passed into `option_scenarios()`, keeping both displays consistent.
- **lxml required** — needed by yfinance `earnings_dates`. Already in requirements.txt.

## Result dict structure

`analyze_position()` returns:
```python
{
  "position": StockPosition | OptionPosition,
  "error": str | None,
  "current_price": float,
  "current_mark": float | None,      # options only
  "events": list[MarketEvent],
  "scenarios": list[Scenario],
  "overall_analysis": str,           # LLM overall summary
  "analyst": dict,                   # from fetch_analyst_data()
  "snapshot": dict,                  # from fetch_stock_snapshot()
  "greeks": Greeks | None,           # options only
  "iv_source": "live" | "estimated", # options only
  "roll_candidates": list,           # options only
}
```

## LLM context pipeline

`generate_all_narratives()` builds context from four sources before calling Claude:
1. `_build_position_context()` — position details, P&L, events
2. `_build_snapshot_context()` — 52w range, beta, volume ratio, P/E, growth, short ratio
3. `_build_analyst_context()` — price targets, ratings summary, recent upgrades/downgrades
4. Scenarios block — all scenarios with key numbers and tradeoffs

Returns `(updated_scenarios, overall_analysis_str)`.

## Fetcher functions

- `fetch_current_price(ticker)` → float
- `fetch_option_mark(ticker, type, strike, expiry)` → float
- `fetch_events(ticker, position)` → list[MarketEvent] — earnings (projected quarterly), Fed meetings (hardcoded FOMC), ex-div, expiry
- `fetch_expiry_dates(ticker)` → list[date]
- `fetch_strikes_for_expiry(ticker, expiry, option_type)` → list[float]
- `fetch_options_chain_for_rolls(ticker, position, price)` → DataFrame
- `fetch_analyst_data(ticker)` → dict with `summary`, `price_targets`, `recent_changes`
- `fetch_stock_snapshot(ticker)` → dict with 52w range, beta, volume, P/E, growth, short ratio

## Events

`MarketEvent.event_type` values: `"earnings"`, `"ex_dividend"`, `"expiry"`, `"fed_meeting"`

FOMC dates are hardcoded in `fetcher.py` through 2027. Update annually from federalreserve.gov.

Earnings: uses `t.earnings_dates` (property, not callable — requires `lxml`). Projects forward quarterly from the latest known date to fill the horizon.

## Scenario engine

### Stocks (`stock_scenarios`)
Returns scenarios for: Hold, Sell now, Set a stop-loss, Buy more (if down).

### Options (`option_scenarios`)
Returns scenarios for: Hold to expiry, Sell now, Buy more time (roll out), Move to better strike (roll).

Roll candidates from `rank_roll_candidates()`:
- Filters: ±20% of spot, OI > 100, bid > 0, ≥14 days beyond current expiry
- Types: `credit_roll`, `same_strike_out`, `better_strike`
- Direction-aware better-strike logic:
  - Long call: lower strike is better
  - Long put: higher strike is better
  - Short call: higher strike is better
  - Short put: lower strike is better

### Roll math
- `net_value`: positive = net credit, negative = net debit
  - Long: `current_mark - new_mark`
  - Short: `new_mark - current_mark`
- `extra_days`: days gained over the *current* expiry (not from today)
- All-in break-even: `new_strike ± (original_premium - current_mark + new_premium)`

## Dependencies

```
streamlit>=1.35.0
python-dotenv>=1.0.0
lxml>=5.0.0
yfinance>=0.2.40
openai>=1.30.0
pandas>=2.0.0
python-dateutil>=2.9.0
plotly>=5.18.0
```

Python 3.9 — use `Optional[X]` not `X | None`.
