"""
Unit tests for pure-logic services and Supabase-backed services (fully mocked).

Covers:
  - services.profile.calculate_targets      (pure function — no mocks needed)
  - services.foods.macros_for_quantity      (pure function — no mocks needed)
  - services.foods.lookup_food              (Supabase mocked)
  - services.groq_match.match_food_name     (Groq API mocked — service kept but not in main chain)
  - services.fuzzy_match.fuzzy_match_food_name  (pure function — no mocks needed)
  - routers.log._build_line_item            (pure function — no mocks needed)
  - routers.profile.pct                     (pure function — no mocks needed)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from groq import APIError

from services.profile import calculate_targets
from services.foods import macros_for_quantity, lookup_food
from services.groq_match import match_food_name
from services.fuzzy_match import fuzzy_match_food_name
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
    Build a mock Supabase client where ALL three query paths in lookup_food
    return the same rows (ilike exact, contains synonym, ilike partial).
    """
    mock = MagicMock()
    result = MagicMock(data=rows)
    base = mock.table.return_value.select.return_value
    base.ilike.return_value.limit.return_value.execute.return_value = result
    base.contains.return_value.limit.return_value.execute.return_value = result
    return mock


@pytest.mark.unit
class TestLookupFood:

    def test_exact_match_found(self):
        with patch("services.foods.get_supabase_admin",
                   return_value=_supabase_returning([ROTI_DB_ROW])):
            result = lookup_food("Roti (Plain Wheat)")
        assert result is not None
        assert result["item_name"] == "Roti (Plain Wheat)"

    def test_synonym_match_fallback(self):
        """
        Exact ilike misses; synonym contains query finds the row.
        ilike calls share one execute mock (side_effect: [] then never reached).
        contains execute returns the match.
        """
        mock_sb = MagicMock()
        base = mock_sb.table.return_value.select.return_value
        # Exact ilike → miss; synonym contains → hit; partial ilike never called
        base.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        base.contains.return_value.limit.return_value.execute.return_value = MagicMock(data=[ROTI_DB_ROW])

        with patch("services.foods.get_supabase_admin", return_value=mock_sb):
            result = lookup_food("roti")
        assert result is not None
        assert result["item_name"] == "Roti (Plain Wheat)"

    def test_partial_match_fallback(self):
        """
        Exact ilike and synonym both miss; partial ilike finds the row.
        ilike is called twice (exact then partial) — use side_effect.
        """
        mock_sb = MagicMock()
        base = mock_sb.table.return_value.select.return_value
        ilike_exec = MagicMock(side_effect=[
            MagicMock(data=[]),         # exact miss
            MagicMock(data=[ROTI_DB_ROW]),  # partial hit
        ])
        base.ilike.return_value.limit.return_value.execute = ilike_exec
        base.contains.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        with patch("services.foods.get_supabase_admin", return_value=mock_sb):
            result = lookup_food("roti wheat")
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


# ─────────────────────────────────────────────────────────────────────────────
# fuzzy_match_food_name — RapidFuzz algorithmic matching (pure, no mocks)
# ─────────────────────────────────────────────────────────────────────────────

FUZZY_LIST = [
    "Roti (Plain Wheat)", "Dal Makhani", "Chicken Biryani",
    "Paneer Tikka", "Aloo Gobhi", "Rajma Masala", "Curd (Plain)",
]

# Realistic subset of the actual DB — used for regression tests on real failures
REALISTIC_LIST = [
    "Roti (Plain Wheat)", "Dal Makhani", "Chicken Biryani",
    "Paneer Tikka", "Aloo Gobhi", "Rajma Masala",
    "Curd (Plain)", "Dahi Bhalla (Curd Dumpling)",
    "Boiled Egg", "Stuffed Paratha",
    "Kesar Milk (Saffron Cold)", "Milk (Full Fat)",
    "Lychee", "Mango",
]


