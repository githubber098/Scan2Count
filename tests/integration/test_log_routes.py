"""
Integration tests for the meal-logging routes.

Routes covered:
  GET  /log
  POST /log        (photo analysis → confirm screen)
  POST /log/manual (text entry → Groq match → confirm screen)
  POST /log/save   (confirm screen → persist to DB → redirect)

All external services (Claude vision, Groq, Supabase) are mocked.
Auth is bypassed via auth_client (dependency override).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FAKE_FOOD, FAKE_IMAGE_BYTES, FAKE_ITEMS_JSON

# Convenience: items_json for /log/save that produces a valid meal
SAMPLE_ITEMS = [
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
]
SAMPLE_ITEMS_JSON = json.dumps(SAMPLE_ITEMS)


# ── GET /log ──────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLogPage:

    def test_unauthenticated_redirects_to_login(self, anon_client):
        response = anon_client.get("/log")
        assert response.status_code == 307
        assert "/login" in response.headers["location"]

    def test_authenticated_returns_200(self, auth_client):
        response = auth_client.get("/log")
        assert response.status_code == 200

    def test_page_contains_photo_tab(self, auth_client):
        response = auth_client.get("/log")
        assert b"Scan Photo" in response.content

    def test_page_contains_manual_tab(self, auth_client):
        response = auth_client.get("/log")
        assert b"Enter Manually" in response.content


# ── POST /log (photo) ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLogPhotoSubmit:

    def test_unauthenticated_redirects(self, anon_client):
        response = anon_client.post(
            "/log",
            files={"photo": ("test.jpg", FAKE_IMAGE_BYTES, "image/jpeg")},
        )
        assert response.status_code == 307

    def test_invalid_content_type_returns_400(self, auth_client):
        response = auth_client.post(
            "/log",
            files={"photo": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 400
        assert b"JPEG" in response.content or b"PNG" in response.content

    def test_oversized_image_returns_400(self, auth_client):
        big_image = b"\xff\xd8" + b"x" * (5 * 1024 * 1024 + 1)
        response = auth_client.post(
            "/log",
            files={"photo": ("big.jpg", big_image, "image/jpeg")},
        )
        assert response.status_code == 400
        assert b"5 MB" in response.content

    def test_no_food_detected_returns_422(self, auth_client):
        with patch("routers.log.get_all_food_names", return_value=["Roti (Plain Wheat)"]), \
             patch("routers.log.analyze_meal_photo", return_value=[]):
            response = auth_client.post(
                "/log",
                files={"photo": ("test.jpg", FAKE_IMAGE_BYTES, "image/jpeg")},
            )
        assert response.status_code == 422
        assert b"No food detected" in response.content

    def test_ai_service_failure_returns_502(self, auth_client):
        with patch("routers.log.get_all_food_names", return_value=[]), \
             patch("routers.log.analyze_meal_photo", side_effect=Exception("timeout")):
            response = auth_client.post(
                "/log",
                files={"photo": ("test.jpg", FAKE_IMAGE_BYTES, "image/jpeg")},
            )
        assert response.status_code == 502

    def test_food_detected_renders_confirm_screen(self, auth_client):
        with patch("routers.log.get_all_food_names", return_value=["Roti (Plain Wheat)"]), \
             patch("routers.log.analyze_meal_photo", return_value=[
                 {"name": "Roti (Plain Wheat)", "quantity": 2, "unit": "piece"}
             ]), \
             patch("routers.log.lookup_food", return_value=FAKE_FOOD):
            response = auth_client.post(
                "/log",
                files={"photo": ("test.jpg", FAKE_IMAGE_BYTES, "image/jpeg")},
            )
        assert response.status_code == 200
        assert b"Confirm meal" in response.content

    def test_food_detected_shows_matched_food_name(self, auth_client):
        with patch("routers.log.get_all_food_names", return_value=["Roti (Plain Wheat)"]), \
             patch("routers.log.analyze_meal_photo", return_value=[
                 {"name": "Roti (Plain Wheat)", "quantity": 2, "unit": "piece"}
             ]), \
             patch("routers.log.lookup_food", return_value=FAKE_FOOD):
            response = auth_client.post(
                "/log",
                files={"photo": ("test.jpg", FAKE_IMAGE_BYTES, "image/jpeg")},
            )
        assert b"Roti (Plain Wheat)" in response.content

    def test_unmatched_food_shows_warning(self, auth_client):
        """A food Claude identifies that isn't in the DB should show an unmatched warning."""
        with patch("routers.log.get_all_food_names", return_value=[]), \
             patch("routers.log.analyze_meal_photo", return_value=[
                 {"name": "Mystery Food", "quantity": 1, "unit": "serving"}
             ]), \
             patch("routers.log.lookup_food", return_value=None):
            response = auth_client.post(
                "/log",
                files={"photo": ("test.jpg", FAKE_IMAGE_BYTES, "image/jpeg")},
            )
        assert response.status_code == 200
        assert b"Not in database" in response.content


