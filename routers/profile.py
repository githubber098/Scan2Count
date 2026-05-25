from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader

from dependencies import get_current_user
from services.profile import get_profile, get_supabase_admin, upsert_profile, calculate_targets

router = APIRouter()
jinja_env = Environment(loader=FileSystemLoader("templates"))


def render(name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(jinja_env.get_template(name).render(**context), status_code=status_code)


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user=Depends(get_current_user)):
    profile = get_profile(str(user.id))
    if profile:
        return RedirectResponse(url="/home", status_code=303)
    return render("onboarding.html", {"request": request})


@router.post("/onboarding")
async def onboarding_submit(
    request: Request,
    user=Depends(get_current_user),
    name: str = Form(...),
    dob: str = Form(...),
    sex: str = Form(...),
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    activity_level: str = Form(...),
    goal: str = Form(...),
):
    from datetime import date
    dob_date = date.fromisoformat(dob)
    today = date.today()
    age = today.year - dob_date.year - (
        (today.month, today.day) < (dob_date.month, dob_date.day)
    )

    targets = calculate_targets(
        age=age, sex=sex, weight_kg=weight_kg,
        height_cm=height_cm, activity_level=activity_level, goal=goal,
    )

    profile_data = {
        "name": name, "dob": dob, "sex": sex,
        "weight_kg": weight_kg, "height_cm": height_cm,
        "activity_level": activity_level, "goal": goal,
        **targets,
    }

    try:
        upsert_profile(str(user.id), profile_data)
    except Exception as e:
        return render("onboarding.html", {"request": request, "error": f"Could not save profile: {e}"}, 500)

    return RedirectResponse(url="/home", status_code=303)


# ---------------------------------------------------------------------------
# Profile view
# ---------------------------------------------------------------------------

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(get_current_user)):
    profile = get_profile(str(user.id))
    if not profile:
        return RedirectResponse(url="/onboarding", status_code=303)
    return render("profile.html", {"request": request, "profile": profile, "user": user})


# ---------------------------------------------------------------------------
# Home screen — today's totals + meal list
# ---------------------------------------------------------------------------

@router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request, user=Depends(get_current_user)):
    profile = get_profile(str(user.id))
    if not profile:
        return RedirectResponse(url="/onboarding", status_code=303)

    # Today's date range in UTC
    now         = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow    = today_start + timedelta(days=1)

    supabase = get_supabase_admin()
    meals_resp = (
        supabase.table("meal_logs")
        .select("*, meal_log_items(*)")
        .eq("user_id", str(user.id))
        .gte("logged_at", today_start.isoformat())
        .lt("logged_at", tomorrow.isoformat())
        .order("logged_at", desc=False)
        .execute()
    )
    meals = meals_resp.data or []

    # Annotate each meal with a readable time string
    for meal in meals:
        try:
            raw = meal.get("logged_at", "")
            dt  = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            meal["time_str"] = dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            meal["time_str"] = "—"

    # Sum today's totals
    totals = dict(calories=0.0, protein_g=0.0, carbs_g=0.0, fat_g=0.0, fiber_g=0.0)
    for meal in meals:
        totals["calories"]  += meal.get("total_calories",  0) or 0
        totals["protein_g"] += meal.get("total_protein_g", 0) or 0
        totals["carbs_g"]   += meal.get("total_carbs_g",   0) or 0
        totals["fat_g"]     += meal.get("total_fat_g",     0) or 0
        totals["fiber_g"]   += meal.get("total_fiber_g",   0) or 0
    totals = {k: round(v, 1) for k, v in totals.items()}

    # Progress percentages (capped at 100 for bar width)
    def pct(val: float, target) -> int:
        t = float(target or 0)
        return min(round(val / t * 100), 100) if t else 0

    cal_t  = profile.get("daily_calorie_target") or 2000
    prot_t = profile.get("daily_protein_g")      or 150
    carb_t = profile.get("daily_carbs_g")        or 250
    fat_t  = profile.get("daily_fat_g")          or 65

    return render("home.html", {
        "request":     request,
        "profile":     profile,
        "meals":       meals,
        "totals":      totals,
        "cal_pct":     pct(totals["calories"],  cal_t),
        "protein_pct": pct(totals["protein_g"], prot_t),
        "carbs_pct":   pct(totals["carbs_g"],   carb_t),
        "fat_pct":     pct(totals["fat_g"],     fat_t),
        "cal_target":  cal_t,
        "prot_target": prot_t,
        "carb_target": carb_t,
        "fat_target":  fat_t,
    })
