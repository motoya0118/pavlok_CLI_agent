"""
v0.3.2 TDEE/PFC計算モジュールの単体テスト
"""

from datetime import date

from backend.calorie_tdee import calculate_remaining, calculate_tdee
from backend.models import CalorieRecord


class TestCalculateTdee:
    """calculate_tdee()のテスト"""

    def test_tdee_01_standard_male_maintain(self):
        """標準男性（維持）"""
        result = calculate_tdee(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="1.375",
            diet_goal="maintain",
        )
        # BMR = 10*70 + 6.25*175 - 5*30 + 5 = 700 + 1093.75 - 150 + 5 = 1648.75
        # TDEE = 1648.75 * 1.375 = 2267.03
        assert result["daily_calorie_goal"] == 2267
        assert result["protein_g"] == 140.0  # 70 * 2
        assert result["fat_g"] == 63.0  # 70 * 0.9
        # C = (2267 - 140*4 - 63*9) / 4 = (2267 - 560 - 567) / 4 = 1140 / 4 = 285
        assert abs(result["carbs_g"] - 285.0) < 0.1

    def test_tdee_02_standard_male_lose(self):
        """標準男性（減量 -500）"""
        result = calculate_tdee(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="1.375",
            diet_goal="lose",
        )
        # TDEE - 500 = 2267 - 500 = 1767
        assert result["daily_calorie_goal"] == 1767
        assert result["protein_g"] == 140.0
        assert result["fat_g"] == 63.0
        # C = (1767 - 560 - 567) / 4 = 640 / 4 = 160
        assert abs(result["carbs_g"] - 160.0) < 0.1

    def test_tdee_03_standard_male_gain(self):
        """標準男性（増量 +500）"""
        result = calculate_tdee(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="1.375",
            diet_goal="gain",
        )
        # TDEE + 500 = 2267 + 500 = 2767
        assert result["daily_calorie_goal"] == 2767
        assert result["protein_g"] == 140.0
        assert result["fat_g"] == 63.0
        # C = (2767 - 560 - 567) / 4 = 1640 / 4 = 410
        assert abs(result["carbs_g"] - 410.0) < 0.1

    def test_tdee_04_standard_female(self):
        """標準女性"""
        result = calculate_tdee(
            gender="female",
            age=25,
            height_cm=165,
            weight_kg=55,
            activity_level="1.55",
            diet_goal="maintain",
        )
        # BMR = 10*55 + 6.25*165 - 5*25 - 161 = 550 + 1031.25 - 125 - 161 = 1295.25
        # TDEE = 1295.25 * 1.55 = 2007.64
        assert result["daily_calorie_goal"] == 2007
        assert result["protein_g"] == 110.0  # 55 * 2
        assert result["fat_g"] == 49.5  # 55 * 0.9

    def test_tdee_05_sedentary(self):
        """ほぼ運動しない（1.2）"""
        result = calculate_tdee(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="1.2",
            diet_goal="maintain",
        )
        # BMR = 1648.75
        # TDEE = 1648.75 * 1.2 = 1978.5
        assert result["daily_calorie_goal"] == 1978

    def test_tdee_06_active(self):
        """活発（1.725）"""
        result = calculate_tdee(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="1.725",
            diet_goal="maintain",
        )
        # BMR = 1648.75
        # TDEE = 1648.75 * 1.725 = 2844.09
        assert result["daily_calorie_goal"] == 2844

    def test_tdee_07_carbs_negative_floor(self):
        """carbs_gが負になる場合は0にfloor"""
        # 極端な条件でcarbsが負になるケース
        result = calculate_tdee(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=100,  # 体重100kg -> P=200g, F=90g
            activity_level="1.2",
            diet_goal="lose",  # -500
        )
        # BMR = 10*100 + 6.25*175 - 5*30 + 5 = 1000 + 1093.75 - 150 + 5 = 1948.75
        # TDEE = 1948.75 * 1.2 = 2338.5
        # Goal = 2338.5 - 500 = 1838.5
        # P*4 + F*9 = 200*4 + 90*9 = 800 + 810 = 1610
        # C = (1838.5 - 1610) / 4 = 57.125（まだ正）
        assert result["carbs_g"] >= 0


