# Oni System v0.3 運用手順書

## 1. デプロイ手順

### 1.1 前提条件

- Python 3.12
- SQLite 3
- 環境変数設定済み（`.env`ファイル）

### 1.2 初回デプロイ

```bash
# 1. リポジトリをクローン
git clone <repository-url>
cd pavlok_CLI_agent

# 2. 仮想環境作成
python -m venv .venv
source .venv/bin/activate

# 3. 依存関係インストール
pip install -e ".[dev]"

# 4. データベース初期化
python -c "from backend.models import Base, create_engine; engine = create_engine('sqlite:///app.db'); Base.metadata.create_all(engine)"

# 5. 初期設定値を投入
python scripts/init_config.py
```

### 1.3 アップデート

```bash
# 1. コードをプル
git pull origin main

# 2. 依存関係を更新
pip install -e ".[dev]"

# 3. マイグレーション実行（必要な場合）
# 重要: alembic.ini は backend/ 配下にあるため、config を明示する
uv run --project . alembic -c backend/alembic.ini upgrade head
# もしくは .venv を直接使う場合
.venv/bin/alembic -c backend/alembic.ini upgrade head

# 4. DB再生成が必要な場合（必要時のみ）
rm -f oni.db
uv run --project . alembic -c backend/alembic.ini upgrade head

# 5. サービス再起動
systemctl restart oni-api
systemctl restart oni-worker
```

---

## 2. サービス管理

### 2.1 systemdサービス定義

`init.sh` から流用できるよう、実行ユーザーを動的解決する手順にします。

```bash
# sudo 実行時は SUDO_USER を優先。未指定なら現在ユーザー。
export SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
export SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}"
export SERVICE_HOME="${SERVICE_HOME:-$(getent passwd "$SERVICE_USER" | cut -d: -f6)}"
if [ -z "$SERVICE_HOME" ]; then
  export SERVICE_HOME="/home/$SERVICE_USER"
fi

# 必要なら外から上書き可能
export APP_DIR="${APP_DIR:-$SERVICE_HOME/pavlok_CLI_agent}"
export LOG_DIR="${LOG_DIR:-$APP_DIR/backend/log}"

mkdir -p "$LOG_DIR"
```

```bash
# /etc/systemd/system/oni-api.service
sudo tee /etc/systemd/system/oni-api.service >/dev/null <<EOF
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
EnvironmentFile=-$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/uvicorn.out
StandardError=append:$LOG_DIR/uvicorn.out

[Install]
WantedBy=multi-user.target
EOF
```

```bash
# /etc/systemd/system/oni-worker.service
sudo tee /etc/systemd/system/oni-worker.service >/dev/null <<EOF
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
EnvironmentFile=-$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python -m backend.worker.worker
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/worker.out
StandardError=append:$LOG_DIR/worker.out

[Install]
WantedBy=multi-user.target
EOF
```

### 2.2 サービス操作コマンド

```bash
# 変数を設定（2.1と同じ）
export SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
export SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}"
export SERVICE_HOME="${SERVICE_HOME:-$(getent passwd "$SERVICE_USER" | cut -d: -f6)}"
if [ -z "$SERVICE_HOME" ]; then
  export SERVICE_HOME="/home/$SERVICE_USER"
fi
export APP_DIR="${APP_DIR:-$SERVICE_HOME/pavlok_CLI_agent}"
export LOG_DIR="${LOG_DIR:-$APP_DIR/backend/log}"

# ユニット反映
sudo systemctl daemon-reload

# 自動起動有効化 + 起動
sudo systemctl enable --now oni-api oni-worker

# 稼働確認
sudo systemctl status oni-api --no-pager
sudo systemctl status oni-worker --no-pager
sudo systemctl is-active oni-api oni-worker

# 再起動
sudo systemctl restart oni-api oni-worker

# 停止
sudo systemctl stop oni-api oni-worker

# 起動
sudo systemctl start oni-api oni-worker

# ヘルスチェック
curl -sS http://127.0.0.1:8000/health

# ログ確認（journal）
sudo journalctl -u oni-api -f
sudo journalctl -u oni-worker -f

# ログ確認（ファイル）
tail -f "$LOG_DIR/uvicorn.out"
tail -f "$LOG_DIR/worker.out"
```

### 2.3 ログローテート設定（必須）

`systemd` で `StandardOutput=append:` を使っているため、`logrotate` で肥大化を防ぎます。

