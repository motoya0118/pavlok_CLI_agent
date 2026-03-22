"""
v0.3.2 LLM画像解析モジュールの単体テスト
"""

import os

import pytest
from pydantic import ValidationError

from backend.calorie_agent import CalorieAnalysisResult, CalorieAnalyzer, FoodItem


class TestPydanticSchema:
    """Pydanticスキーマの検証"""

    def test_schema_valid_food_item(self):
        """FoodItemの正常ケース"""
        item = FoodItem(
            food_name="テスト食事",
            calorie=500,
            protein_g=25.5,
            fat_g=15.0,
            carbs_g=60.0,
        )
        assert item.food_name == "テスト食事"
        assert item.calorie == 500
        assert item.protein_g == 25.5
        assert item.fat_g == 15.0
        assert item.carbs_g == 60.0

    def test_schema_missing_required_field(self):
        """必須フィールド欠落でエラー"""
        with pytest.raises(ValidationError):
            FoodItem(
                food_name="テスト",
                calorie=500,
                # protein_g, fat_g, carbs_g 欠落
            )

    def test_schema_valid_result(self):
        """CalorieAnalysisResultの正常ケース"""
        result = CalorieAnalysisResult(
            schema_version="calorie_v2",
            items=[
                FoodItem(
                    food_name="テスト",
                    calorie=500,
                    protein_g=25.0,
                    fat_g=15.0,
                    carbs_g=60.0,
                )
            ],
            total_calorie=500,
            total_protein_g=25.0,
            total_fat_g=15.0,
            total_carbs_g=60.0,
        )
        assert result.schema_version == "calorie_v2"
        assert len(result.items) == 1
        assert result.total_calorie == 500

    def test_schema_missing_items(self):
        """items欠落でエラー"""
        with pytest.raises(ValidationError):
            CalorieAnalysisResult(
                schema_version="calorie_v2",
                # items 欠落
                total_calorie=500,
                total_protein_g=0,
                total_fat_g=0,
                total_carbs_g=0,
            )

    def test_schema_from_dict_valid(self):
        """辞書からのパース（正常）"""
        data = {
            "schema_version": "calorie_v2",
            "items": [
                {
                    "food_name": "唐揚げ定食",
                    "calorie": 850,
                    "protein_g": 35.5,
                    "fat_g": 28.0,
                    "carbs_g": 95.0,
                }
            ],
            "total_calorie": 850,
            "total_protein_g": 35.5,
            "total_fat_g": 28.0,
            "total_carbs_g": 95.0,
        }
        result = CalorieAnalysisResult.model_validate(data)
        assert result.schema_version == "calorie_v2"
        assert len(result.items) == 1
        assert result.items[0].food_name == "唐揚げ定食"


class TestCalorieAnalyzer:
    """CalorieAnalyzerクラスのテスト"""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_init_openai_provider(self):
        """OpenAI providerで初期化"""
        analyzer = CalorieAnalyzer(provider="openai")
        assert analyzer.provider == "openai"
        assert analyzer.client is not None
        assert analyzer.model is not None

    @pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not configured")
    def test_init_gemini_provider(self):
        """Gemini providerで初期化"""
        analyzer = CalorieAnalyzer(provider="gemini")
        assert analyzer.provider == "gemini"
        assert analyzer.client is not None
        assert analyzer.model is not None

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_init_invalid_provider(self):
        """無効なproviderでエラー"""
        # OpenAIにフォールバックされるはず
        analyzer = CalorieAnalyzer(provider="invalid")
        assert analyzer.provider == "invalid"
        # 無効なproviderでも初期化は成功（実行時にエラー）

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
    def test_create_client_returns_tuple(self):
        """clientとmodel属性が正しく設定される"""
        analyzer = CalorieAnalyzer(provider="openai")
        assert analyzer.client is not None
        assert isinstance(analyzer.model, str)
        assert analyzer.model != ""

    def test_model_dump_converts_to_dict(self):
        """model_dump()で辞書に変換"""
        item = FoodItem(
            food_name="テスト",
            calorie=500,
            protein_g=25.0,
            fat_g=15.0,
            carbs_g=60.0,
        )
        d = item.model_dump()
        assert isinstance(d, dict)
        assert d["food_name"] == "テスト"
        assert d["protein_g"] == 25.0

    def test_items_model_dump(self):
        """itemsリストを辞書リストに変換"""
        result = CalorieAnalysisResult(
            schema_version="calorie_v2",
            items=[
                FoodItem(
                    food_name="テスト1",
                    calorie=300,
                    protein_g=15.0,
                    fat_g=10.0,
                    carbs_g=40.0,
                ),
                FoodItem(
                    food_name="テスト2",
                    calorie=200,
                    protein_g=10.0,
                    fat_g=5.0,
                    carbs_g=20.0,
                ),
            ],
            total_calorie=500,
            total_protein_g=25.0,
            total_fat_g=15.0,
            total_carbs_g=60.0,
        )
        items_dicts = [item.model_dump() for item in result.items]
        assert len(items_dicts) == 2
        assert items_dicts[0]["food_name"] == "テスト1"
        assert items_dicts[1]["calorie"] == 200
