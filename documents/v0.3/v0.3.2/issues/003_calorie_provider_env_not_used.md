# Issue #003: CALORIE_PROVIDER 環境変数が無視される

## 概要

`.env` に `CALORIE_PROVIDER=gemini` を定義しているにも関わらず、画像解析時に OpenAI API が呼び出されています。

## エラーメッセージ

- `CALORIE_PROVIDER=gemini` を設定しているのに OpenAI API が呼ばれる

## 原因

`backend/api/interactive.py` の `_run_calorie_submit_job()` 関数で `analyze_calorie()` を呼び出す際、`provider` 引数を渡していません。そのため、デフォルト値の `"openai"` が使用されています。

```python
# backend/api/interactive.py:1775
parsed_payload, raw_json, provider, model = await asyncio.to_thread(
    analyze_calorie,
    image_bytes,
    mime_type,
    # provider 引数が渡されていない
)
```

また、`CALORIE_PROVIDER` 環境変数を読み込む処理が実装されていません。

## 修正案

### 修正箇所: `backend/api/interactive.py`

```python
# 環境変数からプロバイダーを取得（デフォルトはopenai）
calorie_provider = os.getenv("CALORIE_PROVIDER", "openai").strip()

parsed_payload, raw_json, provider, model = await asyncio.to_thread(
    analyze_calorie,
    image_bytes,
    mime_type,
    calorie_provider,  # provider 引数を渡す
)
```

### 修正箇所: `env-sample`

```bash
# カロリー解析プロバイダー (openai または gemini)
CALORIE_PROVIDER=gemini
```

## 優先度

**中** - 機能はするが、コストの最適化のためにプロバイダーを変更したいユーザーにとって問題

## 担当

TODO: 割り当てられていない

## ステータス

RESOLVED ✅

## 修正内容

`backend/api/interactive.py` の `_run_calorie_submit_job()` 関数で、`CALORIE_PROVIDER` 環境変数を読み取って `analyze_calorie()` に渡すように修正:

```python
calorie_provider = os.getenv("CALORIE_PROVIDER", "openai").strip()
parsed_payload, raw_json, provider, model = await asyncio.to_thread(
    analyze_calorie,
    image_bytes,
    mime_type,
    calorie_provider,  # provider 引数を渡す
)
```

## 修正日

2026-03-20

## 作成日

2026-03-20
