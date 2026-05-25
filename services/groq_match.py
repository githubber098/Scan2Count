from __future__ import annotations

import os
import logging

from groq import Groq

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a food name matcher for an Indian food nutrition database. "
    "Your only job is to pick the single best match from a given list."
)

_USER_TEMPLATE = """\
The user described this food: "{description}"

Pick the single best match from the list below. Rules:
- Return ONLY the exact name as it appears in the list — no extra words, no punctuation.
- If nothing is a reasonable match, return exactly: NO_MATCH

Known food items:
{names_block}
"""


def match_food_name(description: str, food_names: list[str]) -> str | None:
    """
    Use Groq (fast LLM) to map a free-text food description to the closest
    item_name in our indian_food_items database.

    Returns the matched item_name string, or None if no match found.
    Falls back to None on any API error (caller can try lookup_food directly).
    """
    if not food_names:
        return None

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping Groq match")
        return None

    client = Groq(api_key=api_key)
    names_block = "\n".join(f"- {n}" for n in food_names)
    prompt = _USER_TEMPLATE.format(description=description, names_block=names_block)

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=60,
            temperature=0,
        )
        result = response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Groq match failed: %s", exc)
        return None

    if result == "NO_MATCH":
        return None

    # Exact match first
    if result in food_names:
        return result

    # Case-insensitive fallback (in case the model changes capitalisation)
    lower_map = {n.lower(): n for n in food_names}
    return lower_map.get(result.lower())
