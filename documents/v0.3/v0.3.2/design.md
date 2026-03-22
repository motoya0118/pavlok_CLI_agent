# v0.3.2 設計書 - PFCバランス管理機能

## 1. 概要

v0.3.2では、既存の`/cal`コマンドをエンハンスし、PFC（タンパク質・脂質・炭水化物）バランス形式での1日の摂取目標管理機能を追加する。

### 主要な変更点
1. **ユーザー体組成・活動量設定**: `/config`で性別、年齢、身長、体重、運動頻度を登録可能に
2. **TDEE計算機能**: Mifflin-St Jeor式と活動係数による1日推定消費カロリー計算
3. **PFC分解**: タンパク質・脂質・炭水化物の目標値計算
4. **画像解析のPFC対応**: LLMにPFC情報を出力させる（Structured Outputs）
5. **残り摂取許容値の表示**: 1日目標 - 当日摂取分 = 残り許容値のリアルタイム表示

---

## 2. 要件定義

### 2.1 機能要件

| ID | 機能 | 説明 |
|----|------|------|
| F1 | 体組成設定 | `/config`で性別、年齢、身長、体重、運動頻度を設定可能にする |
| F2 | TDEE計算 | Mifflin-St Jeor式と活動係数から1日推定消費カロリーを計算する |
| F3 | 目的別カロリー設定 | 減量（-500kcal）、維持（±0）、増量（+500kcal）を選択可能にする |
| F4 | PFC分解 | 体重ベースのタンパク質、脂質、残りを炭水化物として目標値を算出する |
| F5 | 画像解析PFC出力 | `/cal`のLLMプロンプトを更新し、PFC情報も出力させる |
| F6 | カロリー記録PFC保存 | CalorieRecordテーブルにPFC情報を保存する |
| F7 | 残り許容値計算 | 1日目標 - 当日合計摂取 = 残り許容値を計算する |
| F8 | 残り許容値表示 | `/cal`実行後に残りカロリー・PFCとアドバイスを表示する |

### 2.2 非機能要件

| ID | 要件 | 説明 |
|----|------|------|
| N1 | 計算精度 | TDEE計算は一般的な誤差範囲（±10%）内であること |
| N2 | レスポンス時間 | `/cal`の解析処理はv0.3.1と同様、非同期で3秒以内にACKを返すこと |
| N3 | データ整合性 | 同一日の複数回`/cal`実行時に正しく合算されること |
| N4 | 体組成設定必須 | 設定未完了の場合は画像解析を実行せず、エラーを返すこと |

---

## 3. データベース設計

### 3.1 configurations テーブル追加項目

| key | value_type | default | valid_values | min | max | 説明 |
|-----|------------|---------|--------------|-----|-----|------|
| `GENDER` | STR | - | male, female | - | - | 性別 |
| `AGE` | INT | 30 | - | 10 | 100 | 年齢 |
| `HEIGHT_CM` | INT | 170 | - | 100 | 250 | 身長(cm) |
| `WEIGHT_KG` | FLOAT | 65.0 | - | 30 | 200 | 体重(kg) |
| `ACTIVITY_LEVEL` | STR | 1.375 | 1.2, 1.375, 1.55, 1.725 | - | - | 活動係数 |
| `DIET_GOAL` | STR | maintain | lose, maintain, gain | - | - | 目的（減量/維持/増量） |

### 3.2 calorie_records テーブル追加カラム

| カラム名 | 型 | NULL | 説明 |
|----------|-----|------|------|
| `protein_g` | FLOAT | ○ | タンパク質(g) |
| `fat_g` | FLOAT | ○ | 脂質(g) |
| `carbs_g` | FLOAT | ○ | 炭水化物(g) |

**モデル変更**: `backend/models/__init__.py` の `CalorieRecord` クラス

```python
# v0.3.2追加カラム
protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
```

### 3.3 Migration

**ファイル**: `backend/alembic/versions/v0_3_2_pfc_columns.py`

```python
def upgrade():
    op.add_column('calorie_records', sa.Column('protein_g', sa.Float(), nullable=True))
    op.add_column('calorie_records', sa.Column('fat_g', sa.Float(), nullable=True))
    op.add_column('calorie_records', sa.Column('carbs_g', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('calorie_records', 'carbs_g')
    op.drop_column('calorie_records', 'fat_g')
    op.drop_column('calorie_records', 'protein_g')
```

---

## 4. アーキテクチャ設計

### 4.1 コンポーネント図