# ── POST /log/manual ──────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLogManualSubmit:

    def test_empty_items_returns_400(self, auth_client):
        response = auth_client.post("/log/manual",
                                    data={"items_json": json.dumps([])})
        assert response.status_code == 400

    def test_invalid_json_returns_400(self, auth_client):
        response = auth_client.post("/log/manual",
                                    data={"items_json": "not-valid-json"})
        assert response.status_code == 400

    def test_direct_lookup_shows_confirm_screen(self, auth_client):
        """lookup_food finds the food by name/synonym on the first call."""
        with patch("routers.log.get_all_food_names", return_value=["Dal Makhani"]), \
             patch("routers.log.lookup_food", return_value={
                 "id": 6, "item_name": "Dal Makhani",
                 "quantity": 1.0, "unit": "cup",
                 "calories": 270, "protein": 12,
                 "fat": 8, "carbohydrates": 35, "fiber": 6,
             }):
            response = auth_client.post("/log/manual", data={
                "items_json": json.dumps([{"name": "dal makhani", "servings": 1}])
            })
        assert response.status_code == 200
        assert b"Dal Makhani" in response.content
        assert b"Confirm meal" in response.content

    def test_fuzzy_fallback_finds_food(self, auth_client):
        """When lookup_food misses, fuzzy_match_food_name returns a canonical name
        and a second lookup_food call finds the food."""
        with patch("routers.log.get_all_food_names", return_value=["Roti (Plain Wheat)"]), \
             patch("routers.log.fuzzy_match_food_name", return_value="Roti (Plain Wheat)"), \
             patch("routers.log.lookup_food", side_effect=[None, FAKE_FOOD]):
            response = auth_client.post("/log/manual", data={
                "items_json": json.dumps([{"name": "roti", "servings": 1}])
            })
        assert response.status_code == 200
        assert b"Roti (Plain Wheat)" in response.content

    def test_no_match_found_shows_warning(self, auth_client):
        """Both lookup paths return nothing — item shown as unmatched."""
        with patch("routers.log.get_all_food_names", return_value=[]), \
             patch("routers.log.lookup_food", return_value=None), \
             patch("routers.log.fuzzy_match_food_name", return_value=None):
            response = auth_client.post("/log/manual", data={
                "items_json": json.dumps([{"name": "xyz unknown food", "servings": 1}])
            })
        assert response.status_code == 200
        assert b"Not in database" in response.content

    def test_multiple_items_all_appear_on_confirm(self, auth_client):
        roti = FAKE_FOOD
        dal  = {**FAKE_FOOD, "id": 6, "item_name": "Dal Makhani",
                "quantity": 1.0, "unit": "cup", "calories": 270,
                "protein": 12, "fat": 8, "carbohydrates": 35, "fiber": 6}

        with patch("routers.log.get_all_food_names", return_value=["Roti (Plain Wheat)", "Dal Makhani"]), \
             patch("routers.log.lookup_food", side_effect=[roti, dal]):
            response = auth_client.post("/log/manual", data={
                "items_json": json.dumps([
                    {"name": "roti",        "servings": 2},
                    {"name": "dal makhani", "servings": 1},
                ])
            })
        assert b"Roti (Plain Wheat)" in response.content
        assert b"Dal Makhani" in response.content


# ── POST /log/save ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLogSave:

    def test_unauthenticated_redirects(self, anon_client):
        response = anon_client.post("/log/save",
                                    data={"items_json": SAMPLE_ITEMS_JSON})
        assert response.status_code == 307

    def test_invalid_json_redirects_to_log(self, auth_client):
        response = auth_client.post("/log/save",
                                    data={"items_json": "bad-json"})
        assert response.status_code == 303
        assert response.headers["location"] == "/log"

    def test_empty_items_redirects_to_home(self, auth_client):
        response = auth_client.post("/log/save",
                                    data={"items_json": "[]"})
        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_valid_save_redirects_to_home(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value.data = \
            [{"id": "new-meal-log-uuid"}]

        with patch("routers.log.get_supabase_admin", return_value=mock_sb):
            response = auth_client.post("/log/save",
                                        data={"items_json": SAMPLE_ITEMS_JSON})

        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_save_inserts_meal_log_row(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value.data = \
            [{"id": "new-meal-log-uuid"}]

        with patch("routers.log.get_supabase_admin", return_value=mock_sb):
            auth_client.post("/log/save", data={"items_json": SAMPLE_ITEMS_JSON})

        # Verify .table("meal_logs") was called
        calls = [str(c) for c in mock_sb.table.call_args_list]
        assert any("meal_logs" in c for c in calls)

    def test_save_inserts_meal_log_items_row(self, auth_client):
        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value.data = \
            [{"id": "new-meal-log-uuid"}]

        with patch("routers.log.get_supabase_admin", return_value=mock_sb):
            auth_client.post("/log/save", data={"items_json": SAMPLE_ITEMS_JSON})

        calls = [str(c) for c in mock_sb.table.call_args_list]
        assert any("meal_log_items" in c for c in calls)

    def test_server_side_macro_recalculation(self, auth_client):
        """
        Ensure the server recalculates macros from base values rather than
        trusting the client-side numbers.
        """
        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value.data = \
            [{"id": "new-meal-log-uuid"}]

        # Tampered item: client claims 9999 calories but base math says 168
        tampered = json.dumps([{
            "food_name": "Roti (Plain Wheat)", "quantity": 2.0, "unit": "piece",
            "base_quantity": 1.0,
            "calories_per_base": 84.0,   # server MUST use these
            "protein_per_base": 4.1, "fat_per_base": 0.8,
            "carbs_per_base": 15.2, "fiber_per_base": 2.4,
        }])

        with patch("routers.log.get_supabase_admin", return_value=mock_sb):
            auth_client.post("/log/save", data={"items_json": tampered})

        # Inspect the dict passed to meal_logs insert
        insert_call = mock_sb.table.return_value.insert.call_args_list[0]
        meal_log_data = insert_call[0][0]  # first positional arg
        assert meal_log_data["total_calories"] == pytest.approx(168.0, abs=1)
