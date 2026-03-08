#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[init] %s\n' "$*"
}

warn() {
  printf '[init][WARN] %s\n' "$*" >&2
}

die() {
  printf '[init][ERROR] %s\n' "$*" >&2
  exit 1
}

run_as_service_user() {
  local cmd="$1"
  if [ "$(id -un)" = "$SERVICE_USER" ]; then
    bash -lc "$cmd"
  else
    sudo -u "$SERVICE_USER" bash -lc "$cmd"
  fi
}

require_sudo_once() {
  if [ "$(id -u)" -eq 0 ]; then
    return
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    die "sudo が見つかりません。root で実行するか sudo をインストールしてください。"
  fi
  if sudo -n true 2>/dev/null; then
    return
  fi
  log "systemd/logrotate 設定のため sudo 認証を行います（必要なら1回だけパスワード入力）。"
  sudo -v
}

resolve_paths() {
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
  SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER" 2>/dev/null || true)}"
  if [ -z "$SERVICE_GROUP" ]; then
    SERVICE_GROUP="$SERVICE_USER"
  fi

  SERVICE_HOME="${SERVICE_HOME:-$(getent passwd "$SERVICE_USER" 2>/dev/null | cut -d: -f6 || true)}"
  if [ -z "$SERVICE_HOME" ]; then
    SERVICE_HOME="/home/$SERVICE_USER"
  fi

  APP_DIR="${APP_DIR:-$SCRIPT_DIR}"
  LOG_DIR="${LOG_DIR:-$APP_DIR/backend/log}"
  UNIT_API="${UNIT_API:-oni-api}"
  UNIT_WORKER="${UNIT_WORKER:-oni-worker}"
  FASTAPI_PORT="${FASTAPI_PORT:-8000}"
  SSH_PORT="${SSH_PORT:-22}"
  API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:${FASTAPI_PORT}/health}"
}

validate_port() {
  local label="$1"
  local port="$2"
  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    die "$label は数値で指定してください: $port"
  fi
  if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
    die "$label は 1-65535 の範囲で指定してください: $port"
  fi
}

check_prerequisites() {
  command -v systemctl >/dev/null 2>&1 || die "systemctl が見つかりません。"
  command -v curl >/dev/null 2>&1 || die "curl が見つかりません。"
  command -v logrotate >/dev/null 2>&1 || die "logrotate が見つかりません。"

  [ -d "$APP_DIR" ] || die "APP_DIR が存在しません: $APP_DIR"
  [ -f "$APP_DIR/pyproject.toml" ] || die "pyproject.toml が見つかりません: $APP_DIR"
  [ -f "$APP_DIR/backend/alembic.ini" ] || die "backend/alembic.ini が見つかりません: $APP_DIR"

  validate_port "FASTAPI_PORT" "$FASTAPI_PORT"
  validate_port "SSH_PORT" "$SSH_PORT"
}

ensure_env_file() {
  if [ -f "$APP_DIR/.env" ]; then
    return
  fi

  if [ -f "$APP_DIR/env-sample" ]; then
    log ".env がないため env-sample から初期生成します。"
    run_as_service_user "cp '$APP_DIR/env-sample' '$APP_DIR/.env'"
    die ".env を編集して再実行してください: $APP_DIR/.env"
  fi

  die ".env が見つかりません。"
}

ensure_uv() {
  UV_BIN="$(run_as_service_user 'command -v uv || true' | tr -d '\r')"
  if [ -n "$UV_BIN" ]; then
    log "uv: $UV_BIN"
    return
  fi

  log "uv をインストールします（ユーザー: $SERVICE_USER）。"
  run_as_service_user "curl -LsSf https://astral.sh/uv/install.sh | sh"

  UV_BIN="$(run_as_service_user 'command -v uv || true' | tr -d '\r')"
  [ -n "$UV_BIN" ] || die "uv のインストールに失敗しました。"
  log "uv installed: $UV_BIN"
}

sync_dependencies() {
  log "依存関係を同期します (uv sync --extra dev)。"
  run_as_service_user "cd '$APP_DIR' && '$UV_BIN' sync --extra dev"
}

run_migration() {
  log "マイグレーションを実行します。"
  run_as_service_user "cd '$APP_DIR' && '$APP_DIR/.venv/bin/alembic' -c '$APP_DIR/backend/alembic.ini' upgrade head"
}

