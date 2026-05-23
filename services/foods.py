from __future__ import annotations

from typing import Optional

from services.profile import get_supabase_admin

_SELECT = "food_code, food_name, energy_kcal, protein_g, fat_g, carbs_g, fiber_g"


def lookup_food(name: str) -> Optional[dict]:
    """
    Find the best IFCT match for an AI-identified food name.
    Tries exact → partial food_name → partial local_name.
    Returns the foods row dict or None.
    """
    supabase = get_supabase_admin()
    name = name.strip()

    for query in [
        lambda: supabase.table("foods").select(_SELECT).ilike("food_name", name).limit(1).execute(),
        lambda: supabase.table("foods").select(_SELECT).ilike("food_name", f"%{name}%").limit(1).execute(),
        lambda: supabase.table("foods").select(_SELECT).ilike("local_name", f"%{name}%").limit(1).execute(),
    ]:
        resp = query()
        if resp.data:
            return resp.data[0]

    return None


def macros_for_quantity(food: dict, quantity_g: float) -> dict:
    """Scale per-100g IFCT values to the given quantity."""
    f = quantity_g / 100
    return {
        "calories":  round((food.get("energy_kcal") or 0) * f, 1),
        "protein_g": round((food.get("protein_g")   or 0) * f, 1),
        "fat_g":     round((food.get("fat_g")        or 0) * f, 1),
        "carbs_g":   round((food.get("carbs_g")      or 0) * f, 1),
        "fiber_g":   round((food.get("fiber_g")      or 0) * f, 1),
    }
