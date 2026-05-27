from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader

from dependencies import get_current_user
from services.foods import get_all_food_names, get_fuzzy_targets, get_synonym_map, lookup_food, macros_for_quantity
from services.fuzzy_match import fuzzy_match_food_name
from services.profile import get_supabase_admin
from services.vision import analyze_meal_photo

router = APIRouter()
jinja_env = Environment(loader=FileSystemLoader("templates"))

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def render(name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(jinja_env.get_template(name).render(**context), status_code=status_code)


def _build_line_item(ai_name: str, food: dict | None, user_qty: float, ai_unit: str) -> dict:
    """Shared helper used by both photo and manual flows."""
    if food:
        base_qty = float(food["quantity"] or 1)
        return {
            "ai_name":           ai_name,
            "food_name":         food["item_name"],
            "quantity":          user_qty,
            "unit":              food["unit"],
            "base_quantity":     base_qty,
            "calories_per_base": float(food.get("calories")      or 0),
            "protein_per_base":  float(food.get("protein")       or 0),
            "fat_per_base":      float(food.get("fat")            or 0),
            "carbs_per_base":    float(food.get("carbohydrates")  or 0),
            "fiber_per_base":    float(food.get("fiber")          or 0),
            **macros_for_quantity(food, user_qty),
            "matched": True,
        }
    else:
        return {
            "ai_name":           ai_name,
            "food_name":         ai_name,
            "quantity":          user_qty,
            "unit":              ai_unit,
            "base_quantity":     user_qty,   # factor = 1 so macros stay 0
            "calories_per_base": 0, "protein_per_base": 0,
            "fat_per_base":      0, "carbs_per_base":   0, "fiber_per_base": 0,
            "calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0, "fiber_g": 0,
            "matched": False,
        }


# ---------------------------------------------------------------------------
# GET /log — upload / manual entry page
# ---------------------------------------------------------------------------

@router.get("/log", response_class=HTMLResponse)
async def log_page(request: Request, user=Depends(get_current_user)):
    return render("log.html", {"request": request, "user": user.email})


# ---------------------------------------------------------------------------
# POST /log — analyse photo → confirm screen
# ---------------------------------------------------------------------------

@router.post("/log", response_class=HTMLResponse)
async def log_submit(
    request: Request,
    user=Depends(get_current_user),
    photo: UploadFile = File(...),
):
    ctx = {"request": request, "user": user.email}

    if photo.content_type not in ALLOWED_TYPES:
        return render("log.html", {**ctx, "error": "Please upload a JPEG, PNG, or WebP image."}, 400)

    image_bytes = await photo.read()
    if len(image_bytes) > MAX_BYTES:
        return render("log.html", {**ctx, "error": "Image too large (max 5 MB). Please compress it first."}, 400)

    food_names = get_all_food_names()

    try:
        ai_items = analyze_meal_photo(image_bytes, photo.content_type, food_names)
    except Exception:
        return render("log.html", {**ctx, "error": "Could not reach the AI service. Please try again."}, 502)

    if not ai_items:
        return render(
            "log.html",
            {**ctx, "error": "No food detected in the photo. Try a clearer, closer shot."},
            422,
        )

    line_items = []
    for ai in ai_items:
        food = lookup_food(ai["name"])
        qty  = float(ai.get("quantity") or 1)
        unit = ai.get("unit", "serving")
        line_items.append(_build_line_item(ai["name"], food, qty, unit))

    return render("log_confirm.html", {"request": request, "user": user.email, "items": line_items})


# ---------------------------------------------------------------------------
# POST /log/manual — text entry → confirm screen
# ---------------------------------------------------------------------------

@router.post("/log/manual", response_class=HTMLResponse)
async def manual_submit(
    request: Request,
    user=Depends(get_current_user),
    items_json: str = Form(...),
):
    ctx = {"request": request, "user": user.email}

    try:
        raw_items = json.loads(items_json)  # [{name, servings}]
    except (json.JSONDecodeError, ValueError):
        return render("log.html", {**ctx, "error": "Invalid input. Please try again."}, 400)

    if not raw_items:
        return render("log.html", {**ctx, "error": "No items entered."}, 400)

    synonym_map       = get_synonym_map()    # {lowercase_synonym: canonical_item_name}
    fuzzy_target_map  = get_fuzzy_targets()  # {item_name_or_synonym: canonical_item_name}

    line_items = []
    for item in raw_items:
        description = str(item.get("name", "")).strip()
        servings    = float(item.get("servings") or 1)
        if not description:
            continue

        # 1. Exact synonym match (case-insensitive Python dict lookup)
        canonical = synonym_map.get(description.lower())
        food = lookup_food(canonical) if canonical else None

        # 2. Exact / partial ilike on item_name
        if not food:
            food = lookup_food(description)

        # 3. Fuzzy against item_names AND synonyms — catches misspellings of synonyms
        if not food:
            fuzzy_key = fuzzy_match_food_name(description, list(fuzzy_target_map.keys()))
            if fuzzy_key:
                canonical = fuzzy_target_map.get(fuzzy_key, fuzzy_key)
                food = lookup_food(canonical)

        if food:
            base_qty = float(food["quantity"] or 1)
            user_qty = servings * base_qty   # e.g. 2 servings × 1 piece = 2 pieces
        else:
            user_qty = servings              # unmatched: store as-is

        line_items.append(_build_line_item(description, food, user_qty, "serving"))

    if not line_items:
        return render("log.html", {**ctx, "error": "None of those items were recognised. Check the spelling."}, 400)

    return render("log_confirm.html", {"request": request, "user": user.email, "items": line_items})


# ---------------------------------------------------------------------------
# POST /log/save — persist to DB, redirect home
# ---------------------------------------------------------------------------

@router.post("/log/save")
async def log_save(
    request: Request,
    user=Depends(get_current_user),
    items_json: str = Form(...),
):
    try:
        items = json.loads(items_json)
    except (json.JSONDecodeError, ValueError):
        return RedirectResponse(url="/log", status_code=303)

    if not items:
        return RedirectResponse(url="/home", status_code=303)

    # Recalculate macros server-side (never trust client math)
    final_items = []
    for item in items:
        qty      = float(item.get("quantity")         or 0)
        base_qty = float(item.get("base_quantity")    or 1)
        factor   = qty / base_qty if base_qty else 0
        e   = float(item.get("calories_per_base")  or 0)
        p   = float(item.get("protein_per_base")   or 0)
        fat = float(item.get("fat_per_base")        or 0)
        c   = float(item.get("carbs_per_base")      or 0)
        fi  = float(item.get("fiber_per_base")      or 0)

        final_items.append({
            "food_name": item.get("food_name", ""),
            "quantity_g": qty,
            "calories":  round(e   * factor, 1),
            "protein_g": round(p   * factor, 1),
            "fat_g":     round(fat * factor, 1),
            "carbs_g":   round(c   * factor, 1),
            "fiber_g":   round(fi  * factor, 1),
        })

    supabase = get_supabase_admin()

    log_resp = (
        supabase.table("meal_logs")
        .insert({
            "user_id":         str(user.id),
            "total_calories":  round(sum(i["calories"]  for i in final_items), 1),
            "total_protein_g": round(sum(i["protein_g"] for i in final_items), 1),
            "total_fat_g":     round(sum(i["fat_g"]     for i in final_items), 1),
            "total_carbs_g":   round(sum(i["carbs_g"]   for i in final_items), 1),
            "total_fiber_g":   round(sum(i["fiber_g"]   for i in final_items), 1),
        })
        .execute()
    )

    meal_log_id = log_resp.data[0]["id"]

    supabase.table("meal_log_items").insert([
        {"meal_log_id": meal_log_id, **item}
        for item in final_items
    ]).execute()

    return RedirectResponse(url="/home", status_code=303)
