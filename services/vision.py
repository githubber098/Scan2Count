from __future__ import annotations

import base64
import json
import re

import anthropic

_PROMPT_TEMPLATE = """\
You are a nutrition assistant specializing in Indian cuisine. Analyze this meal photo \
and identify every distinct food item visible.

You MUST match each item to the closest entry from the list below — use the name EXACTLY \
as it appears, no variations, no new names.

Known food items:
{food_names_list}

For each matched item, estimate the quantity using the most natural unit:
- Pieces/items (roti, paratha, naan, poori, idli, dosa, samosa, egg): number of pieces
- Cups (rice, dal, curry, sabzi, raita, soup): number of cups (0.5, 1, 1.5, 2 etc.)
- Weight (pakora, paneer, chicken, fish, meat): grams

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {{"name": "Roti (Plain Wheat)", "quantity": 2, "unit": "piece"}},
  {{"name": "Dal Makhani", "quantity": 1, "unit": "cup"}}
]

Guidelines:
- List each dish component separately, not as one combined entry
- If quantity is unclear, use a typical single-serving estimate
- Return [] if no food is visible
- Do NOT invent names outside the list above
"""


def analyze_meal_photo(
    image_bytes: bytes,
    media_type: str,
    food_names: list[str],
) -> list[dict]:
    """
    Send a meal photo to Claude vision and return identified foods with quantities.
    Returns [{"name": str, "quantity": float, "unit": str}, ...]
    food_names should be the full list from indian_food_items.item_name.
    """
    client = anthropic.Anthropic()
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    names_block = "\n".join(f"- {n}" for n in food_names)
    prompt = _PROMPT_TEMPLATE.format(food_names_list=names_block)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )

    text = response.content[0].text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group())
        return [
            i for i in items
            if isinstance(i, dict) and "name" in i and "quantity" in i
        ]
    except json.JSONDecodeError:
        return []
