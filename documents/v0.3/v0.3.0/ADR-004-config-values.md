# ADR-004: 設定値の採用リスト

## Status
Proposed

## Context
v0.3_design.mdとv0.3_slack_ui_spec.mdで設定値の定義に差分がある。
「実際に使うものだけ残す」原則に基づき、最終的な設定値リストを決定する。

## Decision

### 設定値の最終リスト

#### ✅ 採用する設定値（DB + Slack UIから変更可能）

| 設定キー | デフォルト | 型 | 範囲 | UI表示 | 使用箇所 |
|---------|-----------|-----|------|--------|---------|
| `PAVLOK_TYPE_PUNISH` | zap | str | zap,beep,vibe | static_select | Worker: NO時の罰タイプ |
| `PAVLOK_VALUE_PUNISH` | 35 | int | 0-100 | plain_text_input | Worker: NO時の罰強度 |
| `LIMIT_DAY_PAVLOK_COUNTS` | 100 | int | 1-1000 | plain_text_input | Worker: 日次ZAP上限 |
| `LIMIT_PAVLOK_ZAP_VALUE` | 100 | int | 1-100 | plain_text_input | Worker: ZAP強度ハードリミット |
| `IGNORE_INTERVAL` | 900 | int | 300-1800 | static_select | Worker: ignore検知間隔(秒) |
| `IGNORE_JUDGE_TIME` | 3 | int | 1-30 | plain_text_input | Worker: ignore判定時間(秒) |
| `IGNORE_MAX_RETRY` | 5 | int | 1-20 | plain_text_input | Worker: ignore最大再試行回数 |
| `SYSTEM_PAUSED` | false | bool | true/false | なし（/stop,/restartで制御） | Worker: 罰停止フラグ |

#### ❌ 削除する設定値（v0.3_design.mdにあったが採用しない）

| 設定キー | 理由 |
|---------|------|
| `PAVLOK_TYPE_REMIND` | remind通知はテキストのみ。Pavlokは使わない |
| `PAVLOK_VALUE_REMIND` | 同上 |
| `PUNISH_INTERVAL_SEC` | ignore_intervalで代替 |
| `IGNORE_SPAN` | ignore_judge_timeに名称統一 |
| `REPLY_COUNT_LIMIT` | ignore_max_retryで代替 |
| `REMIND_TIMEOUT_SEC` | timeout_remindに名称統一 |
| `REFLECTION_TIMEOUT_SEC` | timeout_reviewに名称統一 |
| `RETRY_DELAY_MIN` | retry_delayに名称統一 |

#### 🔒 環境変数のみ（Slack UIから変更不可）

| 変数名 | 用途 |
|--------|------|
| `DATABASE_URL` | DB接続文字列 |
| `SLACK_BOT_USER_OAUTH_TOKEN` | Bot用トークン |
| `SLACK_USER_OAUTH_TOKEN` | User用トークン |
| `SLACK_SIGNING_SECRET` | 署名検証用 |
| `PAVLOK_API_KEY` | Pavlok JWT |
| `INTERNAL_SECRET` | /internal保護用 |
| `TIMEZONE` | システムタイムゾーン |
| `AGENT_MODE` | Agent実行モード |
| `AUTHORIZED_USERS` | 認可ユーザーリスト |
| `TIMEOUT_REMIND` | remind応答タイムアウト(秒) |
| `TIMEOUT_REVIEW` | 振り返り応答タイムアウト(秒) |
| `RETRY_DELAY` | 失敗時リトライ遅延(分) |

### 設定値の命名規則

統一された命名規則を採用:

```
{カテゴリ}_{詳細}

カテゴリ:
- PAVLOK_* : Pavlok関連
- IGNORE_* : ignoreモード関連
- LIMIT_* : 制限値
- TIMEOUT_* : タイムアウト値
- RETRY_* : リトライ関連
```

### v0.3_design.mdとの差分対応

#### configurationsテーブル定義の更新

```python
# 更新後の設定値リスト
CONFIG_DEFINITIONS = {
    "PAVLOK_TYPE_PUNISH": {
        "type": "str",
        "default": "zap",
        "valid_values": ["zap", "beep", "vibe"],
        "description": "デフォルト罰スタイル"
    },
    "PAVLOK_VALUE_PUNISH": {
        "type": "int",
        "default": 35,
        "min": 0,
        "max": 100,
        "description": "デフォルト罰強度"
    },
    "LIMIT_DAY_PAVLOK_COUNTS": {
        "type": "int",
        "default": 100,
        "min": 1,
        "max": 1000,
        "description": "1日の最大ZAP回数"
    },
    "LIMIT_PAVLOK_ZAP_VALUE": {
        "type": "int",
        "default": 100,
        "min": 1,
        "max": 100,
        "description": "最大ZAP強度(ハードリミット)"
    },
    "IGNORE_INTERVAL": {
        "type": "int",
        "default": 900,
        "min": 300,
        "max": 1800,
        "description": "ignore検知間隔(秒)",
        "ui_options": [300, 600, 900, 1800]  # 5分, 10分, 15分, 30分
    },
    "IGNORE_JUDGE_TIME": {
        "type": "int",
        "default": 3,
        "min": 1,
        "max": 30,
        "description": "ignore判定時間(秒)"
    },
    "IGNORE_MAX_RETRY": {
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 20,
        "description": "ignore最大再試行回数"
    }
}
```

### 設定値の優先順位

```
通常キー:
1. DB設定値 (configurationsテーブル)
2. 環境変数 (.env)
3. ハードコードされたデフォルト値

運用キー（`TIMEOUT_REMIND` / `TIMEOUT_REVIEW` / `RETRY_DELAY`）:
1. 環境変数 (.env)
2. ハードコードされたデフォルト値
```

## Consequences

### Positive
- 設定値の整理・削減
- 命名の一貫性
- UIとBackendの整合性

### Negative
- v0.3_design.mdの大幅な修正が必要

### Risks
- 既存設定値からの移行
  - 対策: クリーンスタート前提（移行不要）

## Implementation Notes

1. v0.3_design.mdの設定値セクションを更新
2. v0.3_slack_ui_spec.mdの設定モーダルと整合確認
3. init_db.pyのseedデータ更新
4. Worker/Backendでの設定値取得ロジック実装

## Related
- v0.3_slack_ui_spec.md: 2.4 /config - 設定管理
- v0.3_design.md: 10. 設定管理機能詳細設計