```bash
# 変数を設定（2.1と同じ）
export SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
export SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}"
export SERVICE_HOME="${SERVICE_HOME:-$(getent passwd "$SERVICE_USER" | cut -d: -f6)}"
if [ -z "$SERVICE_HOME" ]; then
  export SERVICE_HOME="/home/$SERVICE_USER"
fi
export APP_DIR="${APP_DIR:-$SERVICE_HOME/pavlok_CLI_agent}"
export LOG_DIR="${LOG_DIR:-$APP_DIR/backend/log}"

# /etc/logrotate.d/oni-system
sudo tee /etc/logrotate.d/oni-system >/dev/null <<EOF
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
EOF

# 設定確認（dry run）
sudo logrotate -d /etc/logrotate.d/oni-system

# 手動実行テスト
sudo logrotate -f /etc/logrotate.d/oni-system

# 反映確認
ls -lh "$LOG_DIR"
```

---

## 3. バックアップと復元

### 3.1 データベースバックアップ

```bash
# 手動バックアップ
sqlite3 app.db ".backup 'backup/app.db.$(date +%Y%m%d_%H%M%S)'"

# cronで毎日バックアップ
# crontab -e
0 3 * * * sqlite3 /opt/oni/app.db ".backup '/opt/oni/backup/app.db.$(date +\%Y\%m\%d_\%H\%M\%S)'"
```

### 3.2 復元手順

```bash
# サービス停止
systemctl stop oni-api oni-worker

# バックアップから復元
cp /opt/oni/backup/app.db.20260214_030000 /opt/oni/app.db

# サービス再開
systemctl start oni-api oni-worker
```

---

## 4. 監視

### 4.1 ヘルスチェック

```bash
# APIヘルスチェック
curl http://localhost:8000/health

# 期待されるレスポンス
{"status": "healthy"}
```

### 4.2 ログ監視

重要なログパターン：

| パターン | 重要度 | 対応 |
|---------|-------|------|
| `Error processing schedule` | ERROR | スケジュール処理エラーを調査 |
| `Script execution failed` | ERROR | スクリプト実行エラーを調査 |
| `Slack signature verification failed` | WARN | セキュリティ警告 |
| `Daily zap limit reached` | INFO | 日次上限到達（正常） |

### 4.3 メトリクス

監視すべきメトリクス：

- API レスポンスタイム
- Worker 処理数/分
- データベースサイズ
- 罰実行回数/日

---

## 5. トラブルシューティング

### 5.1 APIが起動しない

```bash
# ポート使用状況確認
lsof -i :8000

# 環境変数確認
env | grep -E "(SLACK|PAVLOK|DATABASE)"

# ログ確認
journalctl -u oni-api -n 100
```

### 5.2 Workerが動作しない

```bash
# プロセス確認
ps aux | grep worker

# データベース接続確認
sqlite3 app.db "SELECT COUNT(*) FROM schedules WHERE state='pending'"

# ログ確認
journalctl -u oni-worker -n 100
```

### 5.3 Slack連携エラー

1. Slack Appの設定を確認
2. OAuthトークンが有効か確認
3. Webhook URLが正しいか確認
4. 署名検証が正しく設定されているか確認

### 5.4 Pavlok連携エラー

1. APIキーが有効か確認
2. デバイスがオンラインか確認
3. APIレート制限に達していないか確認

---

## 6. セキュリティ運用

### 6.1 定期確認事項

- [ ] アクセスログの異常がないか
- [ ] 設定変更監査ログの確認
- [ ] 認可ユーザーリストの更新
- [ ] APIキーのローテーション

### 6.2 インシデント対応

1. 異常を検知したら即座にサービスを停止
2. ログを保全
3. 原因を調査
4. 必要に応じて認証情報をローテーション
5. 修正後にサービス再開

---

## 7. 考慮ポイント

### 7.1 スケーラビリティ

- 現在の設計は1ユーザー・1サーバー前提
- 将来的なマルチユーザー対応はDBスキーマで準備済み

### 7.2 可用性

- APIとWorkerは独立して動作可能
- Workerが停止してもAPIは機能する（ただし処理は滞留）
- APIが停止してもWorkerは1分間隔で処理を継続

### 7.3 パフォーマンス

- 設定値は60秒キャッシュされる
- DBはSQLiteのため、大量データには注意
- Slack APIのレート制限に注意

---

## 8. 連絡先

技術的な問題については、開発チームまでお問い合わせください。
