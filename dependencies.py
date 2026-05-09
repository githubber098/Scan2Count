from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from services.auth import get_user_from_token


def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency. Extracts the JWT from the 'access_token' cookie,
    validates it with Supabase, and returns the user object.

    If the token is missing or invalid, redirects to /login.

    Usage in a route:
        @router.get("/dashboard")
        async def dashboard(user = Depends(get_current_user)):
            # user is guaranteed to be valid here
    """
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=307, headers={"Location": "/login"})

    user = get_user_from_token(token)

    if user is None:
        # Token exists but is expired or invalid — clear it and redirect
        response = RedirectResponse(url="/login", status_code=307)
        response.delete_cookie("access_token")
        raise HTTPException(status_code=307, headers={"Location": "/login"})

    return user


def get_optional_user(request: Request) -> dict | None:
    """
    Like get_current_user but doesn't redirect — returns None if not logged in.
    Use this on pages that should work for both logged-in and logged-out users
    (e.g. the landing page, which shows 'Go to dashboard' if logged in).
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    return get_user_from_token(token)