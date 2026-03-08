# Oni System - Specification v0.3 (Revised)

## 前提
- タイムゾーンは JST 固定
- 実行判定は `now >= run_at`
- parentプロセスは常に1つのみ
- サブプロセスは複数起動可
- PoC段階のためデータアーカイブは未考慮
- YES/NOは先勝ち（最初の応答のみ有効）

---

# ユーザーシナリオ

## init

1. ユーザーが Slack で `/base_commit` を実行
2. コミットメント作成UIを返却
3. ユーザーが「毎日何時に何をやるか」を送信
4. backendはcommitmentをDB登録
5. 当日分の `plan` event が存在しない場合、scheduleに `plan` を登録
6. Slackに完了通知

---

## plan

### 実行条件
- `schedule.event_type = plan`
- `state = pending`
- `run_at <= now`

### 実行フロー

1. 対象レコードを原子的に `processing` に更新
2. `plan` スクリプト実行
3. Slackに24時間分の予定を BlockKit 形式で投稿（thread_ts保存）
4. ユーザーが plan_api で送信
5. DB更新:
   - 対象planを `done`
   - `やる` → remind event をINSERT（state=pending）
   - `やらない` → 行動ログに記録
6. Slackスレッドに登録完了通知
7. Agent実行:
   ```bash
   echo {plan_prompt} | codex exec
   ```

8. 出力結果を schedule.comment_json に保存

### Retry

* Slack API失敗時は stateをpendingに戻す
* retry最大3回
* 3回失敗で `failed`

---

## remind

### 実行条件

* `event_type = remind`
* `state = pending`
* `run_at <= now`

### 実行フロー

1. 原子的に `processing` 更新
2. Slackに BlockKit投稿（thread_ts使用）
3. YES/NOボタン表示
4. ユーザー応答処理（idempotency_key管理 + UPSERT）

### YESの場合

* 行動ログINSERT
* state = done
* YESコメントをスレッド返信

### NOの場合

* 行動ログINSERT
* pavloc NOモード実行
* NOコメント返信

---

## ignoreモード（未応答）

### 発火条件

* state = processing（event_type=plan）
* `ignore_time = (now - run_at) // ignore_interval`

### 実行条件

* panishmentテーブルに (schedule_id, ignore_time) が存在しない

### アルゴリズム

* ignore_time == 1

  * vibe: 100

* ignore_time > 1

  * zap: min(35 + (10 * (ignore_time - 2)), 100)

* 100到達時:

  * state = canceled
  * 行動ログ記録
  * 終了

---

## NOモード

* 行動ログから最新YESまで遡る
* NO_count算出
* zap: min(35 + (10 * (NO_count - 1)), 100)
* panishmentテーブルで重複防止

---

## stop

* `/stop` でpanishment停止
* 実行中処理はtransaction rollback
* 外部APIは巻き戻し不可
* ログ記録

---

## restart

* `/restart` で再開
* ログ記録

---

# システム構成

## command_watcher

* `/base_commit`
* `/stop`
* `/restart`
* Slack署名検証必須

---

## panishment機構

1分間隔で監視

### 監視ロジック

1. `pending AND run_at <= now` を取得
2. 1件ずつ `processing` に原子的更新
3. 更新成功プロセスのみ実行
4. plan成功 → stateはprocessing維持、remind成功 → done
5. 失敗 → failed
6. 同一サイクル内で `processing AND run_at <= now AND event_type=plan` を監視し、ignore検知を実行

---

# DB設計

## schedule

| column       | type                                                       | note      |
| ------------ | ---------------------------------------------------------- | --------- |
| id           | uuid                                                       | PK        |
| user_id      | uuid                                                       |           |
| event_type   | enum(plan, remind)                                         |           |
| run_at       | datetime(JST)                                              |           |
| state        | enum(pending, processing, done, skipped, failed, canceled) |           |
| thread_ts    | string                                                     | Slackスレッド |
| comment_json | json                                                       | Agent出力   |
| retry_count  | int                                                        | default 0 |

### 制約

* (user_id, date(run_at), event_type=plan) UNIQUE

---

## action_logs

| id | uuid |
| ------------ | ---------------------------------------------------------- |
| schedule_id | uuid |
| result | enum(YES, NO, AUTO_IGNORE) |
| created_at | datetime |

---

## panishment

| id | uuid |
| ------------ | ---------------------------------------------------------- |
| schedule_id | uuid |
| mode | enum(ignore, no) |
| count | int |
| created_at | datetime |

UNIQUE(schedule_id, mode, count)

---

# Slack Interaction

* idempotency_key保存
* UPSERT（あと勝ち）
* Slack署名検証必須

---

# セキュリティ

* Slack署名検証
* SQLは必ずバインド
* `/stop` `/restart` は引数禁止
* `/base_commit` 入力長制限

---

# Agent

* timeout: 15分
* 失敗時はSlack通知
* 1万token未満想定
* sanitization未考慮（単一ユーザー前提）

---

# 原則

* scheduleテーブルが唯一の実行真実
* YES/NOは最初の応答のみ有効
* 罰は数学で決まる
* 人の嘘も観測対象

```