```
┌─────────────────────────────────────────────────────────────────┐
│                        Slack                                   │
│  /cal (画像upload) → Modal                                    │
│  /config (体組成設定) → Modal                                  │
└────────────────────┬────────────────────────────────────────────┘
                     │ Webhook
┌────────────────────▼────────────────────────────────────────────┐
│                   FastAPI Backend                              │
│  /slack/command   : /cal, /config 受信                          │
│  /slack/interactive: Modal submit 処理                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│         CalorieAnalyzer (OpenAI Agents SDK)                    │
│         calorie_tdee.py (TDEE/PFC計算)                        │
│         advice_generator.py (アドバイス生成)                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│  OpenAI API      │    │  Gemini API      │
│  gpt-4o-mini     │    │  gemini-3.1-...  │
└──────────────────┘    └──────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│              DB (SQLite + SQLAlchemy)                          │
│  configurations  : 体組成設定                                   │
│  calorie_records : カロリー+PFC記録                             │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 計算フロー

```
[ユーザー体組成設定]
       ↓
[GENDER, AGE, HEIGHT_CM, WEIGHT_KG, ACTIVITY_LEVEL, DIET_GOAL]
       ↓
[Mifflin-St Jeor式]
  男性: 10 × 体重kg + 6.25 × 身長cm - 5 × 年齢 + 5
  女性: 10 × 体重kg + 6.25 × 身長cm - 5 × 年齢 - 161
       ↓
[BMR（基礎代謝）]
       ↓
[TDEE = BMR × 活動係数]
  1.2: ほぼ運動しない
  1.375: 軽い運動（週1-3日）
  1.55: 中程度の運動（週3-5日）
  1.725: 活発（週6-7日）
       ↓
[目的別補正]
  減量: TDEE - 500
  維持: TDEE
  増量: TDEE + 500
       ↓
[1日摂取目標カロリー]
       ↓
[PFC分解]
  P(g) = 体重kg × 2
  F(g) = 体重kg × 0.9
  C(g) = (目標cal - P×4 - F×9) / 4
       ↓
[1日PFC目標値]
```

---

## 5. 実装ガイド

### Phase 1: 体組成設定機能

| タスク | ファイル | 内容 |
|------|---------|------|
| 1.1 | `backend/api/command.py` | `CONFIG_DEFINITIONS`に体組成設定6項目を追加 |
| 1.2 | `backend/slack_ui.py` | `config_modal`に「体組成・活動量」タブを追加 |
| 1.3 | `backend/api/command.py` | `_extract_config_updates_from_view()`にバリデーション追加 |

**実装内容**:

```python
# backend/api/command.py CONFIG_DEFINITIONS追加
CONFIG_DEFINITIONS: dict[str, dict[str, Any]] = {
    # 既存...
    "GENDER": {
        "default": "-",
        "value_type": ConfigValueType.STR,
        "allowed": {"male", "female"},
    },
    "AGE": {
        "default": "30",
        "value_type": ConfigValueType.INT,
        "min": 10,
        "max": 100,
    },
    "HEIGHT_CM": {
        "default": "170",
        "value_type": ConfigValueType.INT,
        "min": 100,
        "max": 250,
    },
    "WEIGHT_KG": {
        "default": "65.0",
        "value_type": ConfigValueType.FLOAT,
        "min": 30,
        "max": 200,
    },
    "ACTIVITY_LEVEL": {
        "default": "1.375",
        "value_type": ConfigValueType.STR,
        "allowed": {"1.2", "1.375", "1.55", "1.725"},
    },
    "DIET_GOAL": {
        "default": "maintain",
        "value_type": ConfigValueType.STR,
        "allowed": {"lose", "maintain", "gain"},
    },
}
```

### Phase 2: TDEE/PFC計算モジュール

| タスク | ファイル | 内容 |
|------|---------|------|
| 2.1 | `backend/calorie_tdee.py`（新規） | `calculate_tdee()`関数実装 |
| 2.2 | `backend/calorie_tdee.py` | `calculate_remaining()`関数実装 |
| 2.3 | `tests_v3/models/test_calorie_tdee.py`（新規） | 単体テスト |

**実装内容**:

```python
# backend/calorie_tdee.py
from datetime import date
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

def calculate_tdee(
    gender: str, age: int, height_cm: int, weight_kg: float,
    activity_level: str, diet_goal: str,
) -> dict:
    # Mifflin-St Jeor式
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    tdee = bmr * float(activity_level)
    goal_adj = {"lose": -500, "maintain": 0, "gain": 500}
    daily_calorie_goal = tdee + goal_adj[diet_goal]

    # PFC分解
    protein_g = weight_kg * 2.0
    fat_g = weight_kg * 0.9
    remaining_calories = daily_calorie_goal - (protein_g * 4) - (fat_g * 9)
    carbs_g = max(0, remaining_calories / 4)

    return {
        "daily_calorie_goal": int(daily_calorie_goal),
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
    }

