from __future__ import annotations

import logging

from rapidfuzz import fuzz, process, utils

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 80


def fuzzy_match_food_name(
    description: str,
    food_names: list[str],
    threshold: int = _DEFAULT_THRESHOLD,
) -> str | None:
    """
    Algorithmically match a free-text food description to the closest name in
    food_names using RapidFuzz WRatio scoring.

    Returns the matched name if score >= threshold, otherwise None.
    Used as a fallback when the Groq API is unavailable or returns None.
    """
    if not food_names or not description:
        return None

    match = process.extractOne(
        description,
        food_names,
        scorer=fuzz.WRatio,
        processor=utils.default_process,  # lowercases + strips both sides before scoring
        score_cutoff=threshold,
    )
    if match is None:
        return None

    matched_name, score, _ = match
    logger.debug("fuzzy match: '%s' → '%s' (score=%d)", description, matched_name, score)
    return matched_name
