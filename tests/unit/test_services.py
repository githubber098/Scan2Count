"""
Unit tests for pure-logic services and Supabase-backed services (fully mocked).

Covers:
  - services.profile.calculate_targets  (pure function — no mocks needed)
  - services.foods.macros_for_quantity  (pure function — no mocks needed)
  - services.foods.lookup_food          (Supabase mocked)
  - services.groq_match.match_food_name (Groq API mocked)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from groq import APIError

from services.profile import calculate_targets
from services.foods import macros_for_quantity, lookup_food
from services.groq_match import match_food_name

# ─────────────────────────────────────────────────────────────────────────────
# calculate_targets — Mifflin-St Jeor formula
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCalculateTargets:
    """Verify the calorie and macro calculations are mathematically correct."""

    def test_male_sedentary_maintain(self):
        # BMR = 10*70 + 6.25*175 - 5*30 + 5 = 1648.75
        # TDEE = 1648.75 * 1.2 = 1978.5 → 1979
        result = calculate_targets(
            age=30, sex="M", weight_kg=70, height_cm=175,
            activity_level="sedentary", goal="maintain",
        )
        assert result["daily_calorie_target"] == 1978   # round(1978.5) → 1978 (banker's rounding)
        assert result["daily_protein_g"]      == 140     # 2g × 70 kg
        assert result["daily_fiber_g"]        == 30

    def test_female_moderate_lose(self):
        # BMR = 10*60 + 6.25*165 - 5*25 - 161 = 1345.25
        # TDEE = 1345.25 * 1.55 = 2085.1375
        # lose → 2085.1375 - 500 = 1585.1375 → 1585
        result = calculate_targets(
            age=25, sex="F", weight_kg=60, height_cm=165,
            activity_level="moderate", goal="lose",
        )
        assert result["daily_calorie_target"] == 1585
        assert result["daily_protein_g"]      == 120     # 2g × 60 kg
        assert result["daily_fiber_g"]        == 30

    def test_male_active_gain(self):
        # BMR = 10*75 + 6.25*180 - 5*22 + 5 = 1770
        # TDEE = 1770 * 1.725 = 3053.25
        # gain → 3053.25 + 300 = 3353.25 → 3353
        result = calculate_targets(
            age=22, sex="M", weight_kg=75, height_cm=180,
            activity_level="active", goal="gain",
        )
        assert result["daily_calorie_target"] == 3353
        assert result["daily_protein_g"]      == 150     # 2g × 75 kg
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
        # Female BMR constant is -161 vs male +5 → 166 kcal difference
        assert male["daily_calorie_target"] > female["daily_calorie_target"]

    def test_unknown_activity_falls_back_to_light(self):
        """Unknown activity_level key should use the 1.375 (light) multiplier."""
        known   = calculate_targets(age=30, sex="M", weight_kg=70, height_cm=175,
                                    activity_level="light", goal="maintain")
        unknown = calculate_targets(age=30, sex="M", weight_kg=70, height_cm=175,
                                    activity_level="INVALID", goal="maintain")
        assert known["daily_calorie_target"] == unknown["daily_calorie_target"]

    def test_macro_calories_sum_near_target(self):
        """protein×4 + fat×9 + carbs×4 should be within ±10 kcal of the target."""
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
        # 150g pakora = 1.5× the 100g base
        result = macros_for_quantity(PAKORA_FOOD, user_quantity=150.0)
        assert result["calories"] == pytest.approx(225.0, abs=0.2)
        assert result["fat_g"]    == pytest.approx(9.0,   abs=0.2)

    def test_none_base_quantity_defaults_to_one_serving(self):
        """Missing/None quantity should fall back to 1 (not divide by zero)."""
        food   = {**ROTI_FOOD, "quantity": None}
        result = macros_for_quantity(food, user_quantity=1.0)
        # factor = 1/1 = 1 → same as base values
        assert result["calories"] == pytest.approx(84.0, abs=0.1)

    def test_zero_quantity_falls_back_to_one_serving(self):
        """quantity=0 is falsy so `or 1` kicks in — avoids division by zero."""
        food   = {**ROTI_FOOD, "quantity": 0}
        result = macros_for_quantity(food, user_quantity=2.0)
        # factor = 2/1 = 2 (0 or 1 = 1 is the fallback)
        assert result["calories"] == pytest.approx(168.0, abs=0.2)

    def test_returns_all_required_keys(self):
        result = macros_for_quantity(ROTI_FOOD, user_quantity=1.0)
        assert set(result.keys()) == {"calories", "protein_g", "fat_g", "carbs_g", "fiber_g"}


# ─────────────────────────────────────────────────────────────────────────────
# lookup_food — Supabase queries mocked
# ─────────────────────────────────────────────────────────────────────────────

# Full food dict as returned by the DB (must include item_name)
ROTI_DB_ROW = {
    "id": 1, "item_name": "Roti (Plain Wheat)",
    "quantity": 1.0, "unit": "piece",
    "calories": 84.0, "protein": 4.1,
    "fat": 0.8, "carbohydrates": 15.2, "fiber": 2.4,
}


def _supabase_returning(rows: list[dict]) -> MagicMock:
    """
    Build a mock Supabase client where every query in lookup_food's chain
    returns the same rows.  lookup_food calls get_supabase_admin() ONCE and
    reuses that client for both queries, so we mock the execute() call with
    side_effect when the two queries must return different results.
    """
    mock = MagicMock()
    mock.table.return_value.select.return_value \
        .ilike.return_value.limit.return_value \
        .execute.return_value.data = rows
    return mock


@pytest.mark.unit
class TestLookupFood:

    def test_exact_match_found(self):
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([ROTI_DB_ROW])):
            result = lookup_food("Roti (Plain Wheat)")
        assert result is not None
        assert result["item_name"] == "Roti (Plain Wheat)"

    def test_partial_match_fallback(self):
        """
        lookup_food calls get_supabase_admin() ONCE and runs two .ilike() queries
        on the same client.  We simulate the first returning [] and the second
        returning a match by using side_effect on execute().
        """
        mock_sb = MagicMock()
        execute_mock = MagicMock()
        # First execute() call → no match; second → match
        execute_mock.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[ROTI_DB_ROW]),
        ]
        mock_sb.table.return_value.select.return_value \
            .ilike.return_value.limit.return_value \
            .execute = execute_mock

        with patch("services.foods.get_supabase_admin", return_value=mock_sb):
            result = lookup_food("roti")
        assert result is not None
        assert result["item_name"] == "Roti (Plain Wheat)"

    def test_no_match_returns_none(self):
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([])):
            result = lookup_food("pizza")
        assert result is None

    def test_strips_whitespace_from_name(self):
        """Whitespace should be stripped before querying."""
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([ROTI_DB_ROW])):
            result = lookup_food("  Roti (Plain Wheat)  ")
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# match_food_name — Groq API mocked
# ─────────────────────────────────────────────────────────────────────────────

FOOD_LIST = ["Roti (Plain Wheat)", "Dal Makhani", "Chicken Biryani", "Paneer Tikka"]


def _groq_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock


@pytest.mark.unit
class TestMatchFoodName:

    def test_returns_exact_match(self):
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = \
                _groq_response("Dal Makhani")
            result = match_food_name("dal makhani", FOOD_LIST)
        assert result == "Dal Makhani"

    def test_case_insensitive_fallback(self):
        """Model returns wrong capitalisation — should still match."""
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = \
                _groq_response("dal makhani")
            result = match_food_name("dal", FOOD_LIST)
        assert result == "Dal Makhani"

    def test_no_match_returns_none(self):
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = \
                _groq_response("NO_MATCH")
            result = match_food_name("spaghetti carbonara", FOOD_LIST)
        assert result is None

    def test_api_error_returns_none(self):
        """Any Groq API failure should return None, not raise."""
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.side_effect = \
                Exception("connection timeout")
            result = match_food_name("roti", FOOD_LIST)
        assert result is None

    def test_empty_food_list_returns_none(self):
        result = match_food_name("roti", [])
        assert result is None

    def test_missing_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        result = match_food_name("roti", FOOD_LIST)
        assert result is None

    def test_misspelling_returns_match(self):
        """'litchi' is a misspelling of lychee — model should return the DB name."""
        extended = FOOD_LIST + ["Lychee"]
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = \
                _groq_response("Lychee")
            result = match_food_name("litchi", extended)
        assert result == "Lychee"

    def test_ingredient_only_returns_no_match(self):
        """'milk' shares a word with 'Milk Peda' but is not that dish — should be NO_MATCH."""
        extended = FOOD_LIST + ["Milk Peda", "Milk Cake"]
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = \
                _groq_response("NO_MATCH")
            result = match_food_name("milk", extended)
        assert result is None

    def test_uses_llama_70b_model(self):
        """Verify the correct model is being called."""
        with patch("services.groq_match.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = \
                _groq_response("Dal Makhani")
            match_food_name("dal", FOOD_LIST)
        call_kwargs = MockGroq.return_value.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "llama-3.3-70b-versatile"
