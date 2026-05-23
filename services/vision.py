from __future__ import annotations

import base64
import json
import re

import anthropic

VISION_PROMPT = """\
You are a nutrition assistant specializing in Indian cuisine. Analyze this meal photo \
and identify every distinct food item visible.

For each item, estimate the quantity in grams based on visual cues \
(plate size, serving spoon, portion depth, standard bowl sizes).

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {"name": "dal makhani", "quantity_g": 150},
  {"name": "basmati rice", "quantity_g": 200}
]

Guidelines:
- Use common Indian food names where applicable \
(e.g. "rajma", "poha", "idli", "paneer butter masala", "roti")
- List each dish component separately, not as one combined entry
- If quantity is unclear, use a typical single-serving estimate
- Return [] if no food is visible
"""


def analyze_meal_photo(image_bytes: bytes, media_type: str) -> list[dict]:
    """
    Send a meal photo to Claude vision and return identified foods with quantities.
    Returns [{"name": str, "quantity_g": float}, ...]
    """
    client = anthropic.Anthropic()
    image_b64 = base64.standard_b64encode(image_bytes).decode()

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
                {"type": "text", "text": VISION_PROMPT},
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
            if isinstance(i, dict) and "name" in i and "quantity_g" in i
        ]
    except json.JSONDecodeError:
        return []
