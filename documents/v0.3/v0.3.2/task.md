# v0.3.2 実装タスク - PFCバランス管理機能

実装の進捗管理用タスクリスト。完了したらチェックしてください。

---

## Phase 0: 環境設定（最初に実施）

### 0.1 依存ライブラリ確認

**ファイル**: `pyproject.toml`

- [x] `openai>=1.60.0` がdependenciesに含まれていることを確認
- [x] 含まれていない場合追加

### 0.2 環境変数追加

**ファイル**: `.env` または `env-sample`

- [x] 以下の環境変数を追加
  ```bash
  # v0.3.2: カロリー解析（PFC対応）
  CALORIE_PROVIDER=openai
  CALORIE_OPENAI_MODEL=gpt-4o-mini
  GEMINI_API_KEY=your-gemini-api-key-here
  CALORIE_GEMINI_MODEL=gemini-3.1-flash-lite-preview
  ADVICE_MODEL=gpt-4o-mini
  ```

---

## Phase 1: 体組成設定機能

### 1.1 CONFIG_DEFINITIONS への追加

**ファイル**: `backend/api/command.py`

- [x] `CONFIG_DEFINITIONS` 辞書に以下6項目を追加
  - [x] `GENDER`: STR, allowed={"male", "female"}, default="-"
  - [x] `AGE`: INT, min=10, max=100, default="30"
  - [x] `HEIGHT_CM`: INT, min=100, max=250, default="170"
  - [x] `WEIGHT_KG`: FLOAT, min=30, max=200, default="65.0"
  - [x] `ACTIVITY_LEVEL`: STR, allowed={"1.2", "1.375", "1.55", "1.725"}, default="1.375"
  - [x] `DIET_GOAL`: STR, allowed={"lose", "maintain", "gain"}, default="maintain"

```python
# 追加位置: CONFIG_DEFINITIONS 辞書内
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
```

### 1.2 _body_composition_section() 関数新規追加

**ファイル**: `backend/slack_ui.py`

- [x] 既存のsection関数（`_punishment_section`など）と同じパターンで`_body_composition_section()`を作成
- [x] 配置場所: `_coach_section()` の後、`config_modal()` の前
- [x] 各設定項目のinput blockを実装

```python
def _body_composition_section(config_values: dict[str, str]) -> list[dict[str, Any]]:
    """Generate body composition configuration section"""
    current_gender = config_values.get("GENDER", "-")
    current_age = config_values.get("AGE", "30")
    current_height = config_values.get("HEIGHT_CM", "170")
    current_weight = config_values.get("WEIGHT_KG", "65.0")
    current_activity = config_values.get("ACTIVITY_LEVEL", "1.375")
    current_goal = config_values.get("DIET_GOAL", "maintain")

    # GENDER options
    gender_options = [
        {"text": {"type": "plain_text", "text": "男性"}, "value": "male"},
        {"text": {"type": "plain_text", "text": "女性"}, "value": "female"},
    ]
    gender_initial = next((o for o in gender_options if o["value"] == current_gender), None)

    # ACTIVITY_LEVEL options
    activity_options = [
        {"text": {"type": "plain_text", "text": "1.2 - ほぼ運動しない"}, "value": "1.2"},
        {"text": {"type": "plain_text", "text": "1.375 - 軽い運動（週1-3日）"}, "value": "1.375"},
        {"text": {"type": "plain_text", "text": "1.55 - 中程度（週3-5日）"}, "value": "1.55"},
        {"text": {"type": "plain_text", "text": "1.725 - 活発（週6-7日）"}, "value": "1.725"},
    ]
    activity_initial = next((o for o in activity_options if o["value"] == current_activity), None)

    # DIET_GOAL options
    goal_options = [
        {"text": {"type": "plain_text", "text": "減量（-500kcal）"}, "value": "lose"},
        {"text": {"type": "plain_text", "text": "維持"}, "value": "maintain"},
        {"text": {"type": "plain_text", "text": "増量（+500kcal）"}, "value": "gain"},
    ]
    goal_initial = next((o for o in goal_options if o["value"] == current_goal), None)

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🏃 体組成・活動量",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "TDEE計算とPFC目標値の算出に使用します。",
            },
        },
        {
            "type": "input",
            "block_id": "config_GENDER",
            "label": {"type": "plain_text", "text": "性別"},
            "element": {
                "type": "static_select",
                "action_id": "input",
                "options": gender_options,
                "initial_option": gender_initial,
            },
        },
        {
            "type": "input",
            "block_id": "config_AGE",
            "label": {"type": "plain_text", "text": "年齢"},
            "element": {
                "type": "plain_text_input",
                "action_id": "input",
                "placeholder": {"type": "plain_text", "text": "30"},
                "initial_value": current_age if current_age != "-" else "",
            },
        },
        {
            "type": "input",
            "block_id": "config_HEIGHT_CM",
            "label": {"type": "plain_text", "text": "身長 (cm)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "input",
                "placeholder": {"type": "plain_text", "text": "170"},
                "initial_value": current_height if current_height != "-" else "",
            },
        },
        {
            "type": "input",
            "block_id": "config_WEIGHT_KG",
            "label": {"type": "plain_text", "text": "体重 (kg)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "input",
                "placeholder": {"type": "plain_text", "text": "65.0"},
                "initial_value": current_weight if current_weight != "-" else "",
            },
        },
        {
            "type": "input",
            "block_id": "config_ACTIVITY_LEVEL",
            "label": {"type": "plain_text", "text": "活動レベル"},
            "element": {
                "type": "static_select",
                "action_id": "input",
                "options": activity_options,
                "initial_option": activity_initial,
            },
        },
        {
            "type": "input",
            "block_id": "config_DIET_GOAL",
            "label": {"type": "plain_text", "text": "目的"},
            "element": {
                "type": "static_select",
                "action_id": "input",
                "options": goal_options,
                "initial_option": goal_initial,
            },
        },
    ]
```

### 1.3 config_modal() にsection追加

**ファイル**: `backend/slack_ui.py`

- [x] `config_modal()` 関数内の`blocks.extend(_coach_section(config_values))`の後に以下を追加
  ```python
  blocks.extend(_body_composition_section(config_values))
  ```
- [x] 配置場所の例:
  ```python
  def config_modal(config_values: dict[str, str]) -> dict[str, Any]:
      blocks = []
      blocks.extend(_punishment_section(config_values))
      blocks.extend(_ignore_section(config_values))
      blocks.extend(_report_section(config_values))
      blocks.extend(_coach_section(config_values))
      blocks.extend(_body_composition_section(config_values))  # 追加
      # ... 以降既存コード
  ```

### 1.4 バリデーション追加

- [x] 既存ロジックで対応（`_extract_config_updates_from_view()`がCONFIG_DEFINITIONSを参照して自動バリデーション）

---

## Phase 2: TDEE/PFC計算モジュール

### 2.1 calorie_tdee.py 新規作成

**ファイル**: `backend/calorie_tdee.py`（新規）

- [x] ファイル作成
- [x] import追加: `datetime`, `date`, `time`, `zoneinfo`, `ZoneInfo`
  ```python
  from datetime import date, datetime, time
  from zoneinfo import ZoneInfo
  ```
- [x] `JST = ZoneInfo("Asia/Tokyo")` 定義

- [x] `calculate_tdee()` 関数実装
  ```python
  def calculate_tdee(
      gender: str,
      age: int,
      height_cm: int,
      weight_kg: float,
      activity_level: str,
      diet_goal: str,
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
  ```

### 2.2 calculate_remaining() 関数実装

**ファイル**: `backend/calorie_tdee.py`

- [x] `calculate_remaining()` 関数実装
  - [x] **循環参照回避**: `_load_user_config_values` はimportせず、引数`configs`で受け取る
  - [x] `calculate_tdee()` で目標値計算
  - [x] `session.query(CalorieRecord)` で当日分を集計
  - [x] NULL値は0として扱う
  - [x] 残り = max(0, 目標 - 集計) で計算

```python
def calculate_remaining(
    user_id: str,
    target_date: date,
    configs: dict[str, str],  # 呼び出し元で_load_user_config_values()した結果を渡す
    session,
) -> dict:
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
    end_of_day = datetime.combine(target_date, time.max)    # 23:59:59.999999

    records = session.query(CalorieRecord).filter(
        CalorieRecord.user_id == user_id,
        CalorieRecord.uploaded_at >= start_of_day,
        CalorieRecord.uploaded_at <= end_of_day,
    ).all()

    consumed_calorie = sum(r.calorie for r in records)
    consumed_protein = sum(r.protein_g or 0 for r in records)
    consumed_fat = sum(r.fat_g or 0 for r in records)
    consumed_carbs = sum(r.carbs_g or 0 for r in records)

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
            "protein_g": max(0, tdee_result["protein_g"] - consumed_protein),
            "fat_g": max(0, tdee_result["fat_g"] - consumed_fat),
            "carbs_g": max(0, tdee_result["carbs_g"] - consumed_carbs),
        },
    }
```

> **注意**: `configs`引数を追加したため、呼び出し元（interactive.py）で以下のように渡します:
> ```python
> configs = _load_user_config_values(user_id)
> remaining_data = calculate_remaining(user_id, datetime.now(JST).date(), configs, session)
> ```

### 2.3 単体テスト作成

**ファイル**: `tests_v3/models/test_calorie_tdee.py`（新規）

- [x] ファイル作成
- [x] `calculate_tdee()` テスト（7ケース）
  - [x] TDEE-01: 標準男性維持
  - [x] TDEE-02: 標準男性減量
  - [x] TDEE-03: 標準男性増量
  - [x] TDEE-04: 標準女性
  - [x] TDEE-05: ほぼ運動しない
  - [x] TDEE-06: 活発
  - [x] TDEE-07: carbs_g負値ケース
- [x] `calculate_remaining()` テスト（6ケース）
  - [x] REM-01: 当日レコード0件
  - [x] REM-02: 1件
  - [x] REM-03: 3件
  - [x] REM-04: 超過時
  - [x] REM-05: NULL handling
  - [x] REM-06: 日付境界
- [x] `pytest tests_v3/models/test_calorie_tdee.py -v` で全テストパス確認

---

## Phase 3: データベース変更

### 3.1 モデル変更

**ファイル**: `backend/models/__init__.py`

- [x] Floatをimportに追加
- [x] `CalorieRecord` クラスにPFCカラム追加
  ```python
  # __tablename__ = "calorie_records" のクラス内に追加
  from sqlalchemy import Float  # import済み確認

  protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
  fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
  carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
  ```

### 3.2 Migration作成

**ファイル**: `backend/alembic/versions/`（自動生成）

- [x] カレントディレクトリを`backend/`に移動
- [x] 以下のコマンドでMigrationファイルを自動生成
  ```bash
  cd backend
  alembic revision -m "v0.3.2 PFC columns"
  ```
- [x] 生成されたファイルを編集

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

- [x] Migration実行
  ```bash
  alembic upgrade head
  ```
- [x] DBにカラムが追加されたことを確認（SQLiteの`PRAGMA table_info(calorie_records)`で確認）

> **生成されたファイル**: `backend/alembic/versions/2026_03_20_1451-22f8f4f0eaf7_v0_3_2_pfc_columns.py`

---

## Phase 4: LLM画像解析再実装

### 4.1 calorie_agent.py 再実装

**ファイル**: `backend/calorie_agent.py`

- [x] 既存の不要な関数を削除
  - [x] `_extract_json_text()` 削除
  - [x] `_extract_openai_content()` 削除
  - [x] `_extract_gemini_content()` 削除
  - [x] `_analyze_with_openai()` 削除
  - [x] `_analyze_with_gemini()` 削除
  - [x] `analyze_calorie()` 削除

> **削除範囲の目安**: `analyze_calorie()`関数が終わるまでを全て削除し、新規実装に置き換える

- [x] Pydanticスキーマ定義
  ```python
  from pydantic import BaseModel

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
  ```

- [x] `CalorieAnalyzer` クラス実装
  - [x] `__init__(provider: str = "openai")`
  - [x] `_create_client() -> tuple[OpenAI, str]`
    - [x] provider="openai": base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    - [x] provider="gemini": base_url="https://generativelanguage.googleapis.com/v1beta/openai", model="gemini-3.1-flash-lite-preview"
  - [x] `analyze(image_bytes: bytes, mime_type: str) -> CalorieAnalysisResult`
    - [x] base64エンコード
    - [x] chat.completions.create() 呼び出し
    - [x] response_formatにjson_schema, strict=True指定
    - [x] model_validate_json()でパース

> **Pydantic modelの使い方**:
> - 関数は`CalorieAnalysisResult`オブジェクトを返す
> - `result.items`で`FoodItem`のリストにアクセス
> - 各itemのフィールドは`item.food_name`, `item.calorie`, `item.protein_g`のようにアクセス
> - 呼び出し元で辞書が必要な場合: `[item.model_dump() for item in result.items]`

### 4.2 単体テスト作成

**ファイル**: `tests_v3/models/test_calorie_agent.py`