def calculate_remaining(
    user_id: str, target_date: date, session,
) -> dict:
    # 既存の_load_user_config_valuesを利用して設定取得
    # calculate_tdee()で目標計算
    # calorie_recordsから当日分集計
    # 残り = 目標 - 集計
    ...
```

### Phase 3: LLM画像解析（OpenAI Agents SDK）

| タスク | ファイル | 内容 |
|------|---------|------|
| 3.1 | `backend/calorie_agent.py`（再実装） | `CalorieAnalyzer`クラス実装 |
| 3.2 | `backend/calorie_agent.py` | Pydanticスキーマ定義 |
| 3.3 | `backend/calorie_agent.py` | Structured Outputs (`json_schema`, `strict=True`) |
| 3.4 | `tests_v3/models/test_calorie_agent.py` | Gemini OpenAI互換EP検証 |

**実装内容**:

```python
# backend/calorie_agent.py
import base64
import os
from pydantic import BaseModel
from openai import OpenAI

class FoodItem(BaseModel):
    food_name: str
    calorie: int
    protein_g: float
    fat_g: float
    carbs_g: float

class CalorieAnalysisResult(BaseModel):
    schema_version: str = "calorie_v2"
    items: list[FoodItem]
    total_calorie: int
    total_protein_g: float
    total_fat_g: float
    total_carbs_g: float

class CalorieAnalyzer:
    def __init__(self, provider: str = "openai"):
        self.provider = provider
        self.client, self.model = self._create_client()

    def _create_client(self) -> tuple[OpenAI, str]:
        if self.provider == "openai":
            base_url = "https://api.openai.com/v1"
            api_key = os.getenv("OPENAI_API_KEY")
            model = os.getenv("CALORIE_OPENAI_MODEL", "gpt-4o-mini")
        else:  # gemini
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            api_key = os.getenv("GEMINI_API_KEY")
            model = os.getenv("CALORIE_GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

        client = OpenAI(base_url=base_url, api_key=api_key)
        return client, model

    def analyze(self, image_bytes: bytes, mime_type: str) -> CalorieAnalysisResult:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{image_b64}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "画像内の食事を解析し、カロリーとPFCを推定してください。"},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "calorie_analysis",
                    "strict": True,
                    "schema": CalorieAnalysisResult.model_json_schema()
                }
            }
        )

        return CalorieAnalysisResult.model_validate_json(
            response.choices[0].message.content
        )
```

### Phase 4: /cal処理の拡張

| タスク | ファイル | 内容 |
|------|---------|------|
| 4.1 | `backend/api/interactive.py` | `_run_calorie_submit_job()`先頭で体組成設定チェック |
| 4.2 | `backend/api/interactive.py` | CalorieRecord保存時にPFCも格納 |
| 4.3 | `backend/api/interactive.py` | `calculate_remaining()`で残り計算 |
| 4.4 | `backend/slack_ui.py` | `_build_calorie_with_remaining_blocks()`で残り許容値UI |

**実装内容（体組成設定チェック）**:

```python
# backend/api/interactive.py _run_calorie_submit_job()の先頭に追加

async def _run_calorie_submit_job(...):
    # v0.3.2追加: 体組成設定チェック
    configs = _load_user_config_values(user_id)
    required_keys = ["GENDER", "AGE", "HEIGHT_CM", "WEIGHT_KG", "ACTIVITY_LEVEL", "DIET_GOAL"]
    missing = [k for k in required_keys if not configs.get(k) or configs[k] == "-"]

    if missing:
        await _notify_calorie_result(
            channel_id=channel_id,
            user_id=user_id,
            message=f"先に`/config`で体組成設定を完了してください（不足: {', '.join(missing)}）",
        )
        return

    # 以降、既存の画像解析処理...
```

**実装内容（PFC保存）**:

```python
# backend/api/interactive.py CalorieRecord保存部分

for row in items:
    session.add(
        CalorieRecord(
            user_id=user_id,
            uploaded_at=uploaded_at_jst,
            food_name=str(row["food_name"]),
            calorie=int(row["calorie"]),
            protein_g=float(row.get("protein_g", 0)),  # 追加
            fat_g=float(row.get("fat_g", 0)),          # 追加
            carbs_g=float(row.get("carbs_g", 0)),      # 追加
            llm_raw_response_json=raw_json,
            provider=provider,
            model=model,
        )
    )
```

**実装内容（残り許容値計算＆通知）**:

```python
# backend/api/interactive.py _run_calorie_submit_job()の最後

from backend.calorie_tdee import calculate_remaining
from backend.advice_generator import AdviceGenerator

remaining_data = calculate_remaining(user_id, datetime.now(JST).date(), session)

