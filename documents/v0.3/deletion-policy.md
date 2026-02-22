# 削除方針ドキュメント

## 1. 概要
v0.3への移行に伴い、不要になるコード・ファイルを整理する。

## 2. 削除リスト

### 2.1 スクリプト削除

| ファイル | 理由 | 削除判定 |
|---------|------|---------|
| `scripts/add_schedules.py` | v0.3ではWorkerが自動生成 | 削除 |
| `scripts/repentance.py` | v0.3では不要な概念 | 削除 |
| `scripts/add_slack_ignore_events.py` | v0.3ではWorkerが自動検知 | 削除 |

### 2.2 テーブル削除（DB Migration時）

| テーブル | 理由 | 削除判定 |
|---------|------|---------|
| `schedules` | 再設計のためDROP | 削除 |
| `behavior_logs` | `action_logs`に名称変更 | 削除 |
| `slack_ignore_events` | v0.3では不要 | 削除 |
| `daily_punishments` | `punishments`に統合 | 削除 |
| `pavlok_counts` | v0.3では不要（punishmentsで管理） | 削除 |

### 2.3 設定値削除

| 設定キー | 理由 | 削除判定 |
|---------|------|---------|
| `PAVLOK_TYPE_REMIND` | remindでPavlokを使わない | 削除 |
| `PAVLOK_VALUE_REMIND` | 同上 | 削除 |
| `PUNISH_INTERVAL_SEC` | `IGNORE_INTERVAL`で代替 | 削除 |
| `IGNORE_SPAN` | `IGNORE_JUDGE_TIME`に統一 | 削除 |
| `REPLY_COUNT_LIMIT` | `IGNORE_MAX_RETRY`で代替 | 削除 |
| `REMIND_TIMEOUT_SEC` | `TIMEOUT_REMIND`に統一 | 削除 |
| `REFLECTION_TIMEOUT_SEC` | `TIMEOUT_REVIEW`に統一 | 削除 |
| `RETRY_DELAY_MIN` | `RETRY_DELAY`に統一 | 削除 |

### 2.4 コード削除（再利用スクリプト内）

#### scripts/slack.py
- 古いコマンド処理ロジック（`/remind`, `/ignore`等）
- CLIベースのインタラクション

#### scripts/behavior_log.py
- `behavior_logs`テーブル参照の削除
- `action_logs`テーブルへの移行

## 3. 残すリスト

### 3.1 再利用するスクリプト

| ファイル | 改修内容 |
|---------|---------|
| `scripts/pavlok.py` | 変更なし |
| `scripts/slack.py` | BlockKit対応追加 |
| `scripts/behavior_log.py` | `action_logs`対応 |

### 3.2 新規作成スクリプト

| ファイル | 用途 |
|---------|------|
| `scripts/plan.py` | planイベント実行 |
| `scripts/remind.py` | remindイベント実行 |
| `scripts/agent_call.py` | Agent呼出 |
| `scripts/worker.py` | Punishment Worker |
| `scripts/init_db.py` | DB初期化 |

## 4. 判断基準

### 4.1 削除基準

以下のいずれかに該当する場合は削除:

1. **依存関係がない**: 他のコードから参照されていない
2. **再利用性が低い**: v0.3のアーキテクチャに適合しない
3. **リスクが低い**: 削除しても復旧容易

### 4.2 残す基準

以下のいずれかに該当する場合は残す:

1. **再利用可能**: 最小限の修正で流用可能
2. **ビジネスロジック**: Pavlok API等の外部連携
3. **移行コストが高い**: 新規作成より修正が容易

## 5. 削除実行タイミング

```
Phase 1: DB Migration
  - DROP TABLE実行
  - 新規テーブル作成

Phase 2: スクリプト削除
  - 削除リストのスクリプトを削除
  - git commit

Phase 3: コード修正
  - 再利用スクリプトの改修
  - 新規スクリプト作成
```

## 6. ロールバック計画

万が一削除が必要になった場合:

1. Gitの履歴から復元可能
2. `git checkout HEAD~1 -- <file>` で復元
3. DBはバックアップから復元

## 7. 関連ドキュメント

- ADR-004: 設定値の採用リスト
- v0.3_design.md: 9. Migration計画
