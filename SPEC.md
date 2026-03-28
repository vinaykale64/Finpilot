# Finpilot — Product Spec v0.1

## Overview

A Streamlit web app for retail traders to enter their stock and options positions and receive plain-English guidance on how to manage them. The app surfaces live price data, upcoming market events, and both rule-based scenarios and LLM-generated narratives to help users make informed decisions without needing to speak "finance."

---

## Out of Scope for V1

- Multi-leg options (spreads, straddles, collars) — later
- Persistent storage / user accounts — later
- Portfolio-level view (correlation, net delta, sector exposure) — later
- Broker API integration — later

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Frontend | Streamlit |
| Backend logic | Python |
| Market data | yfinance |
| LLM narrative | OpenRouter API (user-provided key) |
| Session state | Streamlit `st.session_state` (in-memory only) |

---

## Data Models

### Stock Position
```
ticker:       str       # e.g. "AAPL"
shares:       float     # number of shares
cost_basis:   float     # price per share paid
entry_date:   date      # optional, used for tax context display
```

### Option Position
```
ticker:       str       # underlying ticker
option_type:  str       # "call" or "put"
position:     str       # "long" or "short"
strike:       float     # strike price
expiry:       date      # expiration date
premium:      float     # premium paid per share (x100 = contract cost)
contracts:    int       # number of contracts
```

---

## Live Data Fetched (yfinance)

For each position fetch:
- Current price
- Earnings date (next)
- Ex-dividend date (next)
- For options: implied volatility, current option premium (mark price)
- 52-week high/low (context)

---

## Position States (Rule Engine Inputs)

| State | Condition |
|-------|-----------|
| In profit | current price > cost basis (stocks) / option mark > premium paid |
| At loss | current price < cost basis / option mark < premium paid |
| Near breakeven | within 2% of cost basis |
| Option expiring soon | ≤ 7 days to expiry |
| Event imminent | earnings or ex-div within 5 days |
| Deep ITM / OTM | option delta proxy via moneyness |

---

## Scenario Engine

For each position, generate 3–5 labeled scenarios based on position state.
Each scenario includes:
- **Action label** (plain English, no jargon)
- **Key numbers** (proceeds, new cost basis, break-even, etc.)
- **Trade-off** (what you gain vs. what you give up)
- **LLM narrative** (1–3 sentences, conversational tone)

### Stock Scenarios

**In Profit:**
1. Lock in your gains — sell all shares, show net proceeds
2. Sell half, keep the rest — lock in partial gains, stay exposed to upside
3. Hold and let it run — show downside if it reverses to cost basis
4. Buy more — recalculate average cost, show new break-even

**At Loss:**
1. Sell and cut the loss — show net loss, mention tax-loss harvesting if applicable
2. Buy more to lower your average — new cost basis needed to break even
3. Hold and wait — how far stock needs to recover (% and $) to break even
4. Set a stop-loss — suggest level (e.g., 5–8% below current)

**Near Breakeven:**
- Subset of above with emphasis on low-stakes decision point

### Option Scenarios

**Long Call — In Profit:**
1. Sell the option now — current premium value, net gain
2. Hold to expiry — break-even price required by expiry date
3. Close before earnings — flag IV crush risk in plain English
4. Sell partial contracts — reduce risk, keep some upside

**Long Call — At Loss:**
1. Sell now and limit the damage — current value, remaining loss
2. Hold and hope — break-even price required, days remaining
3. Close before expiry — avoid total loss if far OTM

**Long Put — mirror of Long Call logic with direction flipped**

**Short Call / Short Put:**
1. Buy back now — cost to close, net P&L
2. Hold to expiry — max profit if expires worthless
3. Roll out — see Roll Analysis section below

---

### Roll Analysis (Options Only)

When any option position is analyzed, the app fetches the **live options chain** for the underlying ticker via yfinance and runs background math to surface concrete roll candidates. These are shown as a dedicated "Roll this option" scenario with specific examples — not a generic suggestion.

#### What Gets Fetched
- All available expiry dates beyond the current position's expiry
- For each expiry: strikes within a relevant range (±20% of current stock price)
- Mark price (mid of bid/ask) for each candidate

#### Roll Candidate Filters
Only surface candidates that meet all of:
- Expiry is at least **2 weeks further** than current expiry
- Same option type (call/put) and position direction (long/short)
- Strike is within ±20% of current stock price
- Has sufficient open interest (> 100) and non-zero bid

#### Math Computed Per Candidate

| Metric | Formula |
|--------|---------|
| Cost to roll | (cost to close current) − (premium received/paid for new) |
| New break-even | new strike ± net debit or credit to roll |
| Additional time gained | new expiry − current expiry (in days) |
| Net credit / debit | positive = you receive money to roll, negative = you pay |

#### Candidate Display (up to 3 suggestions)

For each roll candidate shown:
- **New strike & expiry** in plain English ("Move to $190 strike, expiring June 20")
- **Net cost or credit** ("Costs you $0.45/share — $45 per contract" or "You collect $0.30/share — $30 per contract")
- **New break-even price**
- **Extra time gained**
- **LLM narrative** summarizing the trade-off in 2 sentences

