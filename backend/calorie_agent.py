"""LLM adapter for /cal image analysis with Structured Outputs."""

import base64

from pydantic import BaseModel, field_validator

from backend.llm_client import LLMClientConfig


class CalorieAgentError(RuntimeError):
    """General calorie agent error."""


class CalorieConfigError(CalorieAgentError):
    """Configuration error for calorie agent."""


class CalorieImageParseError(CalorieAgentError):
    """Image parsing / JSON parsing error."""


# JSON Schemas for OpenAI Structured Outputs (additionalProperties: false is required)
_FOOD_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "food_name": {
            "type": "string",
            "description": "Name of the food item in Japanese (必ず日本語で)",
        },
        "calorie": {"type": "integer", "description": "Calories in kcal"},
        "protein_g": {"type": "number", "description": "Protein in grams (小数点1桁)"},
        "fat_g": {"type": "number", "description": "Fat in grams (小数点1桁)"},
        "carbs_g": {"type": "number", "description": "Carbohydrates in grams (小数点1桁)"},
    },
    "required": ["food_name", "calorie", "protein_g", "fat_g", "carbs_g"],
    "additionalProperties": False,
}

_CALORIE_ANALYSIS_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "items": {
            "type": "array",
            "items": _FOOD_ITEM_SCHEMA,
            "description": "List of food items in the meal",
        },
        "total_calorie": {"type": "integer", "description": "Total calories in kcal"},
        "total_protein_g": {"type": "number", "description": "Total protein in grams (小数点1桁)"},
        "total_fat_g": {"type": "number", "description": "Total fat in grams (小数点1桁)"},
        "total_carbs_g": {
            "type": "number",
            "description": "Total carbohydrates in grams (小数点1桁)",
        },
    },
    "required": [
        "schema_version",
        "items",
        "total_calorie",
        "total_protein_g",
        "total_fat_g",
        "total_carbs_g",
    ],
    "additionalProperties": False,
}


def _round_to_one_decimal(value: float) -> float:
    """Round to 1 decimal place."""
    return round(value, 1)


# Pydantic schemas for data validation
class FoodItem(BaseModel):
    """Single food item with calorie and PFC information."""

    food_name: str
    calorie: int
    protein_g: float
    fat_g: float
    carbs_g: float

    @field_validator("protein_g", "fat_g", "carbs_g", mode="before")
    @classmethod
    def round_pfc_values(cls, v: float) -> float:
        """Round PFC values to 1 decimal place."""
        return _round_to_one_decimal(v)


class CalorieAnalysisResult(BaseModel):
    """Complete calorie analysis result with PFC breakdown."""

    schema_version: str = "calorie_v2"
    items: list[FoodItem]
    total_calorie: int
    total_protein_g: float
    total_fat_g: float
    total_carbs_g: float

    @field_validator("total_protein_g", "total_fat_g", "total_carbs_g", mode="before")
    @classmethod
    def round_total_pfc_values(cls, v: float) -> float:
        """Round total PFC values to 1 decimal place."""
        return _round_to_one_decimal(v)

    @classmethod
    def model_json_schema(cls) -> dict:
        """Return JSON schema compatible with OpenAI Structured Outputs."""
        return _CALORIE_ANALYSIS_RESULT_SCHEMA


class CalorieAnalyzer:
    """Calorie analyzer using OpenAI Structured Outputs."""

    def __init__(self, provider: str = "openai") -> None:
        """Initialize analyzer with specified provider.

        Args:
            provider: "openai" or "gemini"
        """
        self.provider = provider
        config = LLMClientConfig(provider)
        self.client = config.client
        self.model = config.get_model_for_purpose("image")

    def analyze(self, image_bytes: bytes, mime_type: str) -> CalorieAnalysisResult:
        """Analyze meal image and return calorie + PFC breakdown.

        Args:
            image_bytes: Image data
            mime_type: MIME type (e.g., "image/jpeg")

        Returns:
            CalorieAnalysisResult with PFC information
        """
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{image_b64}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "画像内の食事を解析し、カロリーとPFC（タンパク質・脂質・炭水化物）を推定してください。\n"
                                "複数の料理がある場合はそれぞれの分も推定してください。\n\n"
                                "重要:\n"
                                "- 食品名は必ず日本語で出力してください（例: 「牛肉ステーキ」「白ごはん」「サラダ」）\n"
                                "- PFC値は小数点第1位までで出力してください（例: 25.5g）"
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "calorie_analysis",
                    "strict": True,
                    "schema": _CALORIE_ANALYSIS_RESULT_SCHEMA,
                },
            },
        )

        content = response.choices[0].message.content
        return CalorieAnalysisResult.model_validate_json(content)


def analyze_calorie(
    image_bytes: bytes, mime_type: str, provider: str = "openai"
) -> tuple[CalorieAnalysisResult, str, str, str]:
    """Analyze meal image and return calorie + PFC breakdown.

    Convenience function that creates CalorieAnalyzer and calls analyze().
    Returns (result, raw_json, provider, model) tuple for compatibility.

    Args:
        image_bytes: Image data
        mime_type: MIME type (e.g., "image/jpeg")
        provider: "openai" or "gemini"

    Returns:
        Tuple of (CalorieAnalysisResult, raw_json, provider, model)
    """
    analyzer = CalorieAnalyzer(provider=provider)
    result = analyzer.analyze(image_bytes, mime_type)
    raw_json = result.model_dump_json()
    return result, raw_json, provider, analyzer.model
