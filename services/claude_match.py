from __future__ import annotations

import json
import logging

from anthropic import Anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a food name resolver for an Indian food nutrition database.
Given a list of canonical food names and user-typed inputs, map each input to \
the best matching canonical name.

Match rules (apply all):
- Typos/misspellings: "boilded egg" → "Boiled Egg", "chiken" → "Chicken Biryani"
- Regional/transliterated names: "litchi" → "Lychee", \
"chapati"/"chappati"/"CHAppAtti" → "Roti (Plain Wheat)", "dahi" → "Curd (Plain)"
- Word-order variants: "paratha stuffed" → "Stuffed Paratha"
- Single-word abbreviations where the word NAMES the dish: \
"dal" → "Dal Makhani", "paneer" → "Paneer Tikka", "roti" → "Roti (Plain Wheat)"

NO_MATCH rule: return NO_MATCH when the input is not semantically the food being named.
  Good example — "chips" should NOT match "Fish and Chips": a person asking for "chips"
  is not asking for the combined fish-and-chips dish; the word is only an ingredient/side.
  If the canonical name has the word somewhere in the middle or end but the input doesn't
  clearly identify THAT dish, return NO_MATCH.

Output: a single valid JSON object only, no markdown fences, no prose.\
"""


def match_food_names(
    descriptions: list[str],
    food_names: list[str],
) -> dict[str, str | None]:
    """
    Match a batch of free-text food descriptions to canonical names via Claude Haiku.

    All descriptions are sent in a single API call to minimise cost.
    Returns ``{description: canonical_name}``; NO_MATCH responses and any
    description absent from the model output are mapped to ``None``.
    On API/parse failure every description maps to ``None`` (soft failure —
    the caller shows "Not in database" rather than crashing).
    """
    if not descriptions or not food_names:
        return {d: None for d in descriptions}

    names_block  = "\n".join(f"- {n}" for n in food_names)
    inputs_block = "\n".join(f"- {d}" for d in descriptions)
    user_msg = (
        f"Canonical food names:\n{names_block}\n\n"
        f"Match these inputs (return the exact canonical name string or NO_MATCH):\n"
        f"{inputs_block}\n\nJSON:"
    )

    try:
        client = Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()

        # Strip markdown code fences if the model wraps its output
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed: dict = json.loads(raw.strip())
        return {
            desc: (parsed[desc] if parsed.get(desc) not in (None, "NO_MATCH") else None)
            for desc in descriptions
        }

    except Exception as exc:
        logger.error("claude_match.match_food_names failed: %s", exc)
        return {d: None for d in descriptions}
