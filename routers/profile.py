from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from dependencies import get_current_user
from services.profile import get_profile, upsert_profile, calculate_targets

router = APIRouter()
jinja_env = Environment(loader=FileSystemLoader("templates"))

def render(name: str, context: dict, status_code: int = 200):
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(**context), status_code=status_code)


# ---------------------------------------------------------------------------
# Onboarding (shown once after signup)
# ---------------------------------------------------------------------------

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user=Depends(get_current_user)):
    """
    Show the onboarding form.
    If the user already has a profile (e.g. they navigated here again),
    redirect them to home instead.
    """
    profile = get_profile(str(user.id))
    if profile:
        return RedirectResponse(url="/home", status_code=303)

    return render("onboarding.html", {"request": request})


@router.post("/onboarding")
async def onboarding_submit(
    request: Request,
    user=Depends(get_current_user),
    name: str = Form(...),
    dob: str = Form(...),           # "YYYY-MM-DD" from date input
    sex: str = Form(...),           # "M" or "F"
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    activity_level: str = Form(...),
    goal: str = Form(...),
):
    """
    Save onboarding data, calculate targets, write profile row, redirect to home.
    """

    # Calculate age from date of birth
    from datetime import date
    dob_date = date.fromisoformat(dob)
    today = date.today()
    age = today.year - dob_date.year - (
        (today.month, today.day) < (dob_date.month, dob_date.day)
    )

    targets = calculate_targets(
        age=age,
        sex=sex,
        weight_kg=weight_kg,
        height_cm=height_cm,
        activity_level=activity_level,
        goal=goal,
    )

    profile_data = {
        "name": name,
        "dob": dob,
        "sex": sex,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "activity_level": activity_level,
        "goal": goal,
        **targets,
    }

    try:
        upsert_profile(str(user.id), profile_data)
    except Exception as e:
        return templates.TemplateResponse(
            "onboarding.html",
            {"request": request, "error": f"Could not save profile: {e}"},
            status_code=500,
        )

    return RedirectResponse(url="/home", status_code=303)


# ---------------------------------------------------------------------------
# Profile view / edit
# ---------------------------------------------------------------------------

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(get_current_user)):
    """Show the user's current profile and targets."""
    profile = get_profile(str(user.id))

    if not profile:
        return RedirectResponse(url="/onboarding", status_code=303)

    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "profile": profile, "user": user},
    )


# ---------------------------------------------------------------------------
# Home screen (placeholder for Week 4 — meals + totals)
# ---------------------------------------------------------------------------

@router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request, user=Depends(get_current_user)):
    """
    The main logged-in screen. Shows today's totals and meal list.
    For now: just shows a welcome message + the user's calorie target.
    Week 4 will fill this out with real meal data.
    """
    profile = get_profile(str(user.id))

    if not profile:
        return RedirectResponse(url="/onboarding", status_code=303)

    return render(
        "home.html",
        {"request": request, "profile": profile, "user_email": user.email},
    )