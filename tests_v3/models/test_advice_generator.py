"""
v0.3.2 アドバイス生成モジュールの単体テスト
"""

import os

import pytest

from backend.advice_generator import AdviceGenerator


@pytest.mark.integration
class TestAdviceGenerator:
    """AdviceGeneratorクラスのテスト（APIキー必要）"""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_adv_01_remaining_sufficient(self):
        """残り十分 - 1-2文の励まし"""
        generator = AdviceGenerator(character="標準")

        remaining = {"calorie": 1500, "protein_g": 90, "fat_g": 40, "carbs_g": 180}
        consumed = {"calorie": 500, "protein_g": 40, "fat_g": 20, "carbs_g": 60}
        goal = {"calorie": 2000, "protein_g": 130, "fat_g": 60, "carbs_g": 240}

        advice = generator.generate(remaining, consumed, goal)

        assert isinstance(advice, str)
        assert len(advice) > 0
        assert len(advice.split("\n")) <= 2  # 1-2文

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_adv_02_remaining_low(self):
        """残り少ない - キャラクター口調の警告"""
        generator = AdviceGenerator(character="うる星やつらのラムちゃん")

        remaining = {"calorie": 200, "protein_g": 10, "fat_g": 5, "carbs_g": 20}
        consumed = {"calorie": 1800, "protein_g": 120, "fat_g": 55, "carbs_g": 220}
        goal = {"calorie": 2000, "protein_g": 130, "fat_g": 60, "carbs_g": 240}

        advice = generator.generate(remaining, consumed, goal)

        assert isinstance(advice, str)
        assert len(advice) > 0

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_adv_03_exceeded_goal(self):
        """目標超過 - 超過時のメッセージ"""
        generator = AdviceGenerator(character="コーチ")

        remaining = {"calorie": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}
        consumed = {"calorie": 2500, "protein_g": 150, "fat_g": 70, "carbs_g": 300}
        goal = {"calorie": 2000, "protein_g": 130, "fat_g": 60, "carbs_g": 240}

        advice = generator.generate(remaining, consumed, goal)

        assert isinstance(advice, str)
        assert len(advice) > 0

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_adv_04_remaining_zero(self):
        """残り=0 - 目標達成のメッセージ"""
        generator = AdviceGenerator(character="うる星やつらのラムちゃん")

        remaining = {"calorie": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}
        consumed = {"calorie": 2000, "protein_g": 130, "fat_g": 60, "carbs_g": 240}
        goal = {"calorie": 2000, "protein_g": 130, "fat_g": 60, "carbs_g": 240}

        advice = generator.generate(remaining, consumed, goal)

        assert isinstance(advice, str)
        assert len(advice) > 0
