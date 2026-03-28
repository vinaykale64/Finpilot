# Finpilot

**Know your options.** A plain-English position manager for retail traders.

Enter a stock or single-leg option position and get clear, jargon-free guidance on what to do next — hold, sell, roll, or add. Powered by live market data and Claude AI.

## Features

- **Stock positions** — P&L, upcoming events (earnings, ex-dividend), and actionable scenarios with AI narratives
- **Option positions** — Greeks (delta, gamma, theta, vega, rho), roll analysis with live options chain data, all-in break-even calculations
- **Stock price chart** — hourly for 1W/1M, daily for 3M/YTD/1Y, with weekends hidden
- **Live data** — prices, option chains, and expiry dates via yfinance
- **AI narratives** — plain-English explanations of each scenario via Claude (claude-sonnet-4-6 through OpenRouter)

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

Get a key at [openrouter.ai](https://openrouter.ai). The app works without a key — AI narratives are disabled but rule-based analysis still runs.

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

- Single stock and single-leg option positions
- Individual position view (no portfolio aggregation yet)
- No persistent storage — session only

## Tech stack

Python 3.9 · Streamlit · yfinance · Plotly · OpenRouter (Claude)
