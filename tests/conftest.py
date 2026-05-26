"""
Shared fixtures for the Scan2Count test suite.

Env loading order:
  1. .env.test   (sandbox credentials — gitignored, never committed)
  2. Fallback dummy values so unit tests work without any .env file
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# ── 1. Load sandbox env vars BEFORE importing the app ────────────────────────
_env_test = Path(__file__).parent / ".env.test"
if _env_test.exists():
    load_dotenv(_env_test, override=True)

# Fall back to harmless dummy values so unit tests run with no .env file at all.
os.environ.setdefault("SUPABASE_URL",              "https://sandbox.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY",         "sandbox-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "sandbox-service-role-key")
os.environ.setdefault("ANTHROPIC_API_KEY",         "test-anthropic-key")
os.environ.setdefault("GROQ_API_KEY",              "test-groq-key")
os.environ.setdefault("ENVIRONMENT",               "test")

# ── 2. Import app after env is ready ─────────────────────────────────────────
from dependencies import get_current_user, get_optional_user  # noqa: E402
from main import app  # noqa: E402

# ── Canonical fake data ───────────────────────────────────────────────────────

FAKE_USER_ID    = "test-user-uuid-00000000-0000-0000-0000-000000000001"
FAKE_USER_EMAIL = "test@sandbox.scan2count.com"

FAKE_PROFILE = {
    "user_id":              FAKE_USER_ID,
    "name":                 "Test User",
    "dob":                  "1995-01-15",
    "sex":                  "M",
    "weight_kg":            75.0,
    "height_cm":            178.0,
    "activity_level":       "moderate",
    "goal":                 "maintain",
    "daily_calorie_target": 2600,
    "daily_protein_g":      150,
    "daily_carbs_g":        300,
    "daily_fat_g":          72,
    "daily_fiber_g":        30,
}

FAKE_FOOD = {
    "id":              1,
    "item_name":       "Roti (Plain Wheat)",
    "quantity":        1.0,
    "unit":            "piece",
    "calories":        84.0,
    "protein":         4.1,
    "fat":             0.8,
    "carbohydrates":   15.2,
    "fiber":           2.4,
}

FAKE_MEALS = [
    {
        "id":              "meal-uuid-001",
        "user_id":         FAKE_USER_ID,
        "logged_at":       "2026-05-26T08:30:00+00:00",
        "total_calories":  350.0,
        "total_protein_g": 25.0,
        "total_carbs_g":   45.0,
        "total_fat_g":     8.0,
        "total_fiber_g":   6.0,
        "meal_log_items": [
            {
                "id":         "item-uuid-001",
                "meal_log_id":"meal-uuid-001",
                "food_name":  "Roti (Plain Wheat)",
                "quantity_g": 2.0,
                "calories":   168.0,
                "protein_g":  8.2,
                "fat_g":      1.6,
                "carbs_g":    30.4,
                "fiber_g":    4.8,
            }
        ],
    }
]

# A minimal valid multipart image upload (bytes don't matter — vision is mocked)
FAKE_IMAGE_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16  # JPEG magic + padding

# Serialised items_json as sent by the confirm form to POST /log/save
FAKE_ITEMS_JSON = json.dumps([
    {
        "food_name":         "Roti (Plain Wheat)",
        "quantity":          2.0,
        "unit":              "piece",
        "base_quantity":     1.0,
        "calories_per_base": 84.0,
        "protein_per_base":  4.1,
        "fat_per_base":      0.8,
        "carbs_per_base":    15.2,
        "fiber_per_base":    2.4,
    }
])


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_user() -> MagicMock:
    """A mock Supabase user object (as returned by get_current_user)."""
    user = MagicMock()
    user.id    = FAKE_USER_ID
    user.email = FAKE_USER_EMAIL
    return user


@pytest.fixture()
def auth_client(fake_user) -> TestClient:
    """
    TestClient with get_current_user overridden so every protected route
    receives fake_user without touching Supabase Auth.
    """
    def _override():
        return fake_user

    app.dependency_overrides[get_current_user] = _override
    client = TestClient(app, follow_redirects=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def anon_client() -> TestClient:
    """TestClient with no auth override — simulates a logged-out visitor."""
    client = TestClient(app, follow_redirects=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_supabase(mocker):
    """
    Returns a MagicMock Supabase client whose full method chain resolves
    cleanly.  Patch the specific import path in your test, e.g.:
        mocker.patch("routers.profile.get_supabase_admin", return_value=mock_supabase)
    """
    mock = MagicMock()
    # Default empty response for any .execute() call
    mock.table.return_value.select.return_value \
        .eq.return_value.gte.return_value.lt.return_value \
        .order.return_value.execute.return_value.data = []
    return mock


def make_supabase_insert_mock(returned_row: dict) -> MagicMock:
    """
    Helper: returns a MagicMock whose .table().insert().execute().data
    contains [returned_row].  Used for testing write routes.
    """
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value.data = [returned_row]
    return mock
