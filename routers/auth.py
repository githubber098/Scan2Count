from fastapi import APIRouter, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase_auth.errors import AuthApiError
from jinja2 import Environment, FileSystemLoader

from services.auth import sign_up, sign_in

router = APIRouter()
jinja_env = Environment(loader=FileSystemLoader("templates"))

def render(name: str, context: dict, status_code: int = 200):
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(**context), status_code=status_code)

# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Render the signup form."""
    return render("auth/signup.html", {"request": request})


@router.post("/signup")
async def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    """
    Handle signup form submission.
    On success: set JWT cookie, redirect to onboarding.
    On failure: re-render signup form with error message.
    """

    # Client-side validation would catch this too, but always validate server-side
    if password != confirm_password:
        return render(
            "auth/signup.html",
            {"request": request, "error": "Passwords do not match."},
            status_code=400,
        )

    if len(password) < 8:
        return render(
            "auth/signup.html",
            {"request": request, "error": "Password must be at least 8 characters."},
            status_code=400,
        )

    try:
        result = sign_up(email, password)
    except AuthApiError as e:
        return render(
            "auth/signup.html",
            {"request": request, "error": str(e.message)},
            status_code=400,
        )
    except Exception:
        return render(
            "auth/signup.html",
            {"request": request, "error": "Something went wrong. Please try again."},
            status_code=500,
        )

    if result["session"] is None:
        # Email confirmation required — tell the user to check their inbox
        return render(
            "auth/signup.html",
            {"request": request, "info": "Check your email and click the confirmation link to activate your account."},
            status_code=200,
        )

    response = RedirectResponse(url="/onboarding", status_code=303)
    response.set_cookie(
        key="access_token",
        value=result["session"].access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login form."""
    return render("auth/login.html", {"request": request})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """
    Handle login form submission.
    On success: set JWT cookie, redirect to home.
    On failure: re-render login form with error.
    """
    try:
        result = sign_in(email, password)
    except AuthApiError:
        return render(
            "auth/login.html",
            {"request": request, "error": "Invalid email or password."},
            status_code=401,
        )
    except Exception:
        return render(
            "auth/login.html",
            {"request": request, "error": "Something went wrong. Please try again."},
            status_code=500,
        )

    response = RedirectResponse(url="/home", status_code=303)
    response.set_cookie(
        key="access_token",
        value=result["session"].access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response

@router.post("/auth/session")
async def set_session(access_token: str = Body(..., embed=True), type: str = Body(..., embed=True)):
    response = RedirectResponse(url="/onboarding" if type == "signup" else "/home", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response

# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout():
    """Clear the auth cookie and redirect to landing page."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response