"""
LLM narrative layer via OpenRouter (OpenAI-compatible endpoint).
Generates a single combined analysis covering all scenarios.
"""
import json
from typing import Union
from openai import OpenAI

from .models import MarketEvent, OptionPosition, Scenario, StockPosition

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"

SYSTEM_PROMPT = """You are a plain-English financial coach for everyday retail investors.
Your job is to explain investment options in simple, conversational language — like a knowledgeable friend, not a broker.

Rules:
- Never use jargon without explaining it immediately in plain terms
- Be direct and concise
- Frame everything as possibilities the user can consider, never as definitive advice
- Do not predict future price direction
- Be empathetic — investing is stressful, your tone should be calm and clear"""


def _build_position_context(
    position: Union[StockPosition, OptionPosition],
    current_price: float,
    events: list,
    current_mark: float = None,
    greeks=None,
) -> str:
    lines = []

    if isinstance(position, StockPosition):
        pnl = position.pnl(current_price)
        pnl_pct = position.pnl_pct(current_price)
        sign = "up" if pnl >= 0 else "down"
        lines.append(
            f"Position: {position.shares:,.0f} shares of {position.ticker.upper()}, "
            f"bought at ${position.cost_basis:,.2f}, currently at ${current_price:,.2f} "
            f"({sign} {abs(pnl_pct):.1f}%, {'+' if pnl >= 0 else ''}{pnl:,.2f} total)."
        )
    else:
        mark = current_mark if current_mark is not None else 0.0
        pnl = position.pnl(mark)
        pnl_pct = position.pnl_pct(mark)
        sign = "up" if pnl >= 0 else "down"
        total_cost = position.premium * 100 * position.contracts
        lines.append(
            f"Position: {position.contracts} {position.position} {position.option_type} contract(s) on "
            f"{position.ticker.upper()}. "
            f"Strike ${position.strike:,.2f}, expires {position.expiry.strftime('%b %d, %Y')} "
            f"({position.days_to_expiry} days). "
            f"Stock is currently at ${current_price:,.2f}. "
            f"Paid ${position.premium:,.2f}/share (${total_cost:,.2f} total cost). "
            f"Option now worth ${mark:,.2f}/share "
            f"({sign} {abs(pnl_pct):.1f}%, {'+' if pnl >= 0 else ''}${abs(pnl):,.2f} total P&L). "
            f"Break-even stock price: ${position.breakeven_price():,.2f}."
        )
        if greeks:
            iv_pct = greeks.iv if greeks.iv else 0
            lines.append(
                f"Greeks: delta {greeks.delta:+.3f} (option moves ${abs(greeks.delta):.2f} per $1 stock move), "
                f"theta ${greeks.theta:+,.2f}/day (time decay cost), "
                f"vega ${greeks.vega:+,.2f} per 1% IV change. "
                f"Implied volatility: {iv_pct:.1f}%."
            )

    if events:
        upcoming = [e for e in events if e.days_away >= 0][:4]
        if upcoming:
            event_strs = [f"{e.label} ({e.days_away} days away)" for e in upcoming]
            lines.append("Upcoming events: " + "; ".join(event_strs) + ".")

    return " ".join(lines)


def _build_analyst_context(analyst: dict) -> str:
    if not analyst:
        return ""
    lines = []
    pt = analyst.get("price_targets")
    if pt:
        lines.append(
            f"Analyst price targets: mean ${pt['mean']}, median ${pt['median']}, "
            f"high ${pt['high']}, low ${pt['low']} (current stock price: ${pt['current']})."
        )
    s = analyst.get("summary")
    if s:
        total = s["strong_buy"] + s["buy"] + s["hold"] + s["sell"] + s["strong_sell"]
        if total > 0:
            lines.append(
                f"Analyst ratings ({total} analysts): "
                f"Strong Buy {s['strong_buy']}, Buy {s['buy']}, Hold {s['hold']}, "
                f"Sell {s['sell']}, Strong Sell {s['strong_sell']}."
            )
    changes = analyst.get("recent_changes")
    if changes:
        change_strs = [
            f"{c['firm']} ({c['action']}: {c['from_grade']} → {c['to_grade']})"
            for c in changes[:3] if c.get("firm")
        ]
        if change_strs:
            lines.append("Recent analyst actions: " + "; ".join(change_strs) + ".")
    return " ".join(lines)


def _build_snapshot_context(snapshot: dict) -> str:
    if not snapshot:
        return ""
    lines = []
    low = snapshot.get("week52_low")
    high = snapshot.get("week52_high")
    price = snapshot.get("current_price")
    if low and high and price:
        pct_range = (price - low) / (high - low) * 100 if high != low else 50
        lines.append(f"52-week range: ${low:,.2f} – ${high:,.2f} (stock is at {pct_range:.0f}% of its range).")
    beta = snapshot.get("beta")
    if beta:
        lines.append(f"Beta: {beta:.2f} ({'more volatile' if beta > 1 else 'less volatile'} than the market).")
    vol = snapshot.get("volume")
    avg_vol = snapshot.get("avg_volume")
    if vol and avg_vol and avg_vol > 0:
        vol_ratio = vol / avg_vol
        lines.append(f"Today's volume is {vol_ratio:.1f}x the average ({vol:,.0f} vs avg {avg_vol:,.0f}).")
    fpe = snapshot.get("forward_pe")
    tpe = snapshot.get("trailing_pe")
    if fpe:
        lines.append(f"Forward P/E: {fpe:.1f}" + (f", Trailing P/E: {tpe:.1f}." if tpe else "."))
    eg = snapshot.get("earnings_growth")
    rg = snapshot.get("revenue_growth")
    if eg or rg:
        parts = []
        if eg: parts.append(f"earnings growth {eg*100:.0f}%")
        if rg: parts.append(f"revenue growth {rg*100:.0f}%")
        lines.append("YoY: " + ", ".join(parts) + ".")
    sr = snapshot.get("short_ratio")
    if sr:
        lines.append(f"Short ratio: {sr:.1f} days to cover.")
    return " ".join(lines)


def _build_finviz_context(finviz: dict) -> str:
    if not finviz:
        return ""
    lines = []
    tech = finviz.get("technicals") or {}
    perf = finviz.get("performance") or {}
    recom = finviz.get("recom")

    rsi = tech.get("rsi14")
    if rsi is not None:
        rsi_label = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
        lines.append(f"RSI(14): {rsi:.1f} ({rsi_label}).")

    sma_parts = []
    for key, label in [("sma20_pct", "SMA20"), ("sma50_pct", "SMA50"), ("sma200_pct", "SMA200")]:
        v = tech.get(key)
        if v is not None:
            sma_parts.append(f"{label} {v:+.1f}%")
    if sma_parts:
        lines.append("vs moving averages: " + ", ".join(sma_parts) + ".")

    perf_parts = []
    for key, label in [("perf_week", "1W"), ("perf_month", "1M"), ("perf_quarter", "3M"), ("perf_ytd", "YTD")]:
        v = perf.get(key)
        if v is not None:
            perf_parts.append(f"{label}: {v:+.1f}%")
    if perf_parts:
        lines.append("Recent performance: " + ", ".join(perf_parts) + ".")

    if recom is not None:
        label = "Strong Buy" if recom <= 1.5 else "Buy" if recom <= 2.5 else "Hold" if recom <= 3.5 else "Sell"
        lines.append(f"Analyst consensus score: {recom:.2f}/5.0 ({label}).")

    return " ".join(lines)


def generate_combined_analysis(
    scenarios: list,
    position: Union[StockPosition, OptionPosition],
    current_price: float,
    events: list,
    api_key: str,
    model: str = DEFAULT_MODEL,
    analyst: dict = None,
    snapshot: dict = None,
    finviz: dict = None,
    current_mark: float = None,
    greeks=None,
) -> dict:
    """
    Single LLM call covering all scenarios.
    Returns {
        "overall": str,           # 2-3 sentence overall context
        "summaries": [str, ...]   # one 2-line summary per scenario, same order
    }
    On failure returns empty strings.
    """
    try:
        client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

        position_context = _build_position_context(position, current_price, events, current_mark, greeks)
        analyst_context = _build_analyst_context(analyst or {})
        snapshot_context = _build_snapshot_context(snapshot or {})
        finviz_context = _build_finviz_context(finviz or {})

        scenarios_block = "\n".join(
            f"{i+1}. {s.action_label} — "
            + ", ".join(f"{k}: {v}" for k, v in s.key_numbers.items())
            + f" | Trade-off: {s.tradeoff}"
            for i, s in enumerate(scenarios)
        )

        user_message = (
            f"{position_context}\n\n"
            + (f"Stock snapshot: {snapshot_context}\n\n" if snapshot_context else "")
            + (f"Technical signals: {finviz_context}\n\n" if finviz_context else "")
            + (f"Analyst data: {analyst_context}\n\n" if analyst_context else "")
            + f"The investor is weighing these options:\n{scenarios_block}\n\n"
            f"Respond with a JSON object with exactly two keys:\n"
            f"- \"overall\": 2-3 sentences of big-picture context about this position and what matters most right now. "
            f"End with 'This is not financial advice.'\n"
            f"- \"summaries\": a JSON array of exactly {len(scenarios)} strings, one per option above (same order). "
            f"Each string is 1-2 sentences covering the key trade-off for that specific option. "
            f"Reference the specific numbers. No financial advice disclaimer needed per item.\n\n"
            f"Return only valid JSON, no markdown."
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=600,
            temperature=0.4,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if model wraps in them
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()

        data = json.loads(raw)
        summaries = data.get("summaries", [])
        # Pad or trim to match scenario count
        while len(summaries) < len(scenarios):
            summaries.append("")
        summaries = summaries[:len(scenarios)]

        return {"overall": data.get("overall", ""), "summaries": summaries}

    except Exception:
        return {"overall": "", "summaries": [""] * len(scenarios)}


def generate_all_narratives(
    scenarios: list,
    position: Union[StockPosition, OptionPosition],
    current_price: float,
    events: list,
    api_key: str,
    model: str = DEFAULT_MODEL,
    analyst: dict = None,
    snapshot: dict = None,
    finviz: dict = None,
    current_mark: float = None,
    greeks=None,
) -> list:
    """Attach per-scenario narratives using a single combined LLM call."""
    result = generate_combined_analysis(
        scenarios, position, current_price, events, api_key, model, analyst, snapshot, finviz,
        current_mark=current_mark, greeks=greeks,
    )
    for i, scenario in enumerate(scenarios):
        scenario.narrative = result["summaries"][i]
    return scenarios, result.get("overall", "")
