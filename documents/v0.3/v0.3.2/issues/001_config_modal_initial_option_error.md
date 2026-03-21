# Issue #001: /config モーダルの initial_option エラー

## 概要

`/config` コマンド実行時に設定モーダルが開けないエラーが発生します。

## エラーメッセージ

```
warning: 設定モーダルを開けませんでした: invalid_arguments
([ERROR] failed to match all allowed schemas [json-pointer:/view];
[ERROR] must provide an object [json-pointer:/view/blocks/24/element/initial_option])
```

## 原因

`backend/slack_ui.py` の `_body_composition_section()` 関数において、`initial_option` が `None` の場合でも Block Kit に渡されており、Slack APIがオブジェクトを要求している箇所で `null` が渡されていることが原因です。

該当するセクション:
- `ACTIVITY_LEVEL` の `activity_initial`
- `DIET_GOAL` の `goal_initial`
- `GENDER` の `gender_initial`

## 再現手順

1. `/config` コマンドを実行
2. 体組成設定が未設定（デフォルト値"-"など）の場合に発生
3. または設定値がoptionsに含まれない値の場合に発生

## 修正案

`initial_option` が `None` の場合、デフォルト値を設定するか、`initial_option` 自体を省略する必要があります。

### 修正箇所: `backend/slack_ui.py`

```python
# 修正前
gender_initial = None
for opt in gender_options:
    if opt["value"] == current_gender:
        gender_initial = opt
        break
```

```python
# 修正案1: デフォルト値を設定
gender_initial = None
for opt in gender_options:
    if opt["value"] == current_gender:
        gender_initial = opt
        break
if gender_initial is None:
    gender_initial = gender_options[0]  # デフォルトを設定
```

```python
# 修正案2: initial_optionキーを条件付きで追加
element_data = {
    "type": "static_select",
    "action_id": "GENDER_select",
    "options": gender_options,
}
if gender_initial is not None:
    element_data["initial_option"] = gender_initial
```

## 優先度

**高** - `/config` コマンドが機能しないため、ユーザーが設定変更できない

## 担当

TODO: 割り当てられていない

## ステータス

RESOLVED ✅

## 修正内容

`backend/slack_ui.py` の `_body_composition_section()` 関数で、`initial_option` が `None` の場合にデフォルト値を設定するように修正:

- `gender_initial`: `gender_options[0]` (男性)
- `activity_initial`: `activity_options[1]` (1.375 - 軽い運動)
- `goal_initial`: `goal_options[1]` (維持)

## 修正日

2026-03-20

## 作成日

2026-03-20