class TestCalculateRemaining:
    """calculate_remaining()のテスト"""

    def test_rem_01_no_records(self, v3_db_session):
        """当日レコード0件"""
        configs = {
            "GENDER": "male",
            "AGE": "30",
            "HEIGHT_CM": "175",
            "WEIGHT_KG": "70",
            "ACTIVITY_LEVEL": "1.375",
            "DIET_GOAL": "maintain",
        }
        result = calculate_remaining("user123", date(2026, 3, 20), configs, v3_db_session)

        assert result["goal"]["daily_calorie_goal"] == 2267
        assert result["consumed"]["calorie"] == 0
        assert result["remaining"]["calorie"] == 2267
        assert result["remaining"]["protein_g"] == 140.0
        assert result["remaining"]["fat_g"] == 63.0

    def test_rem_02_single_record(self, v3_db_session):
        """1件のレコード"""
        # レコード作成（JST naive）
        from datetime import datetime

        configs = {
            "GENDER": "male",
            "AGE": "30",
            "HEIGHT_CM": "175",
            "WEIGHT_KG": "70",
            "ACTIVITY_LEVEL": "1.375",
            "DIET_GOAL": "maintain",
        }

        v3_db_session.add(
            CalorieRecord(
                user_id="user123",
                uploaded_at=datetime(2026, 3, 20, 12, 0),
                food_name="テスト食事",
                calorie=500,
                protein_g=20,
                fat_g=15,
                carbs_g=60,
                llm_raw_response_json="{}",
                provider="openai",
            )
        )
        v3_db_session.flush()

        result = calculate_remaining("user123", date(2026, 3, 20), configs, v3_db_session)

        assert result["consumed"]["calorie"] == 500
        assert result["consumed"]["protein_g"] == 20
        assert result["remaining"]["calorie"] == 1767  # 2267 - 500
        assert result["remaining"]["protein_g"] == 120.0  # 140 - 20

    def test_rem_03_multiple_records(self, v3_db_session):
        """3件のレコード"""
        from datetime import datetime

        configs = {
            "GENDER": "male",
            "AGE": "30",
            "HEIGHT_CM": "175",
            "WEIGHT_KG": "70",
            "ACTIVITY_LEVEL": "1.375",
            "DIET_GOAL": "maintain",
        }

        # 3件追加
        for i in range(3):
            v3_db_session.add(
                CalorieRecord(
                    user_id="user123",
                    uploaded_at=datetime(2026, 3, 20, 8 + i * 4, 0),
                    food_name=f"食事{i + 1}",
                    calorie=400,
                    protein_g=15,
                    fat_g=10,
                    carbs_g=50,
                    llm_raw_response_json="{}",
                    provider="openai",
                )
            )
        v3_db_session.flush()

        result = calculate_remaining("user123", date(2026, 3, 20), configs, v3_db_session)

        assert result["consumed"]["calorie"] == 1200  # 400 * 3
        assert result["consumed"]["protein_g"] == 45  # 15 * 3
        assert result["remaining"]["calorie"] == 1067  # 2267 - 1200

    def test_rem_04_exceeds_goal(self, v3_db_session):
        """目標超過時は0にfloor"""
        from datetime import datetime

        configs = {
            "GENDER": "male",
            "AGE": "30",
            "HEIGHT_CM": "175",
            "WEIGHT_KG": "70",
            "ACTIVITY_LEVEL": "1.375",
            "DIET_GOAL": "maintain",
        }

        # 目標超過するレコード
        v3_db_session.add(
            CalorieRecord(
                user_id="user123",
                uploaded_at=datetime(2026, 3, 20, 12, 0),
                food_name="超大食",
                calorie=3000,
                protein_g=200,
                fat_g=100,
                carbs_g=300,
                llm_raw_response_json="{}",
                provider="openai",
            )
        )
        v3_db_session.flush()

        result = calculate_remaining("user123", date(2026, 3, 20), configs, v3_db_session)

        assert result["consumed"]["calorie"] == 3000
        assert result["remaining"]["calorie"] == 0  # max(0, 2267 - 3000)
        assert result["remaining"]["protein_g"] == 0  # max(0, 140 - 200)

    def test_rem_05_null_handling(self, v3_db_session):
        """PFCがNULLのレコードは0として扱う"""
        from datetime import datetime

        configs = {
            "GENDER": "male",
            "AGE": "30",
            "HEIGHT_CM": "175",
            "WEIGHT_KG": "70",
            "ACTIVITY_LEVEL": "1.375",
            "DIET_GOAL": "maintain",
        }

        # PFCがNULLのレコード（既存データ想定）
        v3_db_session.add(
            CalorieRecord(
                user_id="user123",
                uploaded_at=datetime(2026, 3, 20, 12, 0),
                food_name="古い記録",
                calorie=500,
                protein_g=None,
                fat_g=None,
                carbs_g=None,
                llm_raw_response_json="{}",
                provider="openai",
            )
        )
        v3_db_session.flush()

        result = calculate_remaining("user123", date(2026, 3, 20), configs, v3_db_session)

        assert result["consumed"]["calorie"] == 500
        assert result["consumed"]["protein_g"] == 0  # NULLは0
        assert result["consumed"]["fat_g"] == 0
        assert result["consumed"]["carbs_g"] == 0

    def test_rem_06_date_boundary(self, v3_db_session):
        """日付境界のテスト（当日のみ集計）"""
        from datetime import datetime

        configs = {
            "GENDER": "male",
            "AGE": "30",
            "HEIGHT_CM": "175",
            "WEIGHT_KG": "70",
            "ACTIVITY_LEVEL": "1.375",
            "DIET_GOAL": "maintain",
        }

        # 前日のレコード
        v3_db_session.add(
            CalorieRecord(
                user_id="user123",
                uploaded_at=datetime(2026, 3, 19, 23, 59),
                food_name="前日",
                calorie=1000,
                protein_g=50,
                fat_g=30,
                carbs_g=100,
                llm_raw_response_json="{}",
                provider="openai",
            )
        )
        # 当日のレコード
        v3_db_session.add(
            CalorieRecord(
                user_id="user123",
                uploaded_at=datetime(2026, 3, 20, 0, 1),
                food_name="当日",
                calorie=500,
                protein_g=20,
                fat_g=15,
                carbs_g=60,
                llm_raw_response_json="{}",
                provider="openai",
            )
        )
        # 翌日のレコード
        v3_db_session.add(
            CalorieRecord(
                user_id="user123",
                uploaded_at=datetime(2026, 3, 21, 0, 1),
                food_name="翌日",
                calorie=300,
                protein_g=10,
                fat_g=5,
                carbs_g=40,
                llm_raw_response_json="{}",
                provider="openai",
            )
        )
        v3_db_session.flush()

        result = calculate_remaining("user123", date(2026, 3, 20), configs, v3_db_session)

        # 当日のみ集計
        assert result["consumed"]["calorie"] == 500
        assert result["consumed"]["protein_g"] == 20
