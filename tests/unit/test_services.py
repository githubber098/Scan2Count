"""
Unit tests for pure-logic services and Supabase-backed services (fully mocked).

Covers:
  - services.profile.calculate_targets          (pure function — no mocks needed)
  - services.foods.macros_for_quantity          (pure function — no mocks needed)
  - services.foods.lookup_food                  (Supabase mocked)
  - services.claude_match.match_food_names      (Anthropic API mocked)
  - routers.log._build_line_item                (pure function — no mocks needed)
  - routers.profile.pct                         (pure function — no mocks needed)
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import MagicMock, patch

from services.profile import calculate_targets
from services.foods import macros_for_quantity, lookup_food
from services.claude_match import match_food_names
from routers.log import _build_line_item
from routers.profile import pct

# ─────────────────────────────────────────────────────────────────────────────
# calculate_targets — Mifflin-St Jeor formula
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCalculateTargets:
    """Verify the calorie and macro calculations are mathematically correct."""

    def test_male_sedentary_maintain(self):
        # BMR = 10*70 + 6.25*175 - 5*30 + 5 = 1648.75
        # TDEE = 1648.75 * 1.2 = 1978.5 → 1978 (banker's rounding)
        result = calculate_targets(
            age=30, sex="M", weight_kg=70, height_cm=175,
            activity_level="sedentary", goal="maintain",
        )
        assert result["daily_calorie_target"] == 1978
        assert result["daily_protein_g"]      == 140     # 2g × 70 kg
        assert result["daily_fiber_g"]        == 30

    def test_female_moderate_lose(self):
        result = calculate_targets(
            age=25, sex="F", weight_kg=60, height_cm=165,
            activity_level="moderate", goal="lose",
        )
        assert result["daily_calorie_target"] == 1585
        assert result["daily_protein_g"]      == 120
        assert result["daily_fiber_g"]        == 30

    def test_male_active_gain(self):
        result = calculate_targets(
            age=22, sex="M", weight_kg=75, height_cm=180,
            activity_level="active", goal="gain",
        )
        assert result["daily_calorie_target"] == 3353
        assert result["daily_protein_g"]      == 150
        assert result["daily_fiber_g"]        == 30

    def test_goal_lose_is_less_than_maintain(self):
        base = dict(age=28, sex="M", weight_kg=80, height_cm=180,
                    activity_level="moderate")
        lose     = calculate_targets(**base, goal="lose")
        maintain = calculate_targets(**base, goal="maintain")
        gain     = calculate_targets(**base, goal="gain")
        assert lose["daily_calorie_target"] < maintain["daily_calorie_target"] < gain["daily_calorie_target"]

    def test_female_bmr_lower_than_male_same_stats(self):
        shared = dict(age=30, weight_kg=70, height_cm=170,
                      activity_level="sedentary", goal="maintain")
        male   = calculate_targets(sex="M", **shared)
        female = calculate_targets(sex="F", **shared)
        assert male["daily_calorie_target"] > female["daily_calorie_target"]

    def test_unknown_activity_falls_back_to_light(self):
        known   = calculate_targets(age=30, sex="M", weight_kg=70, height_cm=175,
                                    activity_level="light", goal="maintain")
        unknown = calculate_targets(age=30, sex="M", weight_kg=70, height_cm=175,
                                    activity_level="INVALID", goal="maintain")
        assert known["daily_calorie_target"] == unknown["daily_calorie_target"]

    def test_macro_calories_sum_near_target(self):
        result = calculate_targets(age=30, sex="M", weight_kg=75, height_cm=178,
                                   activity_level="moderate", goal="maintain")
        derived = (
            result["daily_protein_g"] * 4
            + result["daily_fat_g"]   * 9
            + result["daily_carbs_g"] * 4
        )
        assert abs(derived - result["daily_calorie_target"]) <= 10


# ─────────────────────────────────────────────────────────────────────────────
# macros_for_quantity — serving-based scaling
# ─────────────────────────────────────────────────────────────────────────────

ROTI_FOOD = {
    "quantity": 1.0, "unit": "piece",
    "calories": 84.0, "protein": 4.1,
    "fat": 0.8, "carbohydrates": 15.2, "fiber": 2.4,
}

RICE_FOOD = {
    "quantity": 1.0, "unit": "cup",
    "calories": 206.0, "protein": 4.3,
    "fat": 0.3, "carbohydrates": 45.0, "fiber": 0.6,
}

PAKORA_FOOD = {
    "quantity": 100.0, "unit": "g",
    "calories": 150.0, "protein": 4.5,
    "fat": 6.0, "carbohydrates": 20.0, "fiber": 2.0,
}


@pytest.mark.unit
class TestMacrosForQuantity:

    def test_single_serving_returns_base_values(self):
        result = macros_for_quantity(ROTI_FOOD, user_quantity=1.0)
        assert result["calories"]  == pytest.approx(84.0,  abs=0.1)
        assert result["protein_g"] == pytest.approx(4.1,   abs=0.1)
        assert result["fat_g"]     == pytest.approx(0.8,   abs=0.1)
        assert result["carbs_g"]   == pytest.approx(15.2,  abs=0.1)
        assert result["fiber_g"]   == pytest.approx(2.4,   abs=0.1)

    def test_double_serving_doubles_all_macros(self):
        result = macros_for_quantity(ROTI_FOOD, user_quantity=2.0)
        assert result["calories"]  == pytest.approx(168.0, abs=0.2)
        assert result["protein_g"] == pytest.approx(8.2,   abs=0.2)

    def test_half_cup_rice(self):
        result = macros_for_quantity(RICE_FOOD, user_quantity=0.5)
        assert result["calories"] == pytest.approx(103.0, abs=0.2)
        assert result["carbs_g"]  == pytest.approx(22.5,  abs=0.2)

    def test_gram_based_food_150g(self):
        result = macros_for_quantity(PAKORA_FOOD, user_quantity=150.0)
        assert result["calories"] == pytest.approx(225.0, abs=0.2)
        assert result["fat_g"]    == pytest.approx(9.0,   abs=0.2)

    def test_none_base_quantity_defaults_to_one_serving(self):
        food   = {**ROTI_FOOD, "quantity": None}
        result = macros_for_quantity(food, user_quantity=1.0)
        assert result["calories"] == pytest.approx(84.0, abs=0.1)

    def test_zero_quantity_falls_back_to_one_serving(self):
        food   = {**ROTI_FOOD, "quantity": 0}
        result = macros_for_quantity(food, user_quantity=2.0)
        assert result["calories"] == pytest.approx(168.0, abs=0.2)

    def test_returns_all_required_keys(self):
        result = macros_for_quantity(ROTI_FOOD, user_quantity=1.0)
        assert set(result.keys()) == {"calories", "protein_g", "fat_g", "carbs_g", "fiber_g"}


# ─────────────────────────────────────────────────────────────────────────────
# lookup_food — Supabase queries mocked
# ─────────────────────────────────────────────────────────────────────────────

ROTI_DB_ROW = {
    "id": 1, "item_name": "Roti (Plain Wheat)",
    "quantity": 1.0, "unit": "piece",
    "calories": 84.0, "protein": 4.1,
    "fat": 0.8, "carbohydrates": 15.2, "fiber": 2.4,
}

FISH_AND_CHIPS_ROW = {
    "id": 99, "item_name": "Fish and Chips",
    "quantity": 1.0, "unit": "serving",
    "calories": 500.0, "protein": 20.0,
    "fat": 25.0, "carbohydrates": 55.0, "fiber": 3.0,
}


def _supabase_returning(rows: list[dict]) -> MagicMock:
    """Build a mock Supabase client for the single exact-ilike query in lookup_food."""
    mock = MagicMock()
    result = MagicMock(data=rows)
    mock.table.return_value.select.return_value.ilike.return_value.limit.return_value.execute.return_value = result
    return mock


@pytest.mark.unit
class TestLookupFood:

    def test_exact_match_found(self):
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([ROTI_DB_ROW])):
            result = lookup_food("Roti (Plain Wheat)")
        assert result is not None
        assert result["item_name"] == "Roti (Plain Wheat)"

    def test_no_partial_ilike_fallback(self):
        """
        Partial substring matching is intentionally absent from lookup_food.
        A partial name that doesn't exactly match any item_name must return None.
        The Claude Haiku layer resolves abbreviations/misspellings before this is called.
        """
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([])):
            result = lookup_food("roti wheat")
        assert result is None

    def test_chips_does_not_match_fish_and_chips(self):
        """
        Regression: 'chips' must not return 'Fish and Chips' via substring match.
        The exact ilike('chips') does not match 'Fish and Chips'.
        """
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([])):
            result = lookup_food("chips")
        assert result is None

    def test_no_match_returns_none(self):
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([])):
            result = lookup_food("pizza")
        assert result is None

    def test_empty_name_returns_none(self):
        result = lookup_food("")
        assert result is None

    def test_strips_whitespace_from_name(self):
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([ROTI_DB_ROW])):
            result = lookup_food("  Roti (Plain Wheat)  ")
        assert result is not None

    def test_does_not_check_synonyms_column(self):
        """Synonym/regional-name resolution happens in Claude Haiku, not here."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        with patch("services.foods.get_supabase_admin", return_value=mock_sb):
            lookup_food("litchi")

        mock_sb.table.return_value.select.return_value.contains.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# match_food_names — Claude Haiku API mocked