validate_worker_by_tests() {
  if [ "${RUN_DEPLOY_TESTS:-0}" != "1" ]; then
    log "Worker検証の pytest -q はスキップします。必要なら RUN_DEPLOY_TESTS=1 を指定してください。"
    return
  fi

  log "Worker検証として pytest -q を実行します。"
  run_as_service_user "cd '$APP_DIR' && '$APP_DIR/.venv/bin/python' -m pytest -q"
}

write_systemd_units() {
  log "systemd ユニットを反映します。"
  sudo mkdir -p "$LOG_DIR"
  sudo chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"

  sudo tee "/etc/systemd/system/$UNIT_API.service" >/dev/null <<EOF
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
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port $FASTAPI_PORT
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/uvicorn.out
StandardError=append:$LOG_DIR/uvicorn.out

[Install]
WantedBy=multi-user.target
EOF

  sudo tee "/etc/systemd/system/$UNIT_WORKER.service" >/dev/null <<EOF
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
EOF
}

write_logrotate_config() {
  log "logrotate 設定を反映します。"
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
}

open_firewall_ports() {
  log "ファイアウォールでポートを開放します (FastAPI: ${FASTAPI_PORT}/tcp, SSH: ${SSH_PORT}/tcp)。"

  if command -v ufw >/dev/null 2>&1; then
    sudo ufw allow "${FASTAPI_PORT}/tcp"
    sudo ufw allow "${SSH_PORT}/tcp"
    log "ufw でポートを開放しました。"
    return
  fi

  if command -v firewall-cmd >/dev/null 2>&1; then
    if sudo firewall-cmd --state >/dev/null 2>&1; then
      sudo firewall-cmd --permanent --add-port="${FASTAPI_PORT}/tcp"
      sudo firewall-cmd --permanent --add-port="${SSH_PORT}/tcp"
      sudo firewall-cmd --reload
      log "firewalld でポートを開放しました。"
      return
    fi
    warn "firewalld が起動していないためポート開放をスキップします。"
    return
  fi

  warn "ufw/firewalld が見つからないためポート開放をスキップします。必要に応じて手動で ${FASTAPI_PORT}/tcp と ${SSH_PORT}/tcp を開放してください。"
}

start_services() {
  log "systemd をリロードしてサービスを有効化/起動します。"
  sudo systemctl daemon-reload
  sudo systemctl enable --now "$UNIT_API" "$UNIT_WORKER"
  sudo systemctl restart "$UNIT_API" "$UNIT_WORKER"
}

verify_api_health() {
  log "API ヘルスチェック: $API_HEALTH_URL"
  local i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 5 "$API_HEALTH_URL" >/dev/null 2>&1; then
      log "API ヘルスチェック成功。"
      return
    fi
    sleep 2
  done
  die "API ヘルスチェック失敗: $API_HEALTH_URL"
}

verify_service_active() {
  sudo systemctl is-active --quiet "$UNIT_API" || die "$UNIT_API が active ではありません。"
  sudo systemctl is-active --quiet "$UNIT_WORKER" || die "$UNIT_WORKER が active ではありません。"
  log "systemd サービス状態: $UNIT_API/$UNIT_WORKER は active"
}

show_summary() {
  cat <<EOF

[init] 完了
  SERVICE_USER : $SERVICE_USER
  SERVICE_GROUP: $SERVICE_GROUP
  APP_DIR      : $APP_DIR
  LOG_DIR      : $LOG_DIR
  FASTAPI_PORT : $FASTAPI_PORT
  SSH_PORT     : $SSH_PORT
  UNIT_API     : $UNIT_API
  UNIT_WORKER  : $UNIT_WORKER

ログ確認:
  sudo journalctl -u $UNIT_API -f
  sudo journalctl -u $UNIT_WORKER -f
  tail -f $LOG_DIR/uvicorn.out
  tail -f $LOG_DIR/worker.out
EOF
}

main() {
  resolve_paths
  check_prerequisites
  require_sudo_once
  ensure_env_file
  ensure_uv
  sync_dependencies
  run_migration
  validate_worker_by_tests
  write_systemd_units
  write_logrotate_config
  open_firewall_ports
  start_services
  verify_api_health
  verify_service_active
  show_summary
}

main "$@"