character = _load_user_config_values(user_id).get("COACH_CHARACTOR", "うる星やつらのラムちゃん")
advice = AdviceGenerator(character).generate(
    remaining=remaining_data["remaining"],
    consumed=remaining_data["consumed"],
    goal=remaining_data["goal"],
)

await _notify_calorie_result(
    channel_id=channel_id,
    user_id=user_id,
    message="カロリー解析結果を記録しました",
    blocks=_build_calorie_with_remaining_blocks(
        items, uploaded_at_jst, remaining_data, advice
    ),
)
```

### Phase 5: アドバイス生成

| タスク | ファイル | 内容 |
|------|---------|------|
| 5.1 | `backend/advice_generator.py`（新規） | `AdviceGenerator`クラス実装 |
| 5.2 | `backend/advice_generator.py` | Structured Outputsでアドバイス生成 |

**実装内容**:

```python
# backend/advice_generator.py
from pydantic import BaseModel
from openai import OpenAI
import os

class MealAdviceRequest(BaseModel):
    advice: str

class AdviceGenerator:
    def __init__(self, character: str = "うる星やつらのラムちゃん"):
        self.character = character
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate(self, remaining: dict, consumed: dict, goal: dict) -> str:
        response = self.client.chat.completions.create(
            model=os.getenv("ADVICE_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": f"あなたは{self.character}です。"
                               "ユーザーの食事管理をサポートするコーチとして、"
                               "1-2文の短い励ましのアドバイスをしてください。"
                },
                {
                    "role": "user",
                    "content": self._build_prompt(remaining, consumed, goal)
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "meal_advice",
                    "strict": True,
                    "schema": MealAdviceRequest.model_json_schema()
                }
            }
        )

        result = MealAdviceRequest.model_validate_json(
            response.choices[0].message.content
        )
        return result.advice
```

### Phase 6: Block Kit UI

| タスク | ファイル | 内容 |
|------|---------|------|
| 6.1 | `backend/slack_ui.py` | `config_modal`に体組成・活動量タブ追加 |
| 6.2 | `backend/slack_ui.py` | `_build_calorie_with_remaining_blocks()`実装 |

**UI表示例**:

```
<@user_id> カロリー解析結果を記録しました

┌─────────────────────────────────────┐
│ 📊 本日の摂取サマリー                  │
├─────────────────────────────────────┤
│ 🍽️ 今回の食事                         │
│  • カロリー: 650 kcal                 │
│  • タンパク質: 25g                    │
│  • 脂質: 18g                         │
│  • 炭水化物: 85g                      │
├─────────────────────────────────────┤
│ 📈 本日の合計                          │
│  • カロリー: 1,450 / 2,000 kcal        │
│  • タンパク質: 85g / 130g             │
│  • 脂質: 45g / 58g                    │
│  • 炭水化物: 180g / 203g              │
├─────────────────────────────────────┤
│ ✅ 残りの摂取許容値                     │
│  • カロリー: 550 kcal                 │
│  • タンパク質: 45g                    │
│  • 脂質: 13g                          │
│  • 炭水化物: 23g                      │
├─────────────────────────────────────┤
│ 💡 アドバイス                         │
│  [キャラクター口調で1-2文のアドバイス]    │
└─────────────────────────────────────┘
```

---

## 6. 環境設定

### 6.1 依存ライブラリ

**ファイル**: `pyproject.toml`

```toml
dependencies = [
    # 既存...
    "openai>=1.60.0",  # Agents SDK / Structured Outputs
]
```

### 6.2 環境変数

**ファイル**: `env-sample` に追加

```bash
# ============================================
# v0.3.2: カロリー解析（PFC対応）
# ============================================

# LLMプロバイダー選択（openai or gemini）
CALORIE_PROVIDER=openai

# OpenAI用（既存のOPENAI_API_KEYを再利用）
CALORIE_OPENAI_MODEL=gpt-4o-mini

# Gemini用（OpenAI互換エンドポイント）
GEMINI_API_KEY=your-gemini-api-key-here
CALORIE_GEMINI_MODEL=gemini-3.1-flash-lite-preview

# アドバイス生成用モデル（省略時はCALORIE_OPENAI_MODELを使用）
ADVICE_MODEL=gpt-4o-mini
```

---

## 7. ファイル構成サマリー

```
backend/
├── api/
│   ├── command.py              # 変更: CONFIG_DEFINITIONS追加、バリデーション
│   └── interactive.py          # 変更: 体組成チェック、PFC保存、残り計算
├── alembic/versions/
│   └── v0_3_2_pfc_columns.py    # 新規: PFCカラム追加
├── models/
│   └── __init__.py             # 変更: CalorieRecordにPFCカラム追加
├── slack_ui.py                 # 変更: config_modal、残り許容値UI
├── calorie_agent.py            # 再実装: OpenAI Agents SDK
├── calorie_tdee.py             # 新規: TDEE/PFC計算
├── advice_generator.py         # 新規: アドバイス生成
tests_v3/
└── models/
    ├── test_calorie_tdee.py    # 新規: TDEE計算テスト
    └── test_calorie_agent.py   # 変更: PFC対応
