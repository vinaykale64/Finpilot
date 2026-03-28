# Finpilot — CLAUDE.md

## Project overview

Finpilot is a Streamlit web app for retail traders. Users enter a stock or single-leg option position and receive plain-English guidance on how to manage it. The app fetches live market data, runs a rule-based scenario engine, computes Black-Scholes Greeks, and generates narratives via Claude (through OpenRouter).

## Architecture

```
app.py                  — Streamlit entry point, UI rendering, analysis pipeline
finpilot/
  models.py             — Dataclasses: StockPosition, OptionPosition, MarketEvent, RollCandidate, Scenario, Greeks
  fetcher.py            — yfinance wrappers: prices, option chains, expiry dates, events
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
- **No portfolio view** — individual positions only; portfolio aggregation is a future milestone.
- **LLM model** — hardcoded to `anthropic/claude-sonnet-4-6` via OpenRouter. Do not add a model selector dropdown.
- **Option expiry** — loaded from yfinance real available dates (two-step: enter ticker → load expiries → select). Do not replace with a free-form date picker.
- **Stock chart** — shown for stock positions only, not options. Uses hourly data for 1W/1M, daily for 3M/YTD/1Y. Weekend/overnight gaps hidden via Plotly `rangebreaks`.
- **Dollar signs in Streamlit** — always escape with `.replace("$", r"\$")` before passing to `st.caption`, `st.info`, or any markdown-rendered component to prevent LaTeX rendering.
- **Greeks computed before scenarios** — `calculate_greeks()` is called first so `theta_per_day` can be passed into `option_scenarios()`, keeping both displays consistent.

## Scenario engine

### Stocks (`stock_scenarios`)
Returns scenarios for: Hold, Sell now, Set a stop-loss, Buy more (if down).

### Options (`option_scenarios`)
Returns scenarios for: Hold to expiry, Sell now, Buy more time (roll out), Move to better strike (roll).

Roll candidates come from `rank_roll_candidates()` which:
- Fetches live options chain via `fetch_options_chain_for_rolls()` (±20% of spot, OI > 100, bid > 0, ≥14 days beyond current expiry)
- Filters to three types: `credit_roll`, `same_strike_out`, `better_strike`
- Applies direction-aware "better strike" logic:
  - Long call: lower strike is better
  - Long put: higher strike is better
  - Short call: higher strike is better
  - Short put: lower strike is better

### Roll math
- `net_value` (on `RollCandidate`): positive = net credit received, negative = net debit paid
  - Long: `current_mark - new_mark`
  - Short: `new_mark - current_mark`
- `extra_days`: days gained over the *current* expiry (not from today)
- All-in break-even: `new_strike ± (original_premium - current_mark + new_premium)`

## Dependencies

```
streamlit>=1.35.0
python-dotenv>=1.0.0
yfinance>=0.2.40
openai>=1.30.0
pandas>=2.0.0
python-dateutil>=2.9.0
plotly>=5.18.0
```

Python 3.9 — use `Optional[X]` not `X | None`.