#### Roll Candidate Selection Logic (rule-based ranking)

Priority order for which 3 candidates to surface:
1. **Same strike, later expiry** — cheapest way to buy time
2. **Better strike (more favorable), same or later expiry** — improve position at a cost
3. **Credit roll** — any roll that generates net credit (always show if available)

#### Plain-English labels for roll scenarios

| Roll type | Label shown to user |
|-----------|-------------------|
| Same strike, out in time | "Buy more time at the same target price" |
| Better strike, net debit | "Move to a better price, pay a small fee" |
| Net credit roll | "Move out and get paid to do it" |

---

## Event Horizon

- **Stocks:** fetch all known events up to **12 months** from today
- **Options:** fetch all known events up to the **option expiry date** (never beyond)

Events fetched per ticker:
- All scheduled earnings dates within the window
- All ex-dividend dates within the window
- For options: expiry date itself as a first-class event

## Event Display

All upcoming events are shown in a **timeline view** under the position summary — not just the next one. This lets the user see, for example, two earnings cycles and three ex-div dates before their option expires.

### Urgency Tiers (color-coded)

| Tier | Condition | Color |
|------|-----------|-------|
| Critical | ≤ 7 days | Red |
| Soon | 8–30 days | Yellow/Orange |
| On radar | 31+ days (within window) | Blue/Neutral |

### Event Copy by Type

| Event | Display copy |
|-------|-------------|
| Earnings (any tier) | "Earnings on [date] — [X days away]. Stock prices can move sharply. Options often get more expensive before earnings, then drop right after." |
| Ex-dividend (any tier) | "Ex-dividend on [date] — [X days away]. If you hold a short call, early assignment risk increases around this date." |
| Option expiry | "This option expires on [date] — [X days away]. After this date it has no value." |

### Scenario Engine Integration

Events within the window are passed into the rule engine and LLM prompt as context, so scenarios can reference them explicitly — e.g., "There are two earnings events before your option expires. The first is in 18 days."

---

## Plain-English Translations (built-in)

The app never shows raw finance terms without a plain-English equivalent:

| Finance term | Plain English shown |
|-------------|---------------------|
| Cost basis | "what you paid" |
| Break-even | "the price you need to just get your money back" |
| Theta decay | "this option loses ~$X per day just from time passing" |
| IV crush | "option prices tend to drop sharply after earnings — even if the stock moves your way" |
| Premium | "the price you paid for the option contract" |
| In the money | "currently profitable if exercised" |
| Out of the money | "not yet profitable — needs to move further" |
| Contracts | "1 contract = 100 shares worth of exposure" |

---

## LLM Narrative Layer

### Purpose
Wrap each rule-based scenario in a conversational 1–3 sentence explanation tailored to the position's specific numbers and context.

### OpenRouter Setup
- User enters their OpenRouter API key in the Streamlit sidebar on first use
- Key is stored in `st.session_state` for the session (never persisted)
- App calls OpenRouter's OpenAI-compatible endpoint (`https://openrouter.ai/api/v1/chat/completions`)
- Default model: `anthropic/claude-haiku-4-5` — user can optionally select from a short list of supported models in the sidebar

### Prompt Structure
```
System: You are a plain-English financial coach for retail investors.
        Avoid jargon. Explain trade-offs simply. Be direct and concise.
        Never give definitive buy/sell recommendations — frame as options.

User:   Position: Long 100 shares of AAPL, cost basis $165, current price $182.
        Upcoming: Earnings in 4 days.
        Scenario: Sell half to lock in partial gains.

        Write a 2-sentence plain-English explanation of this option for a retail trader.
```

### Guardrails
- Always append: "This is not financial advice."
- Do not predict future price direction
- Frame all scenarios as possibilities, not recommendations

---

## UI Layout (Streamlit)

```
[Header] Finpilot — Know your options

[Section 1 — Add Position]
  Tab: Stock | Option
  Form fields based on type
  [Fetch & Analyze] button

[Section 2 — Position Summary]
  Ticker | Type | You paid | Current price | P&L $ | P&L %
  Event warnings (if any) shown here in colored banners

[Section 3 — Your Options]  ← core section
  Card per scenario:
    - Action title (bold, plain English)
    - Key numbers
    - Trade-off line
    - LLM narrative (collapsible or shown inline)

[Section 4 — Position List]
  All positions entered this session (session_state)
  Click to re-analyze any position
  Remove button per position
```

---

## V1 Success Criteria

- User can enter a stock or single-leg option position
- App fetches live price and event data via yfinance
- Rule engine generates at least 3 relevant scenarios per position
- Each scenario has plain-English labels and key numbers
- LLM narrative renders for each scenario
- Event warnings appear when earnings/expiry/div are within threshold
- No jargon displayed without plain-English explanation
- Works entirely in-session (no database, no login)

---

## Later Development Backlog

- [ ] Persistent storage + user accounts
- [ ] Portfolio-level view (net exposure, sector breakdown)
- [ ] Multi-leg options (spreads, straddles, covered calls)
- [ ] Broker API import (Alpaca, Schwab, IBKR)
- [ ] Price alerts
- [ ] Historical position tracking / journal
- [ ] Mobile-optimized layout
