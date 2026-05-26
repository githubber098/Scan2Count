from __future__ import annotations

import os
import logging

from groq import Groq

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a food identity matcher for an Indian food nutrition database. "
    "You understand food names across languages, regional spellings, and common misspellings. "
    "You match based on what the food IS, not on shared words or ingredients."
)

_USER_TEMPLATE = """\
The user wants to log this food: "{description}"

Your job: find the entry in the database that refers to THE SAME FOOD as what the user described.

Matching rules — read carefully:
1. Match by MEANING, not by words. "litchi" and "Lychee" are the same fruit → match.
   "milk" and "Milk Peda" are NOT the same food (milk is an ingredient in peda, not the dish) → NO_MATCH.
2. Accept spelling variants, transliterations, and regional names.
   e.g. "alu" = "aloo", "bhindi" = "okra", "brinjal" = "eggplant/baingan".
3. If the user's description matches multiple variants (e.g. "coconut chutney" could be
   White or Green), prefer the most common / default variant.
4. Only return NO_MATCH if the food the user described genuinely does not exist in the
   database — not because the spelling differs or the name is in another language.
5. Return ONLY the exact database name as listed — no extra words, no explanation.
   If and only if there is truly no matching food, return exactly: NO_MATCH

Database entries:
{names_block}
"""


def match_food_name(description: str, food_names: list[str]) -> str | None:
    """
    Use Groq to map a free-text food description to the closest item_name
    in indian_food_items, matching by food identity (meaning) not word overlap.

    Returns the matched item_name string, or None if no match / API error.
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
            model="llama-3.3-70b-versatile",
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

    # Exact match
    if result in food_names:
        return result

    # Case-insensitive fallback (model may alter capitalisation)
    lower_map = {n.lower(): n for n in food_names}
    return lower_map.get(result.lower())
