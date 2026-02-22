# Oni System v0.3 運用手順書

## 0. このドキュメントの位置づけ

この手順書は `README.md` と `documents/v0.3/user_guide.md` を完了した後に、
本番/常駐サーバー運用を行う担当者向けの手順です。

- `README.md`: 初期セットアップ、Slack/Pavlok連携、ローカル起動
- `documents/v0.3/user_guide.md`: エンドユーザー操作
- `documents/v0.3/operations_guide.md`: サーバー構築、常駐運用、監視、復旧

## 1. 新規サーバー準備（v0.2内容を統合）

### 1.1 セキュリティグループ/ファイアウォール

最低限、次を許可します。

- `22/tcp`: 運用者IPのみ（SSH）
- `8000/tcp`: APIを直接公開する場合のみ

補足:

- リバースプロキシ配下で運用する場合は `8000/tcp` を閉じ、プロキシからの到達だけ許可してください。
- v0.2で詰まりやすかった通り、クラウド側のセキュリティグループ割り当て漏れがあるとSSHできません。

### 1.2 初回SSHと一般ユーザー作成

初回のみ root で接続し、一般ユーザーを作成します。

```bash
ssh root@<VPS_IP>
adduser <service_user>
usermod -aG sudo <service_user>
```

作成後は一般ユーザーで再接続します。

```bash
exit
ssh <service_user>@<VPS_IP>
sudo -v
```

### 1.3 SSH鍵ログイン化とroot封印（推奨）

ローカルで鍵未作成なら作成します。

```bash
ssh-keygen -t ed25519
ssh-copy-id <service_user>@<VPS_IP>
```

`/etc/ssh/sshd_config` を調整します。

```text
PermitRootLogin no
PasswordAuthentication no
```

反映:

```bash
sudo systemctl restart ssh
```

注意:

- 先に別ターミナルで一般ユーザーSSHが成功することを確認してから root ログイン禁止を適用してください。

## 2. デプロイ

### 2.1 推奨: `init.sh` で自動セットアップ

`init.sh` は以下をまとめて実行します。

- `uv` 導入
- 依存同期 (`uv sync --extra dev`)
- Alembic migration
- `pytest -q` による最低限の健全性確認
- systemd unit 反映
- logrotate設定
- サービス起動とヘルスチェック

手順:

```bash
# サーバー上
cd ~
git clone https://github.com/motoya0118/pavlok_CLI_agent.git
cd pavlok_CLI_agent

# .env作成
cp env-sample .env
# 必須値を編集: PAVLOK_API_KEY, SLACK_BOT_USER_OAUTH_TOKEN, SLACK_SIGNING_SECRET, ONI_INTERNAL_SECRET, SLACK_CHANNEL

# 自動セットアップ実行
bash init.sh
```

### 2.2 ソース持ち込み方針（v0.2運用タスクを統合）

- Dockerは使わず、サーバー上に直接実行環境を構築します。
- 通常は `git clone` を推奨します。
- 何らかの理由でファイルコピー配備する場合は、最低限次を揃えてください。
  - `.codex`
  - `prompts`
  - `scripts`
  - `backend`
  - `documents`
  - ルート直下の設定ファイル群（`pyproject.toml`, `uv.lock`, `env-sample` など）

### 2.3 既存データ引き継ぎ（任意）

ローカルのSQLiteデータを引き継ぐ場合のみ実施します。

```bash
# ローカルで実行
scp /path/to/oni.db <service_user>@<VPS_IP>:~/pavlok_CLI_agent/oni.db
```

`DATABASE_URL` を `.env` で独自設定している場合は、そのDB実体を引き継いでください。

### 2.4 Codexをサーバーで使う場合（任意）

v0.2運用タスクで使っていた手順を踏襲します。

```bash
# ローカルで実行
scp ~/.codex/auth.json <service_user>@<VPS_IP>:~/.codex/auth.json
scp ~/.codex/config.toml <service_user>@<VPS_IP>:~/.codex/config.toml
```

サーバー上で確認:

```bash
codex exec こんにちは
```

## 3. systemd サービス管理

### 3.1 ユニット定義（手動管理する場合）

`init.sh` を使わず手動運用する場合のみ必要です。

```bash
export SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
export SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}"
export SERVICE_HOME="${SERVICE_HOME:-$(getent passwd "$SERVICE_USER" | cut -d: -f6)}"
[ -z "$SERVICE_HOME" ] && export SERVICE_HOME="/home/$SERVICE_USER"

export APP_DIR="${APP_DIR:-$SERVICE_HOME/pavlok_CLI_agent}"
export LOG_DIR="${LOG_DIR:-$APP_DIR/backend/log}"
mkdir -p "$LOG_DIR"
```

```bash
# /etc/systemd/system/oni-api.service
sudo tee /etc/systemd/system/oni-api.service >/dev/null <<EOF_UNIT
[Unit]
Description=Oni System FastAPI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/uvicorn.out
StandardError=append:$LOG_DIR/uvicorn.out

[Install]
WantedBy=multi-user.target
EOF_UNIT
```

