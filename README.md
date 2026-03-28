# Finpilot

**Know your options.** A plain-English position manager for retail traders.

Enter a stock or single-leg option position and get clear, jargon-free guidance on what to do next — hold, sell, roll, or add. Powered by live market data and Claude AI.

## Features

- **Stock & option positions** — P&L, actionable scenarios with AI narratives
- **Stock price chart** — hourly for 1W/1M, daily for 3M/YTD/1Y, weekends hidden
- **📊 Market context** (collapsible) — 52-week range, beta, volume, P/E, RSI, SMA20/50/200, volatility, performance, analyst ratings + price targets
- **🗓️ Timeline & News** (collapsible) — event timeline to expiry/1Y with earnings, Fed meetings, ex-dividend dates; recent news headlines with links
- **🔢 Position Greeks** (collapsible, options only) — delta, gamma, theta, vega, rho with plain-English explanations
- **Your options** — rule-based scenarios with AI analysis (single LLM call, overall summary + per-scenario 2-liner)
- **Live data** — prices, option chains, expiry dates, strikes via yfinance; technicals and news via Finviz

## Setup

**1. Clone and create a virtual environment**

```bash
git clone <repo>
cd Finpilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Add your OpenRouter API key**

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=your_key_here
```

Get a key at [openrouter.ai](https://openrouter.ai). The app works without a key — AI narratives are disabled but all rule-based analysis still runs.

**3. Run**

```bash
streamlit run app.py
```

Opens at http://localhost:8501.

## Project structure

```
app.py              — Streamlit UI and analysis pipeline
finpilot/
  models.py         — Data models (StockPosition, OptionPosition, etc.)
  fetcher.py        — Live market data via yfinance + Finviz
  rules.py          — Scenario and roll analysis engine
  greeks.py         — Black-Scholes Greeks calculator
  llm.py            — Claude narrative generation via OpenRouter
```

## Current scope

- Single stock and single-leg option positions (long only for options)
- Individual position view (no portfolio aggregation yet)
- No persistent storage — session only

## Tech stack

Python 3.9 · Streamlit · yfinance · Finviz · Plotly · OpenRouter (Claude)
