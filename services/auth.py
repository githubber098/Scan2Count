import os
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError


def get_supabase() -> Client:
    """
    Create and return a Supabase client.
    Called fresh each time so we don't hold a stale connection.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def sign_up(email: str, password: str) -> dict:
    """
    Register a new user with email + password.
    Returns {"user": ..., "session": ...} on success.
    Raises AuthApiError on failure (e.g. email already registered).
    """
    supabase = get_supabase()
    response = supabase.auth.sign_up({"email": email, "password": password})

    if response.user is None:
        raise AuthApiError("Sign up failed — no user returned.", 400, "signup_failed")

    return {
        "user": response.user,
        "session": response.session,
    }


def sign_in(email: str, password: str) -> dict:
    """
    Sign in an existing user.
    Returns {"user": ..., "session": ...} on success.
    Raises AuthApiError on bad credentials.
    """
    supabase = get_supabase()
    response = supabase.auth.sign_in_with_password(
        {"email": email, "password": password}
    )

    return {
        "user": response.user,
        "session": response.session,
    }


def get_user_from_token(access_token: str) -> dict | None:
    """
    Validate a JWT access token and return the user dict, or None if invalid.
    Used by the get_current_user dependency on every protected route.
    """
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(access_token)
        return response.user
    except Exception:
        return None