"""
Integration tests for authentication routes.

Routes covered: GET/POST /signup, GET/POST /login, POST /logout, POST /auth/session

All Supabase auth calls are mocked — no real network traffic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from gotrue.errors import AuthApiError

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_session(token: str = "fake-access-token") -> MagicMock:
    session = MagicMock()
    session.access_token = token
    return session


def _mock_sign_up_result(*, with_session: bool = True) -> dict:
    user = MagicMock()
    user.email = "new@sandbox.com"
    return {
        "user":    user,
        "session": _mock_session() if with_session else None,
    }


def _mock_sign_in_result() -> dict:
    user = MagicMock()
    user.email = "existing@sandbox.com"
    return {"user": user, "session": _mock_session()}


# ── GET pages ─────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSignupPage:

    def test_get_returns_200(self, anon_client):
        response = anon_client.get("/signup")
        assert response.status_code == 200
        assert b"<form" in response.content

    def test_get_contains_password_field(self, anon_client):
        response = anon_client.get("/signup")
        assert b"password" in response.content.lower()


@pytest.mark.integration
class TestLoginPage:

    def test_get_returns_200(self, anon_client):
        response = anon_client.get("/login")
        assert response.status_code == 200

    def test_get_contains_login_form(self, anon_client):
        response = anon_client.get("/login")
        assert b"<form" in response.content


# ── POST /signup ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSignupSubmit:

    def test_password_mismatch_returns_400(self, anon_client):
        response = anon_client.post("/signup", data={
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "different456",
        })
        assert response.status_code == 400
        assert b"do not match" in response.content.lower()

    def test_password_too_short_returns_400(self, anon_client):
        response = anon_client.post("/signup", data={
            "email": "test@example.com",
            "password": "short",
            "confirm_password": "short",
        })
        assert response.status_code == 400
        assert b"8 characters" in response.content

    def test_valid_signup_with_session_redirects_to_onboarding(self, anon_client):
        with patch("routers.auth.sign_up", return_value=_mock_sign_up_result(with_session=True)):
            response = anon_client.post("/signup", data={
                "email": "new@sandbox.com",
                "password": "securepass",
                "confirm_password": "securepass",
            })
        assert response.status_code == 303
        assert response.headers["location"] == "/onboarding"

    def test_valid_signup_sets_access_token_cookie(self, anon_client):
        with patch("routers.auth.sign_up", return_value=_mock_sign_up_result(with_session=True)):
            response = anon_client.post("/signup", data={
                "email": "new@sandbox.com",
                "password": "securepass",
                "confirm_password": "securepass",
            })
        assert "access_token" in response.cookies

    def test_email_confirmation_required_returns_200_with_info(self, anon_client):
        """When Supabase requires email confirmation, session is None."""
        with patch("routers.auth.sign_up", return_value=_mock_sign_up_result(with_session=False)):
            response = anon_client.post("/signup", data={
                "email": "new@sandbox.com",
                "password": "securepass",
                "confirm_password": "securepass",
            })
        assert response.status_code == 200
        assert b"check your email" in response.content.lower()

    def test_duplicate_email_returns_400_with_error(self, anon_client):
        err = AuthApiError("User already registered", 422, {})
        with patch("routers.auth.sign_up", side_effect=err):
            response = anon_client.post("/signup", data={
                "email": "existing@sandbox.com",
                "password": "securepass",
                "confirm_password": "securepass",
            })
        assert response.status_code == 400


# ── POST /login ───────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLoginSubmit:

    def test_invalid_credentials_returns_401(self, anon_client):
        err = AuthApiError("Invalid login credentials", 400, {})
        with patch("routers.auth.sign_in", side_effect=err):
            response = anon_client.post("/login", data={
                "email": "test@example.com",
                "password": "wrongpass",
            })
        assert response.status_code == 401
        assert b"invalid email or password" in response.content.lower()

    def test_valid_login_redirects_to_home(self, anon_client):
        with patch("routers.auth.sign_in", return_value=_mock_sign_in_result()):
            response = anon_client.post("/login", data={
                "email": "existing@sandbox.com",
                "password": "correctpass",
            })
        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_valid_login_sets_cookie(self, anon_client):
        with patch("routers.auth.sign_in", return_value=_mock_sign_in_result()):
            response = anon_client.post("/login", data={
                "email": "existing@sandbox.com",
                "password": "correctpass",
            })
        assert "access_token" in response.cookies


# ── POST /logout ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLogout:

    def test_logout_redirects_to_root(self, anon_client):
        response = anon_client.post("/logout")
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_logout_clears_access_token_cookie(self, anon_client):
        # Set a cookie first, then logout
        anon_client.cookies.set("access_token", "some-token")
        response = anon_client.post("/logout")
        # Cookie should be deleted (max-age=0 or absent)
        assert response.cookies.get("access_token") != "some-token"


# ── POST /auth/session ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestAuthSession:

    def test_signup_type_redirects_to_onboarding(self, anon_client):
        response = anon_client.post("/auth/session", data={
            "access_token": "some-jwt",
            "type": "signup",
        })
        assert response.status_code == 303
        assert response.headers["location"] == "/onboarding"

    def test_other_type_redirects_to_home(self, anon_client):
        response = anon_client.post("/auth/session", data={
            "access_token": "some-jwt",
            "type": "login",
        })
        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_session_sets_cookie(self, anon_client):
        response = anon_client.post("/auth/session", data={
            "access_token": "some-jwt",
            "type": "signup",
        })
        assert "access_token" in response.cookies