# ─────────────────────────────────────────────────────────────────────────────

FOOD_LIST = ["Roti (Plain Wheat)", "Dal Makhani", "Chicken Biryani",
             "Paneer Tikka", "Lychee", "Curd (Plain)", "Boiled Egg",
             "Stuffed Paratha", "Milk (Full Fat)", "Fish and Chips"]


def _mock_haiku(result_dict: dict) -> MagicMock:
    """Return a patched Anthropic class whose messages.create() returns result_dict as JSON."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(result_dict)
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_resp
    return MagicMock(return_value=mock_client)


@pytest.mark.unit
class TestMatchFoodNames:

    def test_matched_items_returned(self):
        haiku = _mock_haiku({"dal": "Dal Makhani", "litchi": "Lychee"})
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["dal", "litchi"], FOOD_LIST)
        assert result == {"dal": "Dal Makhani", "litchi": "Lychee"}

    def test_no_match_returns_none(self):
        haiku = _mock_haiku({"chips": "NO_MATCH"})
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["chips"], FOOD_LIST)
        assert result == {"chips": None}

    def test_mixed_match_and_no_match(self):
        haiku = _mock_haiku({"roti": "Roti (Plain Wheat)", "xyz": "NO_MATCH"})
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["roti", "xyz"], FOOD_LIST)
        assert result["roti"] == "Roti (Plain Wheat)"
        assert result["xyz"]  is None

    def test_api_error_returns_none_for_all(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("network error")
        haiku = MagicMock(return_value=mock_client)
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["dal", "roti"], FOOD_LIST)
        assert result == {"dal": None, "roti": None}

    def test_invalid_json_returns_none_for_all(self):
        mock_content = MagicMock()
        mock_content.text = "not valid json {"
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        haiku = MagicMock(return_value=mock_client)
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["dal"], FOOD_LIST)
        assert result == {"dal": None}

    def test_empty_descriptions_returns_empty_dict_no_api_call(self):
        haiku = MagicMock()
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names([], FOOD_LIST)
        haiku.assert_not_called()
        assert result == {}

    def test_empty_food_names_returns_none_for_all_no_api_call(self):
        haiku = MagicMock()
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["dal", "roti"], [])
        haiku.assert_not_called()
        assert result == {"dal": None, "roti": None}

    def test_single_api_call_for_multiple_items(self):
        """All descriptions are batched into exactly one Anthropic API call."""
        haiku = _mock_haiku({"dal": "Dal Makhani", "roti": "Roti (Plain Wheat)",
                              "litchi": "Lychee"})
        with patch("services.claude_match.Anthropic", haiku):
            match_food_names(["dal", "roti", "litchi"], FOOD_LIST)
        haiku.return_value.messages.create.assert_called_once()

    def test_strips_markdown_fences(self):
        mock_content = MagicMock()
        mock_content.text = '```json\n{"dal": "Dal Makhani"}\n```'
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp
        haiku = MagicMock(return_value=mock_client)
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["dal"], FOOD_LIST)
        assert result == {"dal": "Dal Makhani"}

    def test_missing_key_in_response_mapped_to_none(self):
        """If the model omits a description from its JSON output, map it to None."""
        haiku = _mock_haiku({"dal": "Dal Makhani"})  # "roti" missing from response
        with patch("services.claude_match.Anthropic", haiku):
            result = match_food_names(["dal", "roti"], FOOD_LIST)
        assert result["dal"]  == "Dal Makhani"
        assert result["roti"] is None

    # ── Regression tests — real failure cases from production ─────────────────

    def test_regression_litchi_maps_to_lychee(self):
        haiku = _mock_haiku({"litchi": "Lychee"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["litchi"], FOOD_LIST)["litchi"] == "Lychee"

    def test_regression_paratha_stuffed_maps_to_stuffed_paratha(self):
        haiku = _mock_haiku({"paratha stuffed": "Stuffed Paratha"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["paratha stuffed"], FOOD_LIST)["paratha stuffed"] == "Stuffed Paratha"

    def test_regression_curd_maps_to_curd_plain(self):
        haiku = _mock_haiku({"curd": "Curd (Plain)"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["curd"], FOOD_LIST)["curd"] == "Curd (Plain)"

    def test_regression_boilded_egg_maps_to_boiled_egg(self):
        haiku = _mock_haiku({"boilded egg": "Boiled Egg"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["boilded egg"], FOOD_LIST)["boilded egg"] == "Boiled Egg"

    def test_regression_chapati_maps_to_roti(self):
        haiku = _mock_haiku({"chapati": "Roti (Plain Wheat)"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["chapati"], FOOD_LIST)["chapati"] == "Roti (Plain Wheat)"

    def test_regression_mixed_case_chappatti_maps_to_roti(self):
        haiku = _mock_haiku({"CHAppAtti": "Roti (Plain Wheat)"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["CHAppAtti"], FOOD_LIST)["CHAppAtti"] == "Roti (Plain Wheat)"

    def test_regression_chips_not_matched_to_fish_and_chips(self):
        haiku = _mock_haiku({"chips": "NO_MATCH"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["chips"], FOOD_LIST)["chips"] is None

    def test_regression_milk_maps_to_plain_milk_not_kesar(self):
        """'milk' should resolve to plain Milk, not Kesar Milk (Saffron Cold)."""
        haiku = _mock_haiku({"milk": "Milk (Full Fat)"})
        with patch("services.claude_match.Anthropic", haiku):
            assert match_food_names(["milk"], FOOD_LIST)["milk"] == "Milk (Full Fat)"


# ─────────────────────────────────────────────────────────────────────────────
# _build_line_item — confirmed-item assembly (pure, no DB)
# ─────────────────────────────────────────────────────────────────────────────

ROTI_FOOD_ROW = {
    "id": 1, "item_name": "Roti (Plain Wheat)",
    "quantity": 1.0, "unit": "piece",
    "calories": 84.0, "protein": 4.1,
    "fat": 0.8, "carbohydrates": 15.2, "fiber": 2.4,
}


@pytest.mark.unit
class TestBuildLineItem:

    def test_matched_food_sets_matched_true(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 1.0, "piece")
        assert item["matched"] is True

    def test_unmatched_food_sets_matched_false(self):
        item = _build_line_item("xyz", None, 1.0, "serving")
        assert item["matched"] is False

    def test_matched_uses_canonical_food_name(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 1.0, "piece")
        assert item["food_name"] == "Roti (Plain Wheat)"

    def test_unmatched_uses_ai_name_as_food_name(self):
        item = _build_line_item("mystery dish", None, 1.0, "serving")
        assert item["food_name"] == "mystery dish"

    def test_matched_calories_scaled_correctly(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 2.0, "piece")
        assert item["calories"] == pytest.approx(168.0, abs=0.2)

    def test_matched_half_serving_scales_down(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 0.5, "piece")
        assert item["calories"]   == pytest.approx(42.0,  abs=0.2)
        assert item["protein_g"]  == pytest.approx(2.05, abs=0.1)

    def test_matched_sets_base_quantity_from_food(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 2.0, "piece")
        assert item["base_quantity"] == pytest.approx(1.0)

    def test_matched_sets_per_base_values(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 1.0, "piece")
        assert item["calories_per_base"] == pytest.approx(84.0)
        assert item["protein_per_base"]  == pytest.approx(4.1)

    def test_unmatched_all_macros_zero(self):
        item = _build_line_item("xyz", None, 2.0, "serving")
        assert item["calories"]  == 0
        assert item["protein_g"] == 0
        assert item["fat_g"]     == 0
        assert item["carbs_g"]   == 0
        assert item["fiber_g"]   == 0

    def test_unmatched_base_quantity_equals_user_qty(self):
        item = _build_line_item("xyz", None, 3.0, "serving")
        assert item["base_quantity"] == item["quantity"]


# ─────────────────────────────────────────────────────────────────────────────
# pct — progress bar percentage helper (pure, no mocks)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestPct:

    def test_zero_consumed_returns_zero(self):
        assert pct(0, 2000) == 0

    def test_full_target_returns_100(self):
        assert pct(2000, 2000) == 100

    def test_half_target_returns_50(self):
        assert pct(1000, 2000) == 50

    def test_over_target_capped_at_100(self):
        assert pct(3000, 2000) == 100

    def test_zero_target_returns_zero_not_divzero(self):
        assert pct(500, 0) == 0

    def test_none_target_returns_zero(self):
        assert pct(500, None) == 0

    def test_rounds_to_nearest_int(self):
        assert pct(333, 1000) == 33

    def test_fractional_consumed_works(self):
        # round(50.5) = 50 in Python 3 (banker's rounding)
        assert pct(50.5, 100) == 50
