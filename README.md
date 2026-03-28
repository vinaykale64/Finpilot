# Finpilot

**Know your options.** A plain-English position manager for retail traders.

Enter a stock or single-leg option position and get clear, jargon-free guidance on what to do next — hold, sell, roll, or add. Powered by live market data and Claude AI.

## Features

- **Stock positions** — P&L, scenarios with AI narratives, stock price chart (1W/1M/3M/YTD/1Y)
- **Option positions** — Greeks (delta, gamma, theta, vega, rho), roll analysis with live chain data, all-in break-even
- **Stock snapshot** — 52-week range bar, beta, volume vs average, forward/trailing P/E, YoY growth, short ratio
- **Analyst ratings** — Buy/Hold/Sell consensus, price targets (mean/median/high/low), recent upgrades/downgrades
- **Event timeline** — visual timeline to expiry (options) or 1 year out (stocks) with earnings, Fed meetings, ex-dividend dates
- **AI narratives** — single LLM call covering all scenarios with an overall summary + per-scenario 2-line analysis
- **Live data** — prices, option chains, expiry dates, strikes, and events via yfinance

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
  fetcher.py        — Live market data via yfinance
  rules.py          — Scenario and roll analysis engine
  greeks.py         — Black-Scholes Greeks calculator
  llm.py            — Claude narrative generation via OpenRouter
```

## Current scope

- Single stock and single-leg option positions (long only for options)
- Individual position view (no portfolio aggregation yet)
- No persistent storage — session only

## Tech stack

Python 3.9 · Streamlit · yfinance · Plotly · OpenRouter (Claude)
