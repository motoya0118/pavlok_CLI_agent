# Issue #002: /cal 画像解析時の OpenAI Structured Outputs スキーマエラー

## 概要

`/cal` コマンドで食事画像を送信した際、OpenAI Structured Outputs のスキーマバリデーションエラーが発生します。

## エラーメッセージ

```
openai.BadRequestError: Error code: 400 - {'error': {'message': "Invalid schema for response_format 'calorie_analysis': In context=(), 'additionalProperties' is required to be supplied and to be false.", 'type': 'invalid_request_error', 'param': 'response_format', 'code': None}}
```

## 原因

`backend/calorie_agent.py` の `CalorieAnalysisResult` および `FoodItem` Pydanticモデルが、`model_json_schema()` を使用してスキーマを生成していますが、OpenAI Structured Outputs では全てのオブジェクトに `additionalProperties: false` が必須です。

Pydanticのデフォルトスキーマ生成では `additionalProperties` が含まれないため、OpenAI API でバリデーションエラーが発生します。

## 修正案

`FoodItem` と `CalorieAnalysisResult` のスキーマを手動で定義し、`additionalProperties: false` を追加します。

### 修正箇所: `backend/calorie_agent.py`

```python
# 手動で定義したJSON Schema（additionalProperties: false必須）
_FOOD_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "food_name": {"type": "string"},
        "calorie": {"type": "integer"},
        "protein_g": {"type": "number"},
        "fat_g": {"type": "number"},
        "carbs_g": {"type": "number"},
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
        },
        "total_calorie": {"type": "integer"},
        "total_protein_g": {"type": "number"},
        "total_fat_g": {"type": "number"},
        "total_carbs_g": {"type": "number"},
    },
    "required": ["schema_version", "items", "total_calorie", "total_protein_g", "total_fat_g", "total_carbs_g"],
    "additionalProperties": False,
}
```

## 優先度

**高** - `/cal` コマンドが機能しないため、ユーザーが食事記録できない

## 担当

TODO: 割り当てられていない

## ステータス

RESOLVED ✅

## 修正内容

`backend/calorie_agent.py` で手動で定義したJSON Schemaを作成し、`additionalProperties: False` を追加:

- `_FOOD_ITEM_SCHEMA`: FoodItem用スキーマ
- `_CALORIE_ANALYSIS_RESULT_SCHEMA`: CalorieAnalysisResult用スキーマ
- `CalorieAnalysisResult.model_json_schema()` をオーバーライドして手動スキーマを返すように変更

## 修正日

2026-03-20

## 作成日

2026-03-20
