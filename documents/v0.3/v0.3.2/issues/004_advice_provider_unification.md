# Issue #004: アドバイス生成でも CALORIE_PROVIDER を参照する

## 概要

画像解析とアドバイス生成でプロバイダー設定を統一する必要があります。

## 現状

| 機能 | 環境変数 | プロバイダー |
|------|----------|------------|
| 画像解析 | `CALORIE_PROVIDER` | openai/gemini |
| アドバイス生成 | `ADVICE_MODEL` | OpenAIのみ |

## 要望

アドバイス生成でも `CALORIE_PROVIDER` を参照して、画像解析と同じプロバイダーを使用する。

## 修正内容

### 1. `AdviceGenerator` の更新

- `__init__(character: str, provider: str = "openai")` に変更
- プロバイダーに応じて適切なクライアントとモデルを使用
  - `openai`: OpenAI API (`ADVICE_MODEL` またはデフォルト)
  - `gemini`: Gemini OpenAI-compatible endpoint

### 2. 呼び出し元の更新

`backend/api/interactive.py` で `calorie_provider` を渡すように変更:

```python
advice = AdviceGenerator(character, calorie_provider).generate(...)
```

## 優先度

**中** - 設定の一貫性のため

## ステータス

RESOLVED ✅

## 修正内容

### 1. `AdviceGenerator` の更新

- `__init__(character: str, provider: str = "openai")` に変更
- `_create_client()` メソッドを追加して、プロバイダーに応じたクライアントとモデルを選択
  - `openai`: `ADVICE_MODEL` 環境変数 (デフォルト: gpt-4o-mini)
  - `gemini`: `CALORIE_GEMINI_MODEL` 環境変数 (デフォルト: gemini-3.1-flash-lite-preview)

### 2. 呼び出し元の更新

`backend/api/interactive.py` で `calorie_provider` を渡すように変更:

```python
advice = AdviceGenerator(character, calorie_provider).generate(...)
```

## 動作

- `CALORIE_PROVIDER=openai` → 画像解析: OpenAI, アドバイス: OpenAI
- `CALORIE_PROVIDER=gemini` → 画像解析: Gemini, アドバイス: Gemini

## 修正日

2026-03-20

## 追加修正: 実装方針の統一

`backend/llm_client.py` を新規作成し、`CalorieAnalyzer` と `AdviceGenerator` の両方で共通の `LLMClientConfig` を使用するように変更:

### `LLMClientConfig` クラス

- プロバイダーに応じたクライアント生成を集約
- `get_provider_from_env()`: 環境変数からプロバイダーを取得
- `get_model_for_purpose(purpose)`: 用途（"image" または "advice"）に応じたモデルを取得

### 更新したファイル

1. `backend/llm_client.py` (新規)
2. `backend/calorie_agent.py` - `LLMClientConfig` を使用
3. `backend/advice_generator.py` - `LLMClientConfig` を使用
4. `tests_v3/models/test_calorie_agent.py` - テストを更新

## 作成日

2026-03-20