@pytest.mark.unit
class TestFuzzyMatchFoodName:

    def test_exact_match(self):
        assert fuzzy_match_food_name("Dal Makhani", FUZZY_LIST) == "Dal Makhani"

    def test_case_insensitive_match(self):
        assert fuzzy_match_food_name("dal makhani", FUZZY_LIST) == "Dal Makhani"

    def test_minor_spelling_error(self):
        # "chiken biryani" is close enough to "Chicken Biryani"
        result = fuzzy_match_food_name("chiken biryani", FUZZY_LIST)
        assert result == "Chicken Biryani"

    def test_transliteration_variant_lenient_threshold(self):
        # "alu gobi" scores ~56 vs "Aloo Gobhi" — transliterations need a
        # lenient threshold; at 50 it matches (Groq handles the strict path)
        result = fuzzy_match_food_name("alu gobi", FUZZY_LIST, threshold=50)
        assert result == "Aloo Gobhi"

    def test_partial_word_match_near_threshold(self):
        # "paneer" alone scores ~75 against "Paneer Tikka" (WRatio partial)
        # passes at threshold=70 but not the default 80 (prevents false positives)
        result = fuzzy_match_food_name("paneer", FUZZY_LIST, threshold=70)
        assert result == "Paneer Tikka"

    def test_below_threshold_returns_none(self):
        # Completely unrelated string should not match anything
        result = fuzzy_match_food_name("spaghetti carbonara", FUZZY_LIST)
        assert result is None

    def test_empty_food_list_returns_none(self):
        assert fuzzy_match_food_name("roti", []) is None

    def test_empty_description_returns_none(self):
        assert fuzzy_match_food_name("", FUZZY_LIST) is None

    def test_custom_threshold_strict(self):
        # With threshold=99, even good matches should fail unless near-perfect
        result = fuzzy_match_food_name("dal makhni", FUZZY_LIST, threshold=99)
        assert result is None

    def test_custom_threshold_lenient(self):
        # With threshold=50, a weak partial match can succeed
        result = fuzzy_match_food_name("rajma", FUZZY_LIST, threshold=50)
        assert result == "Rajma Masala"


