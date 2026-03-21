"""
v0.3.2 Block Kit UIの単体テスト
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.slack_ui import _build_calorie_with_remaining_blocks

JST = ZoneInfo("Asia/Tokyo")


class TestBuildCalorieWithRemainingBlocks:
    """_build_calorie_with_remaining_blocks()のテスト"""

    def test_ui_01_normal_remaining_data(self):
        """正常なremaining_dataでBlock Kit JSONが生成される"""
        items = [
            {"food_name": "テスト食事", "calorie": 500, "protein_g": 25, "fat_g": 15, "carbs_g": 60}
        ]
        remaining_data = {
            "goal": {
                "daily_calorie_goal": 2267,
                "protein_g": 140.0,
                "fat_g": 63.0,
                "carbs_g": 285.0,
            },
            "consumed": {"calorie": 500, "protein_g": 25, "fat_g": 15, "carbs_g": 60},
            "remaining": {
                "calorie": 1767,
                "protein_g": 115.0,
                "fat_g": 48.0,
                "carbs_g": 225.0,
            },
        }
        advice = "良い調子です！"

        blocks = _build_calorie_with_remaining_blocks(
            items, datetime.now(JST), remaining_data, advice
        )

        # Block Kit基本構造
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        assert blocks[0]["type"] in ("section", "header")

        # キーワード確認
        block_text = str(blocks)
        assert "本日の摂取サマリー" in block_text
        assert "🍽️" in block_text or "今回の食事" in block_text
        assert "📈" in block_text or "本日の合計" in block_text
        assert "✅" in block_text or "残りの摂取許容値" in block_text
        assert "💬" in block_text or "アドバイス" in block_text

    def test_ui_02_remaining_zero(self):
        """残り=0の場合の表示"""
        items = [
            {"food_name": "テスト", "calorie": 2267, "protein_g": 140, "fat_g": 63, "carbs_g": 285}
        ]
        remaining_data = {
            "goal": {
                "daily_calorie_goal": 2267,
                "protein_g": 140.0,
                "fat_g": 63.0,
                "carbs_g": 285.0,
            },
            "consumed": {"calorie": 2267, "protein_g": 140, "fat_g": 63, "carbs_g": 285.0},
            "remaining": {"calorie": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0},
        }
        advice = "目標達成です！"

        blocks = _build_calorie_with_remaining_blocks(
            items, datetime.now(JST), remaining_data, advice
        )

        block_text = str(blocks)
        # 残り=0でもエラーにならない
        assert "0" in block_text or "達成" in block_text

    def test_ui_03_multiple_items(self):
        """複数itemsの表示"""
        items = [
            {"food_name": "朝食", "calorie": 400, "protein_g": 20, "fat_g": 10, "carbs_g": 50},
            {"food_name": "昼食", "calorie": 600, "protein_g": 30, "fat_g": 20, "carbs_g": 70},
        ]
        remaining_data = {
            "goal": {
                "daily_calorie_goal": 2267,
                "protein_g": 140.0,
                "fat_g": 63.0,
                "carbs_g": 285.0,
            },
            "consumed": {"calorie": 1000, "protein_g": 50, "fat_g": 30, "carbs_g": 120},
            "remaining": {"calorie": 1267, "protein_g": 90.0, "fat_g": 33.0, "carbs_g": 165.0},
        }
        advice = "順調です！"

        blocks = _build_calorie_with_remaining_blocks(
            items, datetime.now(JST), remaining_data, advice
        )

        block_text = str(blocks)
        # 複数品目が表示されている
        assert "朝食" in block_text or "昼食" in block_text

    def test_ui_pfc_displayed(self):
        """PFC（タンパク質・脂質・炭水化物）が表示される"""
        items = [
            {"food_name": "テスト", "calorie": 500, "protein_g": 25, "fat_g": 15, "carbs_g": 60}
        ]
        remaining_data = {
            "goal": {"daily_calorie_goal": 2000, "protein_g": 100, "fat_g": 50, "carbs_g": 200},
            "consumed": {"calorie": 500, "protein_g": 25, "fat_g": 15, "carbs_g": 60},
            "remaining": {"calorie": 1500, "protein_g": 75, "fat_g": 35, "carbs_g": 140},
        }
        advice = "テスト"

        blocks = _build_calorie_with_remaining_blocks(
            items, datetime.now(JST), remaining_data, advice
        )

        block_text = str(blocks)
        assert "タンパク質" in block_text or "P" in block_text
        assert "脂質" in block_text or "F" in block_text
        assert "炭水化物" in block_text or "C" in block_text
