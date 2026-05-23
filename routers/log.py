from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader

from dependencies import get_current_user
from services.foods import lookup_food, macros_for_quantity
from services.profile import get_supabase_admin
from services.vision import analyze_meal_photo

router = APIRouter()
jinja_env = Environment(loader=FileSystemLoader("templates"))

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def render(name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(jinja_env.get_template(name).render(**context), status_code=status_code)


# ---------------------------------------------------------------------------
# GET /log — upload form
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

    try:
        ai_items = analyze_meal_photo(image_bytes, photo.content_type)
    except Exception:
        return render("log.html", {**ctx, "error": "Could not reach the AI service. Please try again."}, 502)

    if not ai_items:
        return render(
            "log.html",
            {**ctx, "error": "No food detected in the photo. Try a clearer, closer shot."},
            422,
        )

    # Match each AI item against IFCT
    line_items = []
    for ai in ai_items:
        food = lookup_food(ai["name"])
        qty = float(ai["quantity_g"])

        if food:
            line_items.append({
                "ai_name": ai["name"],
                "food_code": food["food_code"],
                "food_name": food["food_name"],
                "quantity_g": qty,
                "energy_kcal_per100g": food["energy_kcal"] or 0,
                "protein_g_per100g":   food["protein_g"]   or 0,
                "fat_g_per100g":       food["fat_g"]        or 0,
                "carbs_g_per100g":     food["carbs_g"]      or 0,
                "fiber_g_per100g":     food["fiber_g"]      or 0,
                **macros_for_quantity(food, qty),
                "matched": True,
            })
        else:
            line_items.append({
                "ai_name":  ai["name"],
                "food_code": None,
                "food_name": ai["name"],
                "quantity_g": qty,
                "energy_kcal_per100g": 0, "protein_g_per100g": 0,
                "fat_g_per100g": 0, "carbs_g_per100g": 0, "fiber_g_per100g": 0,
                "calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0, "fiber_g": 0,
                "matched": False,
            })

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

    # Recalculate macros server-side from submitted quantities (never trust client maths)
    final_items = []
    for item in items:
        qty = float(item.get("quantity_g") or 0)
        factor = qty / 100
        e   = float(item.get("energy_kcal_per100g") or 0)
        p   = float(item.get("protein_g_per100g")   or 0)
        fat = float(item.get("fat_g_per100g")        or 0)
        c   = float(item.get("carbs_g_per100g")      or 0)
        fi  = float(item.get("fiber_g_per100g")      or 0)

        final_items.append({
            "food_code": item.get("food_code"),
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
