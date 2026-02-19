# Oni System v0.3 ユーザーガイド

## 概要

Oni System v0.3は、Slackと連携したコミットメント管理システムです。
Pavlokデバイスを使用して、目標達成をサポートします。

---

## 1. はじめに

### 1.1 システム要件

- Python 3.12
- Slack Workspace（管理者権限が必要）
- Pavlokデバイス（オプション）

### 1.2 必要な環境変数

以下の環境変数を`.env`ファイルに設定してください：

```bash
# インフラ設定
DATABASE_URL=sqlite:///./app.db
TIMEZONE=Asia/Tokyo

# Slack認証
SLACK_BOT_USER_OAUTH_TOKEN=xoxb-...
SLACK_USER_OAUTH_TOKEN=xoxp-...
SLACK_SIGNING_SECRET=...

# Pavlok認証
PAVLOK_API_KEY=...

# セキュリティ
INTERNAL_SECRET=your-internal-secret-key
AUTHORIZED_USERS=U03JBULT484
```

---

## 2. Slackコマンド一覧

### 2.1 /base_commit

コミットメント（毎日の予定）を登録・編集します。

**使用方法:**
```
/base_commit
```

**表示される内容:**
- コミットメント入力モーダル
- 時刻選択機能
- タスク名入力

### 2.2 /stop

罰機構を一時停止します。

**使用方法:**
```
/base_commit
```

**注意:**
- `/restart`で再開するまで罰は実行されません
- スケジュールは継続して記録されます

### 2.3 /restart

停止した罰機構を再開します。

**使用方法:**
```
/restart
```

### 2.4 /config

各種設定を変更します。

**使用方法:**
```
/config          # 設定モーダルを開く
/config view     # 現在の設定を表示
/config reset    # デフォルト値にリセット
/config rollback <key>  # 特定の設定をロールバック
```

**設定可能な項目:**

| 設定キー | デフォルト | 説明 |
|---------|-----------|------|
| PAVLOK_TYPE_PUNISH | zap | 罰の種類 (zap/vibe/beep) |
| PAVLOK_VALUE_PUNISH | 35 | 罰の強度 (0-100) |
| LIMIT_DAY_PAVLOK_COUNTS | 100 | 1日の最大ZAP回数 |
| LIMIT_PAVLOK_ZAP_VALUE | 100 | 最大ZAP強度 |
| IGNORE_INTERVAL | 900 | ignore検知間隔（秒） |
| IGNORE_JUDGE_TIME | 3 | ignore判定時間（秒） |
| IGNORE_MAX_RETRY | 5 | ignore最大再試行回数 |
| COACH_CHARACTOR | うる星やつらのラムちゃん | agent_callコメント生成時の口調 |

**`.env`で管理する項目（/configでは非表示）:**

| 設定キー | デフォルト | 説明 |
|---------|-----------|------|
| TIMEOUT_REMIND | 600 | リマインドタイムアウト（秒） |
| TIMEOUT_REVIEW | 600 | 振り返りタイムアウト（秒） |
| RETRY_DELAY | 5 | リトライ遅延（分） |

---

## 3. イベントフロー

### 3.1 Plan イベント

毎日指定時刻に「今日の予定」を登録するリマインドが届きます。

1. Workerがplanイベントを検知
2. Slackに「予定を登録」ボタン付きメッセージを投稿
3. ボタンをクリックしてモーダルを開く
4. 予定を入力して送信
5. 各時刻にremindイベントがスケジュールされる

### 3.2 Remind イベント

登録した時刻にリマインドが届きます。

1. Workerがremindイベントを検知
2. Slackに「やりました！/やれません」ボタン付きメッセージを投稿
3. ボタンをクリックして応答
4. YES → 完了メッセージ
5. NO → Pavlok実行 + 罰メッセージ

### 3.3 Ignore モード

応答がない場合の自動対応です。

1. 指定時間（デフォルト15分）経過で検知
2. 初回: vibe（振動）100%
3. 2回目以降: zap（電気ショック）35%〜最大100%
4. 最大到達時: タスク自動キャンセル

---

## 4. セキュリティ

### 4.1 認可ユーザー

`AUTHORIZED_USERS`に含まれるユーザーのみがコマンドを実行できます。

### 4.2 罠強度の制限

- 最大強度は`LIMIT_PAVLOK_ZAP_VALUE`で制限されます
- 1日の最大回数は`LIMIT_DAY_PAVLOK_COUNTS`で制限されます
- 強度80以上は警告が表示されます

---

## 5. トラブルシューティング

### 5.1 コマンドが反応しない

- Slack Appの権限を確認してください
- `AUTHORIZED_USERS`に自分のユーザーIDが含まれているか確認してください

### 5.2 Pavlokが動作しない

- Pavlok APIキーが正しいか確認してください
- Pavlokデバイスがオンラインか確認してください

### 5.3 テスト実行方法

```bash
# 全テスト実行
pytest tests_v3/

# 特定のテストのみ
pytest tests_v3/worker/
pytest tests_v3/api/
```

---

## 6. 運用

### 6.1 起動方法

```bash
# FastAPIサーバー起動
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Worker起動（別プロセス）
python -m backend.worker.worker
```

### 6.2 ログ確認

```bash
# サーバーログ
tail -f logs/server.log

# Workerログ
tail -f logs/worker.log
```

### 6.3 設定変更の監査

設定変更は`config_audit_log`テーブルに記録されます。

```sql
SELECT * FROM config_audit_log ORDER BY changed_at DESC LIMIT 10;
```

---

## 7. サポート

問題が発生した場合は、以下の情報を添えて報告してください：

- エラーメッセージ
- 実行したコマンド
- ログの該当箇所
