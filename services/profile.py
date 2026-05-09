import os
from supabase import create_client, Client


def get_supabase_admin() -> Client:
    """
    Admin client using the SERVICE ROLE key — bypasses RLS.
    Only used server-side for profile operations where we've already
    verified the user's identity via their JWT.
    Never expose this key to the browser.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def get_profile(user_id: str) -> dict | None:
    supabase = get_supabase_admin()
    try:
        response = (
            supabase.table("profiles")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None
    except Exception:
        return None


def upsert_profile(user_id: str, data: dict) -> dict:
    """
    Insert or update the profile for a user.
    'data' should contain all profile fields (name, dob, sex, etc.)
    plus the calculated targets.
    Returns the saved profile dict.
    """
    supabase = get_supabase_admin()
    payload = {"user_id": user_id, **data}
    response = (
        supabase.table("profiles")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )
    return response.data[0]


# ---------------------------------------------------------------------------
# Mifflin-St Jeor calorie calculator
# ---------------------------------------------------------------------------

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,       # desk job, little exercise
    "light": 1.375,         # light exercise 1–3 days/week
    "moderate": 1.55,       # moderate exercise 3–5 days/week
    "active": 1.725,        # hard exercise 6–7 days/week
}

def calculate_targets(
    age: int,
    sex: str,          # "M" or "F"
    weight_kg: float,
    height_cm: float,
    activity_level: str,   # one of ACTIVITY_MULTIPLIERS keys
    goal: str,         # "lose" | "maintain" | "gain"
) -> dict:
    """
    Calculate daily calorie and macro targets using Mifflin-St Jeor.

    Steps:
    1. Calculate BMR (Basal Metabolic Rate) — calories burned at complete rest.
    2. Multiply by activity factor → TDEE (Total Daily Energy Expenditure).
    3. Adjust for goal (deficit/surplus).
    4. Split into macros using standard ratios.
    """

    # Step 1: BMR
    if sex == "M":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161

    # Step 2: TDEE
    multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, 1.375)
    tdee = bmr * multiplier

    # Step 3: Adjust for goal
    if goal == "lose":
        calories = tdee - 500      # ~0.5 kg/week deficit
    elif goal == "gain":
        calories = tdee + 300      # lean bulk surplus
    else:
        calories = tdee            # maintain

    calories = round(calories)

    # Step 4: Macros
    # Protein: 2g per kg bodyweight (high — good for both fat loss and muscle gain)
    # Fat: 25% of calories
    # Carbs: remainder
    protein_g = round(2 * weight_kg)
    fat_g = round((calories * 0.25) / 9)          # 9 kcal per gram of fat
    protein_calories = protein_g * 4              # 4 kcal per gram of protein
    fat_calories = fat_g * 9
    carb_calories = calories - protein_calories - fat_calories
    carbs_g = round(carb_calories / 4)            # 4 kcal per gram of carbs
    fiber_g = 30                                   # standard recommendation

    return {
        "daily_calorie_target": calories,
        "daily_protein_g": protein_g,
        "daily_carbs_g": carbs_g,
        "daily_fat_g": fat_g,
        "daily_fiber_g": fiber_g,
    }