```

---

## 8. 単体テスト仕様

### 8.1 Phase 2: TDEE/PFC計算モジュール (`test_calorie_tdee.py`)

**ファイル**: `tests_v3/models/test_calorie_tdee.py`

#### 8.1.1 `calculate_tdee()` テストケース

| ケースID | 入力値 | 期待値 | 説明 |
|----------|--------|--------|------|
| TDEE-01 | `gender="male", age=30, height_cm=175, weight_kg=70, activity_level="1.375", diet_goal="maintain"` | `daily_calorie_goal=2448, protein_g=140.0, fat_g=63.0, carbs_g=283.25` | 標準男性（軽い運動、維持） |
| TDEE-02 | `gender="male", age=30, height_cm=175, weight_kg=70, activity_level="1.375", diet_goal="lose"` | `daily_calorie_goal=1948, protein_g=140.0, fat_g=63.0, carbs_g=158.25` | 標準男性（減量-500） |
| TDEE-03 | `gender="male", age=30, height_cm=175, weight_kg=70, activity_level="1.375", diet_goal="gain"` | `daily_calorie_goal=2948, protein_g=140.0, fat_g=63.0, carbs_g=408.25` | 標準男性（増量+500） |
| TDEE-04 | `gender="female", age=25, height_cm=165, weight_kg=55, activity_level="1.55", diet_goal="maintain"` | `daily_calorie_goal=2137, protein_g=110.0, fat_g=49.5, carbs_g=276.0` | 標準女性（中程度運動） |
| TDEE-05 | `gender="male", age=30, height_cm=175, weight_kg=70, activity_level="1.2", diet_goal="maintain"` | `daily_calorie_goal=2139, protein_g=140.0, fat_g=63.0, carbs_g=224.75` | ほぼ運動しない |
| TDEE-06 | `gender="male", age=30, height_cm=175, weight_kg=70, activity_level="1.725", diet_goal="maintain"` | `daily_calorie_goal=3072, protein_g=140.0, fat_g=63.0, carbs_g=439.75` | 活発（週6-7日） |
| TDEE-07 | `gender="male", age=30, height_cm=175, weight_kg=70, activity_level="1.375", diet_goal="lose"` ※carbs_g計算結果が負になるケース | `carbs_g=0` | 炭水化物が負の場合は0にfloor |

**検証方法**:
```python
def test_calculate_tdee_standard_male_maintain():
    result = calculate_tdee(
        gender="male",
        age=30,
        height_cm=175,
        weight_kg=70,
        activity_level="1.375",
        diet_goal="maintain"
    )
    # BMR = 10*70 + 6.25*175 - 5*30 + 5 = 700 + 1093.75 - 150 + 5 = 1648.75
    # TDEE = 1648.75 * 1.375 = 2267.03
    # Goal = 2267.03 + 0 = 2267.03 → int round = 2267
    # P = 70 * 2 = 140
    # F = 70 * 0.9 = 63
    # C = (2267 - 140*4 - 63*9) / 4 = (2267 - 560 - 567) / 4 = 1140 / 4 = 285
    assert result["daily_calorie_goal"] == 2267
    assert result["protein_g"] == 140.0
    assert result["fat_g"] == 63.0
    assert abs(result["carbs_g"] - 285.0) < 0.1
