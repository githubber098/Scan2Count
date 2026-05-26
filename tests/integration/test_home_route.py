"""
Integration tests for the home screen and onboarding routes.

Routes covered: GET /home, GET /onboarding, POST /onboarding

External dependencies (Supabase) are mocked.
Auth is bypassed via the auth_client fixture (dependency override).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FAKE_PROFILE, FAKE_MEALS, FAKE_USER_ID


# ── /home — unauthenticated ───────────────────────────────────────────────────

@pytest.mark.integration
class TestHomeUnauthenticated:

    def test_redirects_to_login(self, anon_client):
        response = anon_client.get("/home")
        assert response.status_code == 307
        assert "/login" in response.headers["location"]


# ── /home — authenticated, various states ────────────────────────────────────

@pytest.mark.integration
class TestHomeAuthenticated:

    def test_no_profile_redirects_to_onboarding(self, auth_client):
        with patch("routers.profile.get_profile", return_value=None):
            response = auth_client.get("/home")
        assert response.status_code == 303
        assert response.headers["location"] == "/onboarding"

    def test_with_profile_no_meals_returns_200(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = []

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        assert response.status_code == 200

    def test_no_meals_shows_empty_state_message(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = []

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        assert b"No meals logged" in response.content

    def test_with_meals_shows_food_names(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = FAKE_MEALS

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        assert response.status_code == 200
        assert b"Roti (Plain Wheat)" in response.content

    def test_with_meals_shows_calorie_total(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = FAKE_MEALS

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        # FAKE_MEALS has total_calories=350
        assert b"350" in response.content

    def test_shows_user_first_name(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = []

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        assert b"Test User" in response.content

    def test_shows_calorie_target_from_profile(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = []

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        # FAKE_PROFILE has daily_calorie_target=2600
        assert b"2600" in response.content

    def test_navbar_shows_profile_and_logout_not_login(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.gte.return_value.lt.return_value \
            .order.return_value.execute.return_value.data = []

        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE), \
             patch("routers.profile.get_supabase_admin", return_value=mock_sb):
            response = auth_client.get("/home")

        html = response.content
        assert b"Log out" in html
        assert b"Profile" in html
        # "Log in" link should NOT appear when authenticated
        assert b'href="/login"' not in html


# ── /onboarding ───────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestOnboarding:

    def test_unauthenticated_redirects_to_login(self, anon_client):
        response = anon_client.get("/onboarding")
        assert response.status_code == 307
        assert "/login" in response.headers["location"]

    def test_authenticated_no_profile_shows_form(self, auth_client):
        with patch("routers.profile.get_profile", return_value=None):
            response = auth_client.get("/onboarding")
        assert response.status_code == 200
        assert b"<form" in response.content

    def test_authenticated_with_profile_redirects_to_home(self, auth_client):
        with patch("routers.profile.get_profile", return_value=FAKE_PROFILE):
            response = auth_client.get("/onboarding")
        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_post_saves_profile_and_redirects_home(self, auth_client):
        with patch("routers.profile.get_profile", return_value=None), \
             patch("routers.profile.upsert_profile", return_value=FAKE_PROFILE):
            response = auth_client.post("/onboarding", data={
                "name":           "Test User",
                "dob":            "1995-01-15",
                "sex":            "M",
                "weight_kg":      "75",
                "height_cm":      "178",
                "activity_level": "moderate",
                "goal":           "maintain",
            })
        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_post_calls_upsert_with_calculated_targets(self, auth_client):
        """upsert_profile should receive calorie targets derived from the form values."""
        with patch("routers.profile.get_profile", return_value=None), \
             patch("routers.profile.upsert_profile", return_value=FAKE_PROFILE) as mock_upsert:
            auth_client.post("/onboarding", data={
                "name": "Test", "dob": "1995-01-15", "sex": "M",
                "weight_kg": "75", "height_cm": "178",
                "activity_level": "moderate", "goal": "maintain",
            })

        call_kwargs = mock_upsert.call_args[0][1]  # second positional arg is data dict
        assert "daily_calorie_target" in call_kwargs
        assert call_kwargs["daily_calorie_target"] > 0
