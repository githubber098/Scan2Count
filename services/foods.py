from __future__ import annotations

from typing import Optional

from services.profile import get_supabase_admin

_SELECT = "id, item_name, quantity, unit, calories, protein, fat, carbohydrates, fiber"


def get_all_food_names() -> list[str]:
    """Return every item_name from indian_food_items (used to constrain vision prompt)."""
    supabase = get_supabase_admin()
    resp = supabase.table("indian_food_items").select("item_name").order("item_name").execute()
    return [row["item_name"] for row in (resp.data or [])]


def lookup_food(name: str) -> Optional[dict]:
    """
    Find the best match in indian_food_items for a food name.
    Tries exact → partial match on item_name.
    Returns the row dict or None.
    """
    supabase = get_supabase_admin()
    name = name.strip()

    for query in [
        lambda: supabase.table("indian_food_items").select(_SELECT).ilike("item_name", name).limit(1).execute(),
        lambda: supabase.table("indian_food_items").select(_SELECT).ilike("item_name", f"%{name}%").limit(1).execute(),
    ]:
        resp = query()
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