```

#### 8.1.2 `calculate_remaining()` テストケース

| ケースID | 前提条件 | 期待値 | 説明 |
|----------|----------|--------|------|
| REM-01 | 当日のレコード0件 | `remaining_calorie=目標値, remaining_protein=目標値, remaining_fat=目標値, remaining_carbs=目標値` | 初期状態 |
| REM-02 | 当日1件: `{calorie:500, protein_g:20, fat_g:15, carbs_g:60}` | `remaining=目標-各値` | 単純減算 |
| REM-03 | 当日3件の合計 | `remaining=目標-合計値` | 複数件集計 |
| REM-04 | 合計が目標を超過 | `remaining=0`（全項目） | 超過時は0 floor |
| REM-05 | 既存レコードにPFC=NULL | `NULLを0として扱い集計` | NULL handling |
| REM-06 | 異なる日のレコードが存在 | `当日のみ集計、他日は無視` | 日付境界 |

**検証用フィクスチャ**:
```python
@pytest.fixture
def sample_user_with_records(session, user_id="test-user"):
    # 体組成設定
    configs = [
        Configuration(user_id=user_id, key="GENDER", value="male", value_type=ConfigValueType.STR),
        Configuration(user_id=user_id, key="AGE", value="30", value_type=ConfigValueType.INT),
        Configuration(user_id=user_id, key="HEIGHT_CM", value="175", value_type=ConfigValueType.INT),
        Configuration(user_id=user_id, key="WEIGHT_KG", value="70", value_type=ConfigValueType.FLOAT),
        Configuration(user_id=user_id, key="ACTIVITY_LEVEL", value="1.375", value_type=ConfigValueType.STR),
        Configuration(user_id=user_id, key="DIET_GOAL", value="maintain", value_type=ConfigValueType.STR),
    ]
    for c in configs:
        session.add(c)
    session.flush()

    # 当日のカロリー記録（JST）
    today = datetime(2026, 3, 20, 12, 0)
    records = [
        CalorieRecord(
            user_id=user_id, uploaded_at=today, food_name="昼食",
            calorie=500, protein_g=20, fat_g=15, carbs_g=60,
            llm_raw_response_json="{}", provider="openai"
        ),
        CalorieRecord(
            user_id=user_id, uploaded_at=today, food_name="間食",
            calorie=200, protein_g=5, fat_g=10, carbs_g=25,
            llm_raw_response_json="{}", provider="openai"
        ),
    ]
    for r in records:
        session.add(r)
    session.commit()

    yield user_id
```

### 8.2 Phase 3: LLM画像解析 (`test_calorie_agent.py`)

**ファイル**: `tests_v3/models/test_calorie_agent.py`

#### 8.2.1 スキーマ検証テスト

| ケースID | 検証内容 | 期待値 |
|----------|----------|--------|
| SCHEMA-01 | `FoodItem`の必須フィールド | 全フィールド必須、型チェック |
| SCHEMA-02 | `CalorieAnalysisResult`の必須フィールド | `schema_version="calorie_v2"`固定 |
| SCHEMA-03 | Structured Outputs `strict=True` | スキーマ外のフィールドは拒否 |

```python
def test_schema_validation():
    # 正常ケース
    valid_data = {
        "schema_version": "calorie_v2",
        "items": [
            {
                "food_name": "唐揚げ定食",
                "calorie": 850,
                "protein_g": 35.5,
                "fat_g": 28.0,
                "carbs_g": 95.0
            }
        ],
        "total_calorie": 850,
        "total_protein_g": 35.5,
        "total_fat_g": 28.0,
        "total_carbs_g": 95.0
    }
    result = CalorieAnalysisResult.model_validate(valid_data)
    assert result.schema_version == "calorie_v2"
    assert len(result.items) == 1

    # 異常ケース：必須フィールド欠落
    invalid_data = {
        "schema_version": "calorie_v2",
        "items": [{"food_name": "唐揚げ定食"}]  # PFC欠落
    }
    with pytest.raises(ValidationError):
        CalorieAnalysisResult.model_validate(invalid_data)
```

#### 8.2.2 OpenAI Provider テスト

| ケースID | 入力 | 期待値 | 説明 |
|----------|------|--------|------|
| OPENAI-01 | 正常な食事画像 | `CalorieAnalysisResult`型、PFC値が正数 | Structured Outputs動作 |
| OPENAI-02 | 空白画像 | エラーまたは空items | エラーハンドリング |
| OPENAI-03 | 複数品目画像 | items.length >= 2、totalが合計値 | 複数品目検出 |

```python
@pytest.mark.integration
def test_openai_calorie_analysis():
    analyzer = CalorieAnalyzer(provider="openai")
    with open("tests_v3/fixtures/sample_meal.jpg", "rb") as f:
        image_bytes = f.read()

    result = analyzer.analyze(image_bytes, "image/jpeg")

    assert isinstance(result, CalorieAnalysisResult)
    assert result.schema_version == "calorie_v2"
    assert len(result.items) >= 1
    assert result.total_calorie > 0
    assert result.total_protein_g >= 0
    assert result.total_fat_g >= 0
    assert result.total_carbs_g >= 0
```

#### 8.2.3 Gemini OpenAI互換EP テスト

| ケースID | 入力 | 期待値 | 説明 |
|----------|------|--------|------|
| GEMINI-01 | 正常な食事画像 | `CalorieAnalysisResult`型、OpenAIと同等の構造 | OpenAI互換EP動作 |
| GEMINI-02 | Structured Outputs | `strict=True`が効いているか | スキーマ準拠 |

```python
@pytest.mark.integration
def test_gemini_openai_compat_endpoint():
    analyzer = CalorieAnalyzer(provider="gemini")
    with open("tests_v3/fixtures/sample_meal.jpg", "rb") as f:
        image_bytes = f.read()

    result = analyzer.analyze(image_bytes, "image/jpeg")

    # OpenAIと同じスキーマで返ってくることを確認
    assert isinstance(result, CalorieAnalysisResult)
    assert result.schema_version == "calorie_v2"

    # PFC値が含まれている
    for item in result.items:
        assert hasattr(item, "protein_g")
        assert hasattr(item, "fat_g")
        assert hasattr(item, "carbs_g")