@pytest.mark.unit
class TestFuzzyMatchRegressions:
    """
    Regression tests derived from real user inputs that failed in production.
    Each test is named after the original failure so it can be traced back.

    Passing status and required threshold are documented inline.
    Tests marked TRANSLITERATION_GAP document cases that RapidFuzz cannot
    solve and require Groq — they assert None at the default threshold.
    """

    # ── Case: "boilded egg" ──────────────────────────────────────────────────
    # WRatio("boilded egg", "Boiled Egg") = 76. Passes at threshold=70 but not 80.
    # The default threshold of 80 is too strict for single-char-swap typos.
    def test_typo_boilded_egg_at_threshold_70(self):
        result = fuzzy_match_food_name("boilded egg", REALISTIC_LIST, threshold=70)
        assert result == "Boiled Egg"

    def test_typo_boilded_egg_misses_at_default_threshold(self):
        # Documents that the default threshold=80 is too strict for this typo.
        # If this test starts FAILING (i.e. it returns a match), the threshold
        # was changed — verify the change doesn't introduce false positives.
        result = fuzzy_match_food_name("boilded egg", REALISTIC_LIST, threshold=80)
        assert result is None

    # ── Case: "paratha stuffed" ──────────────────────────────────────────────
    # WRatio = 82 via token_sort. Passes at default threshold=80 when the DB
    # item is named "Stuffed Paratha". Failure in prod means DB name differs.
    def test_word_order_paratha_stuffed(self):
        result = fuzzy_match_food_name("paratha stuffed", REALISTIC_LIST)
        assert result == "Stuffed Paratha"

    # ── Case: "litchi" (TRANSLITERATION_GAP) ────────────────────────────────
    # WRatio("litchi", "Lychee") = 33. No string algorithm bridges this gap.
    # Groq (or a synonyms entry) is required. This test documents the gap.
    def test_transliteration_litchi_not_matched_by_fuzzy(self):
        result = fuzzy_match_food_name("litchi", REALISTIC_LIST, threshold=80)
        assert result is None  # must be handled by synonyms column or Groq

    # ── Case: "milk" false positive ──────────────────────────────────────────
    # The partial ilike step (`%milk%`) returned "Kesar Milk" — wrong food.
    # Fuzzy at threshold=80 correctly rejects it (WRatio=73 < 80).
    def test_milk_does_not_false_positive_to_kesar_milk_at_default(self):
        result = fuzzy_match_food_name("milk", REALISTIC_LIST, threshold=80)
        # Neither "Kesar Milk" nor "Milk (Full Fat)" should win at strict threshold
        assert result != "Kesar Milk (Saffron Cold)"

    def test_milk_ambiguity_at_lenient_threshold(self):
        # WRatio("milk", "Milk (Full Fat)") == WRatio("milk", "Kesar Milk") == 73.
        # When scores tie, rapidfuzz returns the first candidate in the list.
        # This documents that single-word "milk" is AMBIGUOUS for fuzzy matching —
        # the correct answer ("Curd (Plain)" vs "Kesar Milk") needs Groq or synonyms.
        result = fuzzy_match_food_name("milk", REALISTIC_LIST, threshold=70)
        # At threshold=70 something matches — we can't guarantee which "milk" item
        assert result is not None
        assert "milk" in result.lower() or "Milk" in result

    # ── Case: "curd" false positive ──────────────────────────────────────────
    # The partial ilike step returned "Dahi Bhalla (Curd Dumpling)" — wrong food.
    # Fuzzy at threshold=80 rejects "Dahi Bhalla" (WRatio=68) AND "Curd (Plain)"
    # (WRatio=73). Both are below 80 so fuzzy returns None — correct: Groq/synonyms
    # should handle "curd" → "Curd (Plain)".
    def test_curd_does_not_false_positive_to_dahi_bhalla(self):
        result = fuzzy_match_food_name("curd", REALISTIC_LIST, threshold=80)
        assert result != "Dahi Bhalla (Curd Dumpling)"

    def test_curd_matches_plain_curd_at_lenient_threshold(self):
        # At threshold=70, "Curd (Plain)" (WRatio=73) beats "Dahi Bhalla" (WRatio=68)
        result = fuzzy_match_food_name("curd", REALISTIC_LIST, threshold=70)
        assert result == "Curd (Plain)"


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
        # 2 rotis = 2 × 84 = 168
        item = _build_line_item("roti", ROTI_FOOD_ROW, 2.0, "piece")
        assert item["calories"] == pytest.approx(168.0, abs=0.2)

    def test_matched_half_serving_scales_down(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 0.5, "piece")
        assert item["calories"] == pytest.approx(42.0, abs=0.2)
        assert item["protein_g"] == pytest.approx(2.05, abs=0.1)

    def test_matched_sets_base_quantity_from_food(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 2.0, "piece")
        assert item["base_quantity"] == pytest.approx(1.0)

    def test_matched_sets_per_base_values(self):
        item = _build_line_item("roti", ROTI_FOOD_ROW, 1.0, "piece")
        assert item["calories_per_base"] == pytest.approx(84.0)
        assert item["protein_per_base"]  == pytest.approx(4.1)

    def test_unmatched_all_macros_zero(self):
        item = _build_line_item("xyz", None, 2.0, "serving")
        assert item["calories"] == 0
        assert item["protein_g"] == 0
        assert item["fat_g"] == 0
        assert item["carbs_g"] == 0
        assert item["fiber_g"] == 0

    def test_unmatched_base_quantity_equals_user_qty(self):
        # factor must be 1 so that macros stay 0 after recalc on confirm
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
        # 333/1000 = 33.3% → rounds to 33
        assert pct(333, 1000) == 33

    def test_fractional_consumed_works(self):
        # round(50.5) = 50 in Python 3 (banker's rounding)
        assert pct(50.5, 100) == 50
