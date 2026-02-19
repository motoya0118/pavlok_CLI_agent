"""Command API Handlers"""
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict
from collections.abc import Mapping

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Commitment,
    Configuration,
    ConfigAuditLog,
    ConfigValueType,
    ChangeSource,
)

MAX_COMMITMENT_ROWS = 10
DEFAULT_COACH_CHARACTOR = "うる星やつらのラムちゃん"
CONFIG_DEFINITIONS: dict[str, dict[str, Any]] = {
    "PAVLOK_TYPE_PUNISH": {
        "default": "zap",
        "value_type": ConfigValueType.STR,
        "allowed": {"zap", "vibe", "beep"},
    },
    "PAVLOK_VALUE_PUNISH": {"default": "35", "value_type": ConfigValueType.INT},
    "LIMIT_DAY_PAVLOK_COUNTS": {"default": "100", "value_type": ConfigValueType.INT},
    "LIMIT_PAVLOK_ZAP_VALUE": {"default": "100", "value_type": ConfigValueType.INT},
    "IGNORE_INTERVAL": {"default": "900", "value_type": ConfigValueType.INT},
    "IGNORE_JUDGE_TIME": {"default": "3", "value_type": ConfigValueType.INT},
    "IGNORE_MAX_RETRY": {"default": "5", "value_type": ConfigValueType.INT},
    "TIMEOUT_REMIND": {"default": "600", "value_type": ConfigValueType.INT},
    "TIMEOUT_REVIEW": {"default": "600", "value_type": ConfigValueType.INT},
    "RETRY_DELAY": {"default": "5", "value_type": ConfigValueType.INT},
    "COACH_CHARACTOR": {
        "default": DEFAULT_COACH_CHARACTOR,
        "value_type": ConfigValueType.STR,
    },
}

_SESSION_FACTORY = None
_SESSION_DB_URL = None


def _get_session():
    """Create DB session using current DATABASE_URL."""
    global _SESSION_FACTORY, _SESSION_DB_URL
    database_url = os.getenv("DATABASE_URL", "sqlite:///./oni.db")

    if _SESSION_FACTORY is None or _SESSION_DB_URL != database_url:
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        )
        _SESSION_FACTORY = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
        _SESSION_DB_URL = database_url

    return _SESSION_FACTORY()


def _load_existing_commitments(user_id: str) -> list[dict[str, str]]:
    """Load existing active commitments for modal prefill."""
    if not user_id:
        return []

    session = _get_session()
    try:
        rows = (
            session.query(Commitment)
            .filter(
                Commitment.user_id == user_id,
                Commitment.active.is_(True),
            )
            .order_by(Commitment.time.asc(), Commitment.created_at.asc())
            .limit(MAX_COMMITMENT_ROWS)
            .all()
        )
        return [{"task": row.task, "time": row.time} for row in rows]
    except Exception as exc:
        print(f"[{datetime.now()}] failed to load commitments for modal: {exc}")
        return []
    finally:
        session.close()


def _open_slack_modal(trigger_id: str, view: Dict[str, Any]) -> tuple[bool, str]:
    """
    Open a modal using Slack views.open API.
    Returns (ok, reason).
    """
    bot_token = os.getenv("SLACK_BOT_USER_OAUTH_TOKEN")
    if not bot_token:
        return False, "SLACK_BOT_USER_OAUTH_TOKEN is not configured"

    try:
        response = requests.post(
            "https://slack.com/api/views.open",
            headers={
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "trigger_id": trigger_id,
                "view": view,
            },
            timeout=2.5,
        )
    except requests.RequestException as exc:
        return False, f"views.open request failed: {exc}"

    try:
        payload = response.json()
    except ValueError:
        return False, f"views.open non-JSON response: status={response.status_code}"

    if not payload.get("ok"):
        error = payload.get("error", "views.open failed")
        details = payload.get("response_metadata", {}).get("messages", [])
        if details:
            return False, f"{error} ({'; '.join(details)})"
        return False, error

    return True, "ok"


def _parse_private_metadata(raw_metadata: str) -> dict[str, str]:
    """Parse Slack view private_metadata JSON safely."""
    if not raw_metadata:
        return {}
    try:
        parsed = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def _load_user_config_values(user_id: str) -> dict[str, str]:
    """Load config values for user with defaults."""
    values = {
        key: str(definition["default"])
        for key, definition in CONFIG_DEFINITIONS.items()
    }
    if not user_id:
        return values

    session = _get_session()
    try:
        rows = (
            session.query(Configuration)
            .filter(
                Configuration.user_id == user_id,
                Configuration.key.in_(list(CONFIG_DEFINITIONS.keys())),
            )
            .all()
        )
        for row in rows:
            values[row.key] = str(row.value)
    except Exception as exc:
        print(f"[{datetime.now()}] failed to load configs for modal: {exc}")
    finally:
        session.close()
    return values


def _extract_config_updates_from_view(
    state_values: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Extract config values from config_submit state and validate."""
    updates: dict[str, str] = {}
    errors: dict[str, str] = {}

    for key, definition in CONFIG_DEFINITIONS.items():
        block = state_values.get(key, {})
        if not isinstance(block, dict):
            continue

        raw_value = ""
        payload = next((v for v in block.values() if isinstance(v, dict)), {})
        if "selected_option" in payload:
            selected = payload.get("selected_option", {})
            if isinstance(selected, dict):
                raw_value = str(selected.get("value", "") or "")
        elif "value" in payload:
            raw_value = str(payload.get("value", "") or "").strip()

        if raw_value == "":
            continue

        allowed = definition.get("allowed")
        if isinstance(allowed, set) and raw_value not in allowed:
            errors[key] = "選択値が不正です。"
            continue

        if definition["value_type"] == ConfigValueType.INT:
            try:
                int(raw_value)
            except ValueError:
                errors[key] = "数値で入力してください。"
                continue

        if key == "COACH_CHARACTOR" and len(raw_value) > 100:
            errors[key] = "100文字以内で入力してください。"
            continue

        updates[key] = raw_value

    return updates, errors


def _save_user_configs(user_id: str, updates: dict[str, str]) -> int:
    """Upsert user configuration values and append audit logs."""
    if not user_id or not updates:
        return 0

    now = datetime.now()
    changed_count = 0
    session = _get_session()
    try:
        for key, new_value in updates.items():
            definition = CONFIG_DEFINITIONS.get(key)
            if not definition:
                continue

            row = (
                session.query(Configuration)
                .filter(
                    Configuration.user_id == user_id,
                    Configuration.key == key,
                )
                .first()
            )
            old_value = row.value if row else None
            if old_value == new_value:
                continue

            if row is None:
                row = Configuration(
                    user_id=user_id,
                    key=key,
                    value=new_value,
                    value_type=definition["value_type"],
                    default_value=str(definition["default"]),
                    version=1,
                    description=f"Configured via /config ({key})",
                )
                session.add(row)
            else:
                row.value = new_value
                row.value_type = definition["value_type"]
                row.version = (row.version or 0) + 1
                row.updated_at = now

            session.add(
                ConfigAuditLog(
                    config_key=key,
                    old_value=old_value,
                    new_value=new_value,
                    changed_by=user_id,
                    changed_at=now,
                    change_source=ChangeSource.SLACK_COMMAND,
                )
            )
            changed_count += 1

        session.commit()
        return changed_count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _set_system_paused(user_id: str, paused: bool) -> bool:
    """Upsert SYSTEM_PAUSED config and invalidate local cache."""
    paused_value = "true" if paused else "false"
    changed_by = user_id if user_id else "system"
    now = datetime.now()

    session = _get_session()
    try:
        row = (
            session.query(Configuration)
            .filter(Configuration.key == "SYSTEM_PAUSED")
            .first()
        )
        old_value = row.value if row else None

        if row is None:
            row = Configuration(
                user_id=changed_by,
                key="SYSTEM_PAUSED",
                value=paused_value,
                value_type=ConfigValueType.BOOL,
                default_value="false",
                version=1,
                description="Pause worker cycle execution",
            )
            session.add(row)
        else:
            row.value = paused_value
            row.value_type = ConfigValueType.BOOL
            row.default_value = "false"
            row.version = (row.version or 0) + 1
            row.updated_at = now

        session.add(
            ConfigAuditLog(
                config_key="SYSTEM_PAUSED",
                old_value=old_value,
                new_value=paused_value,
                changed_by=changed_by,
                changed_at=now,
                change_source=ChangeSource.SLACK_COMMAND,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # Invalidate local config cache in this process.
    try:
        from backend.worker.config_cache import invalidate_config_cache
        invalidate_config_cache("SYSTEM_PAUSED")
    except Exception:
        pass

    return old_value != paused_value


async def process_base_commit(request) -> Dict[str, Any]:
    """
    ベースコミットコマンド処理

    Args:
        request: FastAPIリクエスト

    Returns:
        Dict[str, Any]: 処理結果
    """
    from backend.slack_ui import base_commit_modal

    request_map = request if isinstance(request, Mapping) else {}
    user_id = request_map.get("user_id", "")
    channel_id = request_map.get("channel_id", "")
    response_url = request_map.get("response_url", "")
    trigger_id = request_map.get("trigger_id", "")

    if not isinstance(user_id, str):
        user_id = ""
    if not isinstance(channel_id, str):
        channel_id = ""
    if not isinstance(response_url, str):
        response_url = ""
    if not isinstance(trigger_id, str):
        trigger_id = ""

    existing_commitments: list[dict[str, str]] = []
    if user_id:
        existing_commitments = _load_existing_commitments(user_id)
    modal_data = base_commit_modal(existing_commitments)
    private_metadata: dict[str, str] = {}
    if channel_id:
        private_metadata["channel_id"] = channel_id
    if user_id:
        private_metadata["user_id"] = user_id
    if response_url:
        private_metadata["response_url"] = response_url
    if private_metadata:
        modal_data["private_metadata"] = json.dumps(private_metadata, ensure_ascii=False)

    if trigger_id:
        ok, reason = await asyncio.to_thread(_open_slack_modal, trigger_id, modal_data)
        if ok:
            print(f"[{datetime.now()}] views.open succeeded")
            # Slash command response must be a valid command response.
            return {
                "status": "success",
                "response_type": "ephemeral",
                "text": "コミットメント管理モーダルを開きました。",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "📋 コミットメント管理モーダルを開きました。",
                        },
                    }
                ],
            }
        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": f"モーダルを開けませんでした: {reason}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":warning: モーダルを開けませんでした: {reason}",
                    },
                }
            ],
        }
        
    print(f"[{datetime.now()}] views.open skipped: missing trigger_id")

    return {
        "status": "success",
        "response_type": "ephemeral",
        "text": "trigger_id が取得できないためモーダルを開けませんでした。再実行してください。",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":warning: trigger_id が取得できないためモーダルを開けませんでした。再実行してください。",
                },
            }
        ],
    }


async def process_plan(request) -> Dict[str, Any]:
    """
    plan編集コマンド処理

    Args:
        request: FastAPIリクエスト

    Returns:
        Dict[str, Any]: 処理結果
    """
    from backend.slack_ui import plan_input_modal

    request_map = request if isinstance(request, Mapping) else {}
    user_id = request_map.get("user_id", "")
    channel_id = request_map.get("channel_id", "")
    response_url = request_map.get("response_url", "")
    trigger_id = request_map.get("trigger_id", "")

    if not isinstance(user_id, str):
        user_id = ""
    if not isinstance(channel_id, str):
        channel_id = ""
    if not isinstance(response_url, str):
        response_url = ""
    if not isinstance(trigger_id, str):
        trigger_id = ""

    commitments: list[dict[str, str]] = []
    if user_id:
        commitments = _load_existing_commitments(user_id)

    modal_data = plan_input_modal(commitments)
    private_metadata: dict[str, str] = {}
    if channel_id:
        private_metadata["channel_id"] = channel_id
    if user_id:
        private_metadata["user_id"] = user_id
    if response_url:
        private_metadata["response_url"] = response_url
    if private_metadata:
        modal_data["private_metadata"] = json.dumps(private_metadata, ensure_ascii=False)

    if trigger_id:
        ok, reason = await asyncio.to_thread(_open_slack_modal, trigger_id, modal_data)
        if ok:
            print(f"[{datetime.now()}] plan views.open succeeded")
            return {
                "status": "success",
                "response_type": "ephemeral",
                "text": "今日の予定モーダルを開きました。",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "📅 今日の予定モーダルを開きました。",
                        },
                    }
                ],
            }

        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": f"モーダルを開けませんでした: {reason}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":warning: モーダルを開けませんでした: {reason}",
                    },
                }
            ],
        }

    print(f"[{datetime.now()}] plan views.open skipped: missing trigger_id")
    return {
        "status": "success",
        "response_type": "ephemeral",
        "text": "trigger_id が取得できないためモーダルを開けませんでした。再実行してください。",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":warning: trigger_id が取得できないためモーダルを開けませんでした。再実行してください。",
                },
            }
        ],
    }


async def process_stop(request) -> Dict[str, Any]:
    """
    停止コマンド処理

    Args:
        request: FastAPIリクエスト

    Returns:
        Dict[str, Any]: 処理結果
    """
    from backend.slack_ui import stop_notification

    request_map = request if isinstance(request, Mapping) else {}
    user_id = request_map.get("user_id", "")
    if not isinstance(user_id, str):
        user_id = ""

    changed = _set_system_paused(user_id=user_id, paused=True)
    print(
        f"[{datetime.now()}] process_stop applied SYSTEM_PAUSED=true "
        f"user_id={user_id or 'system'} changed={changed}"
    )

    blocks = stop_notification()
    return {
        "status": "success",
        "response_type": "ephemeral",
        "text": "鬼コーチを停止しました",
        "blocks": blocks,
    }


async def process_restart(request) -> Dict[str, Any]:
    """
    再開コマンド処理

    Args:
        request: FastAPIリクエスト

    Returns:
        Dict[str, Any]: 処理結果
    """
    from backend.slack_ui import restart_notification

    request_map = request if isinstance(request, Mapping) else {}
    user_id = request_map.get("user_id", "")
    if not isinstance(user_id, str):
        user_id = ""

    changed = _set_system_paused(user_id=user_id, paused=False)
    print(
        f"[{datetime.now()}] process_restart applied SYSTEM_PAUSED=false "
        f"user_id={user_id or 'system'} changed={changed}"
    )

    blocks = restart_notification()
    return {
        "status": "success",
        "response_type": "ephemeral",
        "text": "鬼コーチを再開しました",
        "blocks": blocks,
    }


async def process_config(request, config_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    設定コマンド処理

    Args:
        request: FastAPIリクエスト
        config_data: 設定データ

    Returns:
        Dict[str, Any]: 処理結果
    """
    request_map = request if isinstance(request, Mapping) else {}

    # Interactive config modal submit (view_submission).
    view = request_map.get("view") if isinstance(request_map, Mapping) else None
    if isinstance(view, Mapping) and view.get("callback_id") == "config_submit":
        payload_user = request_map.get("user", {})
        user_id = payload_user.get("id", "") if isinstance(payload_user, Mapping) else ""
        metadata = _parse_private_metadata(str(view.get("private_metadata", "") or ""))
        if not user_id:
            user_id = metadata.get("user_id", "")

        state = view.get("state", {})
        state_values = (
            state.get("values", {})
            if isinstance(state, Mapping)
            else {}
        )
        updates, errors = _extract_config_updates_from_view(
            state_values if isinstance(state_values, dict) else {}
        )
        if errors:
            return {
                "response_action": "errors",
                "errors": errors,
            }

        try:
            changed_count = _save_user_configs(user_id, updates)
        except Exception as exc:
            print(f"[{datetime.now()}] process_config save error: {exc}")
            return {
                "response_action": "errors",
                "errors": {
                    "COACH_CHARACTOR": "設定保存に失敗しました。再度お試しください。"
                },
            }

        print(
            f"[{datetime.now()}] config_submit saved: "
            f"user_id={user_id} changed={changed_count}"
        )
        return {
            "response_action": "clear",
        }

    # Slash command path: open /config modal via views.open.
    trigger_id = request_map.get("trigger_id", "")
    if not isinstance(trigger_id, str):
        trigger_id = ""
    if trigger_id:
        from backend.slack_ui import config_modal

        user_id = request_map.get("user_id", "")
        channel_id = request_map.get("channel_id", "")
        response_url = request_map.get("response_url", "")

        if not isinstance(user_id, str):
            user_id = ""
        if not isinstance(channel_id, str):
            channel_id = ""
        if not isinstance(response_url, str):
            response_url = ""

        current_values = _load_user_config_values(user_id)
        view_payload = config_modal(current_values)
        private_metadata: dict[str, str] = {}
        if user_id:
            private_metadata["user_id"] = user_id
        if channel_id:
            private_metadata["channel_id"] = channel_id
        if response_url:
            private_metadata["response_url"] = response_url
        if private_metadata:
            view_payload["private_metadata"] = json.dumps(
                private_metadata,
                ensure_ascii=False,
            )

        ok, reason = await asyncio.to_thread(_open_slack_modal, trigger_id, view_payload)
        if ok:
            return {
                "status": "success",
                "response_type": "ephemeral",
                "text": "設定モーダルを開きました。",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "⚙️ 設定モーダルを開きました。",
                        },
                    }
                ],
            }

        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": f"設定モーダルを開けませんでした: {reason}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":warning: 設定モーダルを開けませんでした: {reason}",
                    },
                }
            ],
        }

    # Backward-compatible path used in unit tests.
    method = getattr(request, "method", "GET")
    if method == "GET":
        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": "現在の設定を表示します。",
            "data": {"configurations": _load_user_config_values("")},
        }
    if method == "POST" and config_data:
        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": "設定を更新しました",
            "data": config_data,
        }
    return {
        "status": "success",
        "response_type": "ephemeral",
        "text": "設定処理完了",
    }