```

### 8.3 Phase 4: /cal処理 (`test_interactive_calorie.py`)

**ファイル**: `tests_v3/api/test_interactive_calorie.py`（新規）

#### 8.3.1 体組成設定チェック

| ケースID | 前提状態 | 期待動作 | 説明 |
|----------|----------|----------|------|
| BODY-01 | 全設定未設定 | `return`、エラー通知 | 全項目欠落 |
| BODY-02 | GENDERのみ欠落 | `return`、エラー通知"不足: GENDER" | 単一欠落 |
| BODY-03 | AGE, HEIGHT_CM欠落 | `return`、エラー通知"不足: AGE, HEIGHT_CM" | 複数欠落 |
| BODY-04 | 全設定完了 | 正常処理継続 | OKパターン |

```python
@pytest.mark.asyncio
async def test_calorie_submit_missing_body_composition(session, mock_slack_client):
    user_id = "test-user"
    # 設定なし
    with pytest.raises(HTTPException) as exc:
        await _run_calorie_submit_job(
            user_id=user_id,
            channel_id="C123",
            image_bytes=b"fake",
            mime_type="image/jpeg",
            uploaded_at_jst=datetime.now(JST),
            session=session,
        )
    assert "体組成設定" in str(exc.value)
```

#### 8.3.2 PFC保存

| ケースID | LLMレスポンス | DB保存値 | 説明 |
|----------|---------------|----------|------|
| SAVE-01 | items[0].protein_g=25.5 | `protein_g=25.5` | 小数点保存 |
| SAVE-02 | items[0].fat_g=0 | `fat_g=0.0` | 0値保存 |
| SAVE-03 | items複数 | 各アイテム独立保存 | 複数品目 |

```python
@pytest.mark.asyncio
async def test_pfc_save_to_db(session):
    analysis_result = CalorieAnalysisResult(
        schema_version="calorie_v2",
        items=[
            FoodItem(
                food_name="测试",
                calorie=500,
                protein_g=25.5,
                fat_g=15.0,
                carbs_g=60.0
            )
        ],
        total_calorie=500,
        total_protein_g=25.5,
        total_fat_g=15.0,
        total_carbs_g=60.0
    )

    # 保存処理...
    session.flush()

    records = session.query(CalorieRecord).filter_by(user_id="test-user").all()
    assert len(records) == 1
    assert records[0].protein_g == 25.5
    assert records[0].fat_g == 15.0
    assert records[0].carbs_g == 60.0
```

#### 8.3.3 残り計算

| ケースID | 当日摂取合計 | 目標 | 残り | 説明 |
|----------|-------------|------|------|------|
| REM-CAL-01 | 0 | 2267 | 2267 | 初期状態 |
| REM-CAL-02 | 1500 | 2267 | 767 | 通常パターン |
| REM-CAL-03 | 2500 | 2267 | 0 | 超過時 |

```python
@pytest.mark.asyncio
async def test_remaining_calculation(session, sample_user_with_records):
    # 目標: 2267 kcal, P=140, F=63, C=285
    # 摂取: 700 kcal, P=25, F=25, C=85
    remaining = calculate_remaining(
        user_id="test-user",
        target_date=date(2026, 3, 20),
        session=session
    )

    assert remaining["goal"]["calorie"] == 2267
    assert remaining["consumed"]["calorie"] == 700
    assert remaining["remaining"]["calorie"] == 1567
    assert remaining["remaining"]["protein_g"] == 115.0  # 140 - 25
    assert remaining["remaining"]["fat_g"] == 38.0       # 63 - 25
    assert remaining["remaining"]["carbs_g"] == 200.0    # 285 - 85
