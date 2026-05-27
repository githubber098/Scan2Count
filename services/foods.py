from __future__ import annotations

from typing import Optional

from services.profile import get_supabase_admin

_SELECT = "id, item_name, quantity, unit, calories, protein, fat, carbohydrates, fiber"


def _parse_synonyms(raw) -> list[str]:
    """
    Parse the synonyms column, which may be stored as:
      - a TEXT comma-separated string: "Chapati, Chappati, Phulka"
      - a TEXT[] array: ["Chapati", "Chappati", "Phulka"]
      - a TEXT[] with one element containing a CSV string: ["Chapati, Chappati, Phulka"]
    Returns a clean list of individual synonym strings.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, list):
        result = []
        for item in raw:
            result.extend(_parse_synonyms(item))
        return result
    return []


def get_all_food_names() -> list[str]:
    """Return every item_name from indian_food_items (used to constrain vision prompt)."""
    supabase = get_supabase_admin()
    resp = supabase.table("indian_food_items").select("item_name").order("item_name").execute()
    return [row["item_name"] for row in (resp.data or [])]


def get_synonym_map() -> dict[str, str]:
    """
    Return {lowercase_synonym: canonical_item_name}.
    Synonyms may be stored as a comma-separated TEXT string or a TEXT[] array —
    _parse_synonyms handles both.
    """
    supabase = get_supabase_admin()
    resp = supabase.table("indian_food_items").select("item_name, synonyms").execute()
    mapping: dict[str, str] = {}
    for row in (resp.data or []):
        for syn in _parse_synonyms(row.get("synonyms")):
            mapping[syn.lower()] = row["item_name"]
    return mapping


def get_fuzzy_targets() -> dict[str, str]:
    """
    Return {name_or_synonym: canonical_item_name} for use as fuzzy matching targets.
    Includes every item_name AND every synonym so that misspellings like "Chappatti"
    can match the synonym "Chapati" (score ~96) rather than only item_names.
    """
    supabase = get_supabase_admin()
    resp = supabase.table("indian_food_items").select("item_name, synonyms").execute()
    targets: dict[str, str] = {}
    for row in (resp.data or []):
        canonical = row["item_name"]
        targets[canonical] = canonical
        for syn in _parse_synonyms(row.get("synonyms")):
            targets[syn] = canonical
    return targets


def lookup_food(name: str) -> Optional[dict]:
    """
    Find a row in indian_food_items by exact case-insensitive item_name match.
    Synonym matching is NOT done here — call get_synonym_map() before this
    and resolve to the canonical name first.
    Partial substring matching is intentionally excluded to avoid false positives
    (e.g. "chips" matching "Fish and Chips", "milk" matching "Kesar Milk").
    """
    supabase = get_supabase_admin()
    name = name.strip()

    resp = supabase.table("indian_food_items").select(_SELECT).ilike("item_name", name).limit(1).execute()
    if resp.data:
        return resp.data[0]

    return None


def macros_for_quantity(food: dict, user_quantity: float) -> dict:
    """Scale per-serving macros to the user's quantity. base is food['quantity']."""
    base_qty = float(food.get("quantity") or 1)
    factor = user_quantity / base_qty if base_qty else 0
    return {
        "calories":  round((food.get("calories")      or 0) * factor, 1),
        "protein_g": round((food.get("protein")       or 0) * factor, 1),
        "fat_g":     round((food.get("fat")            or 0) * factor, 1),
        "carbs_g":   round((food.get("carbohydrates")  or 0) * factor, 1),
        "fiber_g":   round((food.get("fiber")          or 0) * factor, 1),
    }