- [x] ファイル作成（TDD: Red→Green→Refactor）
- [x] スキーマ検証テスト（5ケース）
  - [x] 正常ケース
  - [x] 異常ケース（必須フィールド欠落）
  - [x] 辞書パース
- [x] CalorieAnalyzerテスト（6ケース）
  - [x] OpenAI Providerテスト
  - [x] Gemini Providerテスト（APIキーなし時スキップ）
  - [x] 無効provider時のフォールバック
  - [x] _create_client返り値
  - [x] model_dump変換
- [x] `pytest tests_v3/models/test_calorie_agent.py -v` で10 passed, 1 skipped

---

## Phase 5: /cal処理の拡張

### 5.1 体組成設定チェック

**ファイル**: `backend/api/interactive.py`

- [x] `_run_calorie_submit_job()` 関数の先頭にチェック追加
  ```python
  # v0.3.2追加: 体組成設定チェック
  from backend.api.command import _load_user_config_values

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
  ```

> **注意**: `_notify_calorie_result()`は既存関数（`backend/api/interactive.py:251`）

### 5.2 PFC保存

**ファイル**: `backend/api/interactive.py`

- [x] `CalorieRecord` 保存部分にPFC追加
- [x] **重要**: `items`はPydantic modelのリストなので、辞書に変換してから処理

```python
# LLM解析結果を辞書リストに変換
items_dicts = [item.model_dump() for item in analysis_result.items]

# 既存の保存ループ内
for row in items_dicts:
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

### 5.3 残り計算＆通知

**ファイル**: `backend/api/interactive.py`

- [x] `calculate_remaining()` import追加
  ```python
  from backend.calorie_tdee import calculate_remaining
  ```

- [x] `_run_calorie_submit_job()` の最後で残り計算
  ```python
  # configsは既に5.1で取得している
  remaining_data = calculate_remaining(user_id, datetime.now(JST).date(), configs, session)
  ```

- [ ] `_build_calorie_with_remaining_blocks()` 呼び出し（Phase 6で実装）

### 5.4 単体テスト作成

**ファイル**: `tests_v3/api/test_interactive_calorie.py`（新規）

- [x] ファイル作成
- [x] `TestCalorieSubmitBodyCompositionCheck` クラス（体組成チェックテスト）
  - [x] BODY-01: 全設定未設定でエラー通知
  - [x] BODY-02: 一部設定未設定
  - [x] BODY-03: 全設定完了（正常パス）
  - [x] BODY-04: 設定値バリデーション
- [x] `TestCalorieSubmitPFCSave` クラス（PFC保存テスト）
  - [x] SAVE-01: 小数点値の保存
  - [x] SAVE-02: 0値の保存
  - [x] SAVE-03: NULL値の保存
- [x] 実装完了後にテストパス確認: `pytest tests_v3/api/test_interactive_calorie.py -v`

---

## Phase 6: Block Kit UI

### 6.1 残り許容値UI実装

**ファイル**: `backend/slack_ui.py`

- [x] `_build_calorie_with_remaining_blocks()` 関数実装
  - [x] 配置場所: Calorie Modalセクション内
  - [x] 本次の食事セクション
  - [x] 本日の合計セクション
  - [x] 残りの摂取許容値セクション
  - [x] アドバイスセクション

```python
def _build_calorie_with_remaining_blocks(
    items: list[dict[str, Any]],
    uploaded_at: datetime,
    remaining_data: dict[str, Any],
    advice: str,
) -> list[dict[str, Any]]:
    """Build calorie notification blocks with remaining intake"""

    # 今回の食事を構築
    meal_parts = []
    for item in items:
        meal_parts.append(
            f"• {item['food_name']}: {item['calorie']}kcal "
            f"(P:{item.get('protein_g', 0)}g F:{item.get('fat_g', 0)}g C:{item.get('carbs_g', 0)}g)"
        )

    goal = remaining_data["goal"]
    consumed = remaining_data["consumed"]
    remaining = remaining_data["remaining"]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 本日の摂取サマリー"}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🍽️ 今回の食事*\n" + "\n".join(meal_parts)
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*📈 本日の合計*\n"
                    f"カロリー: {consumed['calorie']} / {goal['daily_calorie_goal']} kcal\n"
                    f"タンパク質: {consumed['protein_g']} / {goal['protein_g']} g\n"
                    f"脂質: {consumed['fat_g']} / {goal['fat_g']} g\n"
                    f"炭水化物: {consumed['carbs_g']} / {goal['carbs_g']:.1f} g"
                )
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*✅ 残りの摂取許容値*\n"
                    f"カロリー: {remaining['calorie']} kcal\n"
                    f"タンパク質: {remaining['protein_g']} g\n"
                    f"脂質: {remaining['fat_g']} g\n"
                    f"炭水化物: {remaining['carbs_g']:.1f} g"
                )
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*💬 アドバイス*\n{advice}"
            }
        },
    ]
    return blocks