```

### 8.4 Phase 5: アドバイス生成 (`test_advice_generator.py`)

**ファイル**: `tests_v3/models/test_advice_generator.py`（新規）

#### 8.4.1 アドバイス生成

| ケースID | キャラクター | 入力状態 | 期待される出力 | 説明 |
|----------|-------------|----------|----------------|------|
| ADV-01 | デフォルト | 残り十分 | 1-2文の励まし | 正常パターン |
| ADV-02 | うる星やつらのラムちゃん | 残り少ない | キャラクター口調の警告 | 口調反映 |
| ADV-03 | カスタム | 目標超過 | 超過時のメッセージ | 超過パターン |
| ADV-04 | 任意 | 残り=0 | 「目標達成」等のメッセージ | 完了パターン |

```python
@pytest.mark.integration
def test_advice_generation():
    generator = AdviceGenerator(character="うる星やつらのラムちゃん")

    remaining = {"calorie": 500, "protein_g": 30, "fat_g": 10, "carbs_g": 50}
    consumed = {"calorie": 1767, "protein_g": 110, "fat_g": 53, "carbs_g": 235}
    goal = {"calorie": 2267, "protein_g": 140, "fat_g": 63, "carbs_g": 285}

    advice = generator.generate(remaining, consumed, goal)

    assert isinstance(advice, str)
    assert len(advice) > 0
    assert len(advice.split("\n")) <= 2  # 1-2文
```

### 8.5 Phase 6: Block Kit UI (`test_slack_ui.py`)

**ファイル**: `tests_v3/ui/test_slack_ui.py`（新規）

#### 8.5.1 Block Kit JSON構造

| ケースID | 入力 | 検証内容 | 説明 |
|----------|------|----------|------|
| UI-01 | 正常なremainingデータ | Block Kit JSON valid | JSON構造チェック |
| UI-02 | 残り=0 | 「目標達成」表示 | 超過/完了表示 |
| UI-03 | 複数items | 各itemのPFC表示 | 複数品目UI |

```python
def test_build_calorie_with_remaining_blocks():
    items = [
        {"food_name": "テスト", "calorie": 500, "protein_g": 25, "fat_g": 15, "carbs_g": 60}
    ]
    remaining_data = {
        "goal": {"calorie": 2267, "protein_g": 140, "fat_g": 63, "carbs_g": 285},
        "consumed": {"calorie": 500, "protein_g": 25, "fat_g": 15, "carbs_g": 60},
        "remaining": {"calorie": 1767, "protein_g": 115, "fat_g": 48, "carbs_g": 225}
    }
    advice = "良い調子です！"

    blocks = _build_calorie_with_remaining_blocks(items, datetime.now(JST), remaining_data, advice)

    # Block Kit基本構造
    assert isinstance(blocks, list)
    assert blocks[0]["type"] == "section"

    # キーワード確認
    block_text = str(blocks)
    assert "本日の摂取サマリー" in block_text
    assert "タンパク質" in block_text
    assert "脂質" in block_text
    assert "炭水化物" in block_text
```

### 8.6 テスト実行コマンド

```bash
# Phase 2: TDEE計算
pytest tests_v3/models/test_calorie_tdee.py -v

# Phase 3: LLM画像解析（integrationマーク付き）
pytest tests_v3/models/test_calorie_agent.py -v -m integration

# Phase 4: /cal処理
pytest tests_v3/api/test_interactive_calorie.py -v

# Phase 5: アドバイス生成
pytest tests_v3/models/test_advice_generator.py -v -m integration

# Phase 6: UI
pytest tests_v3/ui/test_slack_ui.py -v

# 全実行
pytest tests_v3/ -v
```

---

## 9. 実装上の注意点

### 8.1 timezone/日付境界

- `calorie_records.uploaded_at`はJSTのnaive datetimeとして保存
- 日付集計時はJSTの日付境界（00:00-23:59:59）で判定

### 8.2 既存関数の再利用

- `_load_user_config_values(user_id)`（backend/api/command.py）を再利用
- 返り値は`dict[str, str]`なので、数値は適宜パースが必要

### 8.3 calorie_agent.pyの削除範囲

**削除**:
- `_extract_json_text()`, `_extract_openai_content()`, `_extract_gemini_content()`
- `_analyze_with_openai()`, `_analyze_with_gemini()`, `analyze_calorie()`

**新規**:
- `CalorieAnalyzer` クラス

### 8.4 エッジケース対応

| ケース | 対応 |
|--------|------|
| PFCがNULLの既存レコード | `or 0`で0として扱う |
| 体組成設定未完了時 | 画像解析を実行せず、`/config`で設定することをエラー通知 |
| 体重の小数点入力 | `float()`でパース、`round(value, 1)`で丸める |
| 当日の合計が目標を超過 | `max(0, 目標 - 合計)`で0にfloor |
| 複数回/cal実行 | 既存レコードに追記、残り値は再計算 |

---

## 10. LLMエンドポイント

| プロバイダー | ベースURL | 備考 |
|------------|-----------|------|
| OpenAI | `https://api.openai.com/v1` | ネイティブ |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | OpenAI互換 |

---

## 11. 将来の拡張案

- マクロ栄養素比率のカスタマイズ（高タンパク、ケトgenic等）
- 食事履歴からの傾向分析
- 週次・月次レポートへの統合
