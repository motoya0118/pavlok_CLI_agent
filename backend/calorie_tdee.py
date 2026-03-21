"""
v0.3.2 TDEE/PFC計算モジュール

Mifflin-St Jeor式によるTDEE計算とPFC目標値の算出、当日摂取量の集計を行う。
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def _round_to_one_decimal(value: float) -> float:
    """Round to 1 decimal place."""
    return round(value, 1)


def calculate_tdee(
    gender: str,
    age: int,
    height_cm: int,
    weight_kg: float,
    activity_level: str,
    diet_goal: str,
) -> dict:
    """
    Mifflin-St Jeor式でTDEEを計算し、PFC目標値を算出する。

    Args:
        gender: "male" or "female"
        age: 年齢
        height_cm: 身長(cm)
        weight_kg: 体重(kg)
        activity_level: 活動係数 "1.2", "1.375", "1.55", "1.725"
        diet_goal: "lose"(減量), "maintain"(維持), "gain"(増量)

    Returns:
        daily_calorie_goal: 1日摂取目標カロリー(kcal)
        protein_g: タンパク質目標(g)
        fat_g: 脂質目標(g)
        carbs_g: 炭水化物目標(g)
    """
    # Mifflin-St Jeor式（基礎代謝BMR）
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    # TDEE = BMR × 活動係数
    tdee = bmr * float(activity_level)

    # 目的別補正
    goal_adj = {"lose": -500, "maintain": 0, "gain": 500}
    daily_calorie_goal = tdee + goal_adj[diet_goal]

    # PFC分解
    # タンパク質: 体重 × 2g
    protein_g = weight_kg * 2.0
    # 脂質: 体重 × 0.9g
    fat_g = weight_kg * 0.9
    # 炭水化物: 残りカロリー / 4
    remaining_calories = daily_calorie_goal - (protein_g * 4) - (fat_g * 9)
    carbs_g = max(0, remaining_calories / 4)

    return {
        "daily_calorie_goal": int(daily_calorie_goal),
        "protein_g": _round_to_one_decimal(protein_g),
        "fat_g": _round_to_one_decimal(fat_g),
        "carbs_g": _round_to_one_decimal(carbs_g),
    }


def calculate_remaining(
    user_id: str,
    target_date: date,
    configs: dict[str, str],
    session,
) -> dict:
    """
    当日の摂取残量を計算する。

    Args:
        user_id: ユーザーID
        target_date: 集計対象日付
        configs: _load_user_config_values()で取得した設定辞書
        session: DBセッション

    Returns:
        goal: TDEE計算結果
        consumed: 当日摂取量
        remaining: 残り許容値
    """
    from backend.models import CalorieRecord

    # TDEE計算
    tdee_result = calculate_tdee(
        gender=configs.get("GENDER", "male"),
        age=int(configs.get("AGE", 30)),
        height_cm=int(configs.get("HEIGHT_CM", 170)),
        weight_kg=float(configs.get("WEIGHT_KG", 65.0)),
        activity_level=configs.get("ACTIVITY_LEVEL", "1.375"),
        diet_goal=configs.get("DIET_GOAL", "maintain"),
    )

    # 当日集計（JSTの日付境界で判定）
    # DBのuploaded_atはnaive datetime（JST）なので、比較もnaiveで行う
    start_of_day = datetime.combine(target_date, time.min)  # 00:00:00
    end_of_day = datetime.combine(target_date, time.max)  # 23:59:59.999999

    records = (
        session.query(CalorieRecord)
        .filter(
            CalorieRecord.user_id == user_id,
            CalorieRecord.uploaded_at >= start_of_day,
            CalorieRecord.uploaded_at <= end_of_day,
        )
        .all()
    )

    consumed_calorie = sum(r.calorie for r in records)
    consumed_protein = _round_to_one_decimal(sum(r.protein_g or 0 for r in records))
    consumed_fat = _round_to_one_decimal(sum(r.fat_g or 0 for r in records))
    consumed_carbs = _round_to_one_decimal(sum(r.carbs_g or 0 for r in records))

    return {
        "goal": tdee_result,
        "consumed": {
            "calorie": consumed_calorie,
            "protein_g": consumed_protein,
            "fat_g": consumed_fat,
            "carbs_g": consumed_carbs,
        },
        "remaining": {
            "calorie": max(0, tdee_result["daily_calorie_goal"] - consumed_calorie),
            "protein_g": max(0, _round_to_one_decimal(tdee_result["protein_g"] - consumed_protein)),
            "fat_g": max(0, _round_to_one_decimal(tdee_result["fat_g"] - consumed_fat)),
            "carbs_g": max(0, _round_to_one_decimal(tdee_result["carbs_g"] - consumed_carbs)),
        },
    }
