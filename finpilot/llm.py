"""
LLM narrative layer via OpenRouter (OpenAI-compatible endpoint).
Generates plain-English explanations for each scenario.
"""
from typing import Union
from openai import OpenAI

from .models import MarketEvent, OptionPosition, Scenario, StockPosition

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"

SYSTEM_PROMPT = """You are a plain-English financial coach for everyday retail investors.
Your job is to explain investment options in simple, conversational language — like a knowledgeable friend, not a broker.

Rules:
- Never use jargon without explaining it immediately in plain terms
- Be direct and concise: 2-3 sentences max
- Frame everything as possibilities the user can consider, never as definitive advice
- Always end with: "This is not financial advice."
- Do not predict future price direction
- Be empathetic — investing is stressful, your tone should be calm and clear"""


def _build_position_context(
    position: Union[StockPosition, OptionPosition],
    current_price: float,
    events: list[MarketEvent],
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
        current_mark = current_price  # current_price passed in as mark for options
        pnl = position.pnl(current_mark)
        sign = "up" if pnl >= 0 else "down"
        lines.append(
            f"Position: {position.contracts} {position.position} {position.option_type} contract(s) on "
            f"{position.ticker.upper()}, strike ${position.strike:,.2f}, expires {position.expiry.strftime('%b %d, %Y')}. "
            f"Paid ${position.premium:,.2f}/share, now worth ~${current_mark:,.2f}/share ({sign} ${abs(pnl):,.2f} total). "
            f"Break-even: ${position.breakeven_price():,.2f}. Days to expiry: {position.days_to_expiry}."
        )

    if events:
        upcoming = [e for e in events if e.days_away >= 0][:3]
        if upcoming:
            event_strs = [f"{e.label} ({e.days_away} days away)" for e in upcoming]
            lines.append("Upcoming events: " + "; ".join(event_strs) + ".")

    return " ".join(lines)


def generate_narrative(
    scenario: Scenario,
    position: Union[StockPosition, OptionPosition],
    current_price: float,
    events: list[MarketEvent],
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Call OpenRouter to generate a plain-English narrative for a scenario.
    Returns the narrative string. On failure, returns the tradeoff as fallback.
    """
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )

        position_context = _build_position_context(position, current_price, events)

        key_numbers_str = ", ".join(f"{k}: {v}" for k, v in scenario.key_numbers.items())

        user_message = (
            f"{position_context}\n\n"
            f"Scenario the investor is considering: \"{scenario.action_label}\"\n"
            f"Key numbers: {key_numbers_str}\n"
            f"Trade-off: {scenario.tradeoff}\n\n"
            f"Write a 2-3 sentence plain-English explanation of this option for a retail investor. "
            f"Reference the specific numbers above. End with 'This is not financial advice.'"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=200,
            temperature=0.4,
        )

        return response.choices[0].message.content.strip()

    except Exception:
        return f"{scenario.tradeoff} This is not financial advice."


def generate_all_narratives(
    scenarios: list[Scenario],
    position: Union[StockPosition, OptionPosition],
    current_price: float,
    events: list[MarketEvent],
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> list[Scenario]:
    """Fill in narrative for each scenario and return updated list."""
    for scenario in scenarios:
        scenario.narrative = generate_narrative(
            scenario, position, current_price, events, api_key, model
        )
    return scenarios