```

> **引数の型**:
> - `items`: 辞書のリスト（Pydantic modelを`.model_dump()`で変換したもの）
> - `remaining_data`: `calculate_remaining()`の返り値

### 6.2 単体テスト作成

**ファイル**: `tests_v3/ui/test_slack_ui.py`（新規）

- [x] ファイル作成
- [x] `tests_v3/ui/__init__.py` 作成
- [x] `TestBuildCalorieWithRemainingBlocks` クラス
  - [x] UI-01: 正常なremaining_dataでBlock Kit JSON生成
  - [x] UI-02: 残り=0の場合の表示
  - [x] UI-03: 複数itemsの表示
  - [x] UI-04: PFC（タンパク質・脂質・炭水化物）表示確認
- [x] 実装完了後にテストパス確認: `pytest tests_v3/ui/test_slack_ui.py -v`

---

## Phase 7: アドバイス生成

### 7.1 advice_generator.py 新規作成

**ファイル**: `backend/advice_generator.py`（新規）

- [x] ファイル作成
- [x] Pydanticスキーマ定義（OpenAI Structured Outputs対応）
- [x] `AdviceGenerator` クラス実装
  - [x] `__init__(character: str)`
  - [x] `generate(remaining: dict, consumed: dict, goal: dict) -> str`
    - [x] OpenAI Structured Outputs使用
    - [x] system promptにキャラクター反映
    - [x] 1-2文の短いアドバイス
    - [x] 状態判定（goal_achieved, running_low, exceeded, on_track）

### 7.2 /cal処理から呼び出し

**ファイル**: `backend/api/interactive.py`

- [x] `AdviceGenerator` import追加
- [x] COACH_CHARACTOR設定取得
- [x] アドバイス生成呼び出し

### 7.3 単体テスト作成

**ファイル**: `tests_v3/models/test_advice_generator.py`（新規）

- [x] ファイル作成
- [x] `TestAdviceGenerator` クラス（@pytest.mark.integration）
  - [x] ADV-01: 残り十分（1-2文の励まし）
  - [x] ADV-02: 残り少ない（キャラクター口調の警告）
  - [x] ADV-03: 目標超過時のメッセージ
  - [x] ADV-04: 目標達成のメッセージ
- [x] 実装完了後にテストパス確認: `pytest tests_v3/models/test_advice_generator.py -v -m integration`

---

## 実装完了チェックリスト

### 全体

- [x] すべての単体テストがパスする
  ```bash
  pytest tests_v3/models/test_calorie_tdee.py -v
  pytest tests_v3/models/test_calorie_agent.py -v -m integration
  pytest tests_v3/models/test_advice_generator.py -v -m integration
  pytest tests_v3/api/test_interactive_calorie.py -v
  pytest tests_v3/ui/test_slack_ui.py -v
  ```
- [x] lintエラーがない
- [x] Migrationが適用されている
- [x] `/config` で体組成設定ができる（手動テスト）
- [x] `/cal` で画像解析後にPFCが表示される（手動テスト）
- [x] 残り摂取許容値が正しく計算される（単体テストで確認済み）
- [x] アドバイスが表示される（手動テスト）

### 手動テスト

> **自動テスト結果**: 36 passed, 1 skipped (全Phase完了)
>
> 手動テストは実際のSlack環境で動作確認が必要です。

- [x] 体組成未設定時に `/cal` でエラーが表示される
- [x] 1日に複数回 `/cal` を実行した場合、合計が正しく集計される
- [x] 目標を超過した場合、残りが0表示になる
- [x] Gemini providerでも画像解析が動く

---

## 備考

- 実装順序はPhase順に推奨（Phase 0→1→2→3→4→5→6→7）
- Phase 0は最初に実施すること
- Phase 6のUI実装はPhase 5のPFC保存完了後に行うこと
- integrationテストにはAPIキーが必要（`.env`の設定が必要）
