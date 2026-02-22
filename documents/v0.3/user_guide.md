# Oni System v0.3 ユーザーガイド

## このガイドの位置づけ

このドキュメントは、`README.md` の導入手順（セットアップ、Slack/Pavlok連携、API/Worker起動）が完了した後に読む運用ガイドです。  
インフラ運用（systemd、logrotate、バックアップ）は `documents/v0.3/operations_guide.md` を参照してください。

## 1. 最短の使い方

1. Slackで `/base_commit` を実行し、毎日やるタスクを登録します。
2. 通常は次のWorkerサイクル（最長約1分）で plan 通知が届きます。すぐ編集したい場合は `/plan` を実行します。
3. remind 通知に対して `やりました` または `やれません` で応答します。

## 2. Slackコマンド

### 2.1 `/base_commit`

毎日繰り返すコミットメントを登録・編集します。

- 最大10件まで登録可能です。
- 送信時は既存コミットメントを洗い替えします。
- タスク名だけ、時刻だけの行は保存時にバリデーションエラーになります。

### 2.2 `/plan`

「今日の予定」モーダルを手動で開きます。

- 各タスクごとに `今日/明日` と実行時刻を設定できます。
- 各行の `スキップ` をONにすると、その行の remind は作成されません。
- 送信時に、現在の pending/processing スケジュールを洗い替えし、選択内容で remind と次回 plan を再作成します。

### 2.3 `/config`

設定モーダルを開きます。

- v0.3 のユーザー操作はモーダル更新が前提です。
- `/config view` `/config reset` `/config rollback` のようなサブコマンドは現行実装ではサポートしていません。

### 2.4 `/stop`

鬼コーチの自動処理を一時停止します。

- `SYSTEM_PAUSED=true` が設定され、Workerサイクルがスキップされます。
- 停止中は新規の plan/remind 実行や ignore 監視は進みません。

### 2.5 `/restart`

`/stop` で停止した処理を再開します。

- `SYSTEM_PAUSED=false` に戻ります。
- 次回Workerサイクルから通常処理が再開されます。

### 2.6 `/help`

Slack上でコマンド一覧と利用要点を表示します。

## 3. 日次フロー

### 3.1 Plan フェーズ

1. plan イベントで「予定を登録」通知が届きます。
2. planモーダル送信後、当日分の remind と次回 plan が登録されます。

### 3.2 Remind フェーズ

1. 指定時刻に remind 通知が届きます。
2. `やりました` は DONE 記録になります。
3. `やれません` は NO 記録になり、設定値に応じたPavlok刺激が実行されます。

### 3.3 Ignore フェーズ（未応答）

- `IGNORE_INTERVAL`（既定900秒）ごとに ignore 判定が走ります。
- 1回目は `vibe 100`、2回目以降は `zap` を段階的に強化します。
- `IGNORE_MAX_RETRY` 超過時、または強度上限到達時は対象タスクが自動キャンセルされます。

## 4. 設定項目

### 4.1 `/config` で更新する項目

| 設定キー | デフォルト | 説明 |
| --- | --- | --- |
| `PAVLOK_TYPE_PUNISH` | `zap` | NO時の刺激タイプ（`zap`/`vibe`/`beep`） |
| `PAVLOK_VALUE_PUNISH` | `35` | NO時の基準強度（0-100） |
| `LIMIT_DAY_PAVLOK_COUNTS` | `100` | 1日のZAP実行上限回数 |
| `LIMIT_PAVLOK_ZAP_VALUE` | `100` | ZAP強度の上限 |
| `PAVLOK_TYPE_NOTION` | `vibe` | 通知時の刺激タイプ（`zap`/`vibe`/`beep`） |
| `PAVLOK_VALUE_NOTION` | `35` | 通知時の刺激強度（0-100） |
| `IGNORE_INTERVAL` | `900` | ignore判定間隔（秒。300/600/900/1800） |
| `IGNORE_JUDGE_TIME` | `3` | ignore判定時間（秒） |
| `IGNORE_MAX_RETRY` | `5` | ignore最大再試行回数 |
| `COACH_CHARACTOR` | `うる星やつらのラムちゃん` | コメント生成時の口調設定（最大100文字） |

### 4.2 `.env` でのみ管理する項目

| 設定キー | デフォルト | 説明 |
| --- | --- | --- |
| `TIMEOUT_REMIND` | `600` | remind応答タイムアウト（秒） |
| `TIMEOUT_REVIEW` | `600` | 振り返り応答タイムアウト（秒） |
| `RETRY_DELAY` | `5` | Workerリトライ遅延（分） |

## 5. 環境変数メモ（ユーザー向け）

`env-sample` を基準に、少なくとも次を設定してください。

- `PAVLOK_API_KEY`
- `SLACK_BOT_USER_OAUTH_TOKEN`
- `SLACK_CHANNEL`（または `SLACK_CHANNEL_ID`）
- `SLACK_SIGNING_SECRET`
- `DATABASE_URL`（未指定時は `sqlite:///./oni.db`）

内部APIを利用する構成では `ONI_INTERNAL_SECRET` も設定してください。

## 6. トラブルシューティング

### 6.1 Slashコマンドが401になる

- `SLACK_SIGNING_SECRET` の設定値とSlack App側の Signing Secret を一致させてください。
- Slack Appの Request URL が `/slack/gateway` または `/slack/command`/`/slack/interactive` の正しいエンドポイントを向いているか確認してください。

### 6.2 `/plan` や `/config` でモーダルが開かない

- Slackから直接スラッシュコマンドを実行し、`trigger_id` が渡る経路で再実行してください。
- `SLACK_BOT_USER_OAUTH_TOKEN` の権限を確認してください。

### 6.3 remindが来ない

- Workerが起動しているか確認してください。
- `/stop` で停止中の場合は `/restart` を実行してください。
- `/base_commit` で有効なコミットメントが登録されているか確認してください。

### 6.4 Pavlok刺激が来ない

- `PAVLOK_API_KEY` が有効か確認してください。
- デバイスがアカウントに紐付いてオンラインか確認してください。
- `LIMIT_DAY_PAVLOK_COUNTS` に到達していないか確認してください。

## 7. 関連ドキュメント

- セットアップ全体: `README.md`
- サービス運用: `documents/v0.3/operations_guide.md`