```bash
# /etc/systemd/system/oni-worker.service
sudo tee /etc/systemd/system/oni-worker.service >/dev/null <<EOF_UNIT
[Unit]
Description=Oni System Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python -m backend.worker.worker
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/worker.out
StandardError=append:$LOG_DIR/worker.out

[Install]
WantedBy=multi-user.target
EOF_UNIT
```

適用:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now oni-api oni-worker
```

### 3.2 日常操作

```bash
# 状態確認
sudo systemctl status oni-api --no-pager
sudo systemctl status oni-worker --no-pager
sudo systemctl is-active oni-api oni-worker

# 再起動
sudo systemctl restart oni-api oni-worker

# 停止/起動
sudo systemctl stop oni-api oni-worker
sudo systemctl start oni-api oni-worker

# ヘルスチェック
curl -sS http://127.0.0.1:8000/health
# 期待例: {"status":"ok", ...}

# ログ
sudo journalctl -u oni-api -f
sudo journalctl -u oni-worker -f
```

### 3.3 logrotate（必須）

```bash
sudo tee /etc/logrotate.d/oni-system >/dev/null <<EOF_ROTATE
$LOG_DIR/uvicorn.out $LOG_DIR/worker.out {
    daily
    rotate 14
    size 20M
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
    su $SERVICE_USER $SERVICE_GROUP
    create 0640 $SERVICE_USER $SERVICE_GROUP
}
EOF_ROTATE

sudo logrotate -d /etc/logrotate.d/oni-system
sudo logrotate -f /etc/logrotate.d/oni-system
```

## 4. バックアップと復元

SQLite運用（`DATABASE_URL` 未変更時）を前提に記載します。

```bash
export APP_DIR="${APP_DIR:-$HOME/pavlok_CLI_agent}"
export DB_PATH="${DB_PATH:-$APP_DIR/oni.db}"
mkdir -p "$APP_DIR/backup"
```

### 4.1 バックアップ

```bash
sqlite3 "$DB_PATH" ".backup '$APP_DIR/backup/oni.db.$(date +%Y%m%d_%H%M%S)'"
```

cron例:

```bash
0 3 * * * sqlite3 /home/<service_user>/pavlok_CLI_agent/oni.db ".backup '/home/<service_user>/pavlok_CLI_agent/backup/oni.db.$(date +\%Y\%m\%d_\%H\%M\%S)'"
```

### 4.2 復元

```bash
sudo systemctl stop oni-api oni-worker
cp /home/<service_user>/pavlok_CLI_agent/backup/oni.db.<timestamp> /home/<service_user>/pavlok_CLI_agent/oni.db
sudo systemctl start oni-api oni-worker
```

## 5. 監視

### 5.1 最低限の監視項目

- APIヘルス (`/health`)
- `oni-api` / `oni-worker` の systemd active 状態
- DBファイルサイズ
- Pavlok実行回数（上限到達の頻度）

### 5.2 ログ監視の目安

| パターン | 重要度 | 対応 |
| --- | --- | --- |
| `Error processing schedule` | ERROR | schedule処理失敗。対象IDを追跡して再実行可否を判断 |
| `Script execution failed` | ERROR | `plan.py`/`remind.py` の実行失敗 |
| `Invalid signature` | WARN | Slack署名不一致。`SLACK_SIGNING_SECRET` とSlack App設定を確認 |
| `daily zap limit reached` | INFO | 1日上限到達。設定見直し判断材料 |

## 6. トラブルシューティング

### 6.1 APIが起動しない

```bash
lsof -i :8000
sudo journalctl -u oni-api -n 100 --no-pager
```

確認ポイント:

- `.env` の必須値不足
- `.venv` 不整合（`uv sync --extra dev` を再実行）

### 6.2 Workerが動かない

```bash
sudo journalctl -u oni-worker -n 100 --no-pager
sqlite3 ~/pavlok_CLI_agent/oni.db "SELECT COUNT(*) FROM schedules WHERE state='pending';"
```

### 6.3 Slack連携で401が出る

- `SLACK_SIGNING_SECRET` がSlack Appの値と一致しているか
- Slack Request URLが正しいか（`/slack/gateway` など）

### 6.4 Pavlok連携が失敗する

- `PAVLOK_API_KEY` の有効性
- デバイスのオンライン状態
- 日次上限 (`LIMIT_DAY_PAVLOK_COUNTS`) 到達状況

## 7. アップデート手順（安全版）

```bash
cd ~/pavlok_CLI_agent
git pull origin main
uv sync --extra dev
.venv/bin/alembic -c backend/alembic.ini upgrade head
sudo systemctl restart oni-api oni-worker
curl -sS http://127.0.0.1:8000/health
```

注意:

- 通常アップデートで `oni.db` を削除しないでください。

## 8. 定期運用チェックリスト

- [ ] `sudo systemctl is-active oni-api oni-worker` が `active`
- [ ] `SLACK_SIGNING_SECRET` / `ONI_INTERNAL_SECRET` / `PAVLOK_API_KEY` のローテーション計画がある
- [ ] `backup/` に日次バックアップが生成されている
- [ ] `uvicorn.out` / `worker.out` の肥大化が抑制されている
