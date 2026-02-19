"""Interactive API Handlers"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, Any

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Commitment,
    Schedule,
    ScheduleState,
    EventType,
    ActionLog,
    ActionResult,
    Punishment,
    PunishmentMode,
    Configuration,
)

MAX_COMMITMENT_ROWS = 10
MIN_COMMITMENT_ROWS = 3

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


def _extract_submission_metadata(payload_data: Dict[str, Any]) -> dict[str, str]:
    """
    Extract context passed from slash command -> modal -> submission.
    We use private_metadata to keep channel_id for post-submit notifications.
    """
    view = payload_data.get("view", {})
    metadata_raw = view.get("private_metadata", "")
    metadata: dict[str, str] = {}

    if metadata_raw:
        try:
            parsed = json.loads(metadata_raw)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            for key in ("channel_id", "user_id", "response_url", "schedule_id"):
                value = parsed.get(key)
                if isinstance(value, str) and value:
                    metadata[key] = value

    user_id = payload_data.get("user", {}).get("id")
    if isinstance(user_id, str) and user_id:
        metadata.setdefault("user_id", user_id)

    return metadata


def _build_commitment_summary_message(
    user_id: str, commitments: list[dict[str, str]]
) -> tuple[str, list[dict[str, Any]]]:
    """Build summary text/blocks sent after successful modal submit."""
    mention = f"<@{user_id}>"
    if commitments:
        summary_lines = [
            f"{idx}. `{row['time'][:5]}` {row['task']}"
            for idx, row in enumerate(commitments, start=1)
        ]
        summary = "\n".join(summary_lines)
        text = (
            f"{mention} コミットメント登録完了\n"
            f"今の登録は {len(commitments)} 件です。"
        )
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"✅ *コミットメント登録完了*\n"
                        f"{mention} 今の登録は *{len(commitments)}件* です。"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*現在の登録*\n{summary}",
                },
            },
        ]
        return text, blocks

    text = f"{mention} コミットメントをすべて解除しました。"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"✅ *コミットメント登録完了*\n{mention} 登録は現在 *0件* です。",
            },
        }
    ]
    return text, blocks


async def _notify_commitment_saved(
    channel_id: str,
    user_id: str,
    commitments: list[dict[str, str]],
    response_url: str = "",
) -> None:
    """Post a summary message to Slack after commitment submit succeeds."""
    bot_token = os.getenv("SLACK_BOT_USER_OAUTH_TOKEN")
    if not bot_token:
        print(
            f"[{datetime.now()}] skip post-submit notification: "
            "SLACK_BOT_USER_OAUTH_TOKEN is not configured"
        )
        return

    def _post() -> tuple[bool, str]:
        text, blocks = _build_commitment_summary_message(user_id, commitments)

        # Prefer response_url: no extra scopes required and works for slash-command context.
        if response_url:
            try:
                response = requests.post(
                    response_url,
                    json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": text,
                        "blocks": blocks,
                    },
                    timeout=2.5,
                )
            except requests.RequestException as exc:
                return False, f"response_url post failed: {exc}"

            if 200 <= response.status_code < 300:
                return True, "ok(response_url)"
            return False, f"response_url post status={response.status_code}"

        headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        def _open_dm_channel() -> tuple[str, str]:
            try:
                open_resp = requests.post(
                    "https://slack.com/api/conversations.open",
                    headers=headers,
                    json={"users": user_id},
                    timeout=2.5,
                )
                open_body = open_resp.json()
            except (requests.RequestException, ValueError) as exc:
                return "", f"conversations.open failed: {exc}"

            if not open_body.get("ok"):
                return "", f"conversations.open error: {open_body.get('error')}"

            dm_channel = open_body.get("channel", {}).get("id", "")
            if not dm_channel:
                return "", "conversations.open returned no channel id"
            return dm_channel, "ok"

        def _post_message(target_channel: str) -> tuple[bool, str]:
            try:
                post_resp = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json={
                        "channel": target_channel,
                        "text": text,
                        "blocks": blocks,
                        "unfurl_links": False,
                        "unfurl_media": False,
                    },
                    timeout=2.5,
                )
                post_body = post_resp.json()
            except (requests.RequestException, ValueError) as exc:
                return False, f"chat.postMessage failed: {exc}"

            if not post_body.get("ok"):
                return False, f"chat.postMessage error: {post_body.get('error')}"
            return True, "ok"

        target_channel = channel_id
        if target_channel:
            ok, reason = _post_message(target_channel)
            if ok:
                return True, "ok"
            if "not_in_channel" not in reason and "channel_not_found" not in reason:
                return False, reason

        dm_channel, dm_reason = _open_dm_channel()
        if not dm_channel:
            return False, dm_reason
        return _post_message(dm_channel)

    ok, reason = await asyncio.to_thread(_post)
    if ok:
        print(
            f"[{datetime.now()}] post-submit notification sent: "
            f"user_id={user_id} channel={channel_id or '(dm)'} count={len(commitments)}"
        )
    else:
        print(f"[{datetime.now()}] post-submit notification failed: {reason}")


def _to_relative_day_label(date_value: str) -> str:
    """Convert relative date token to Japanese display label."""
    if date_value == "tomorrow":
        return "明日"
    return "今日"


async def _notify_plan_saved(
    channel_id: str,
    user_id: str,
    scheduled_tasks: list[dict[str, str]],
    next_plan: dict[str, str],
    thread_ts: str = "",
) -> None:
    """Post plan submit completion message to Slack."""
    bot_token = os.getenv("SLACK_BOT_USER_OAUTH_TOKEN")
    if not bot_token:
        print(
            f"[{datetime.now()}] skip plan-submit notification: "
            "SLACK_BOT_USER_OAUTH_TOKEN is not configured"
        )
        return

    from backend.slack_ui import plan_complete_notification

    visible_tasks = scheduled_tasks
    if not visible_tasks:
        visible_tasks = [
            {"task": "実行タスクなし", "date": "今日", "time": "--:--"}
        ]

    text = f"<@{user_id}> 24時間のplanを登録しました。"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text,
            },
        },
        *plan_complete_notification(visible_tasks, next_plan),
    ]
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    def _post() -> tuple[bool, str]:
        def _call_chat_update(target_channel: str, message_ts: str) -> tuple[bool, str]:
            try:
                update_resp = requests.post(
                    "https://slack.com/api/chat.update",
                    headers=headers,
                    json={
                        "channel": target_channel,
                        "ts": message_ts,
                        "text": text,
                        "blocks": blocks,
                        "link_names": True,
                    },
                    timeout=2.5,
                )
                update_body = update_resp.json()
            except (requests.RequestException, ValueError) as exc:
                return False, f"chat.update failed: {exc}"

            if not update_body.get("ok"):
                return False, f"chat.update error: {update_body.get('error')}"
            return True, "ok"

        def _open_dm_channel() -> tuple[str, str]:
            try:
                open_resp = requests.post(
                    "https://slack.com/api/conversations.open",
                    headers=headers,
                    json={"users": user_id},
                    timeout=2.5,
                )
                open_body = open_resp.json()
            except (requests.RequestException, ValueError) as exc:
                return "", f"conversations.open failed: {exc}"

            if not open_body.get("ok"):
                return "", f"conversations.open error: {open_body.get('error')}"

            dm_channel = open_body.get("channel", {}).get("id", "")
            if not dm_channel:
                return "", "conversations.open returned no channel id"
            return dm_channel, "ok"

        def _post_message(target_channel: str, post_thread_ts: str = "") -> tuple[bool, str]:
            payload: Dict[str, Any] = {
                "channel": target_channel,
                "text": text,
                "blocks": blocks,
                "link_names": True,
                "unfurl_links": False,
                "unfurl_media": False,
            }
            if post_thread_ts:
                payload["thread_ts"] = post_thread_ts

            try:
                post_resp = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json=payload,
                    timeout=2.5,
                )
                post_body = post_resp.json()
            except (requests.RequestException, ValueError) as exc:
                return False, f"chat.postMessage failed: {exc}"

            if not post_body.get("ok"):
                return False, f"chat.postMessage error: {post_body.get('error')}"
            return True, "ok"

        if channel_id and thread_ts:
            ok, reason = _call_chat_update(channel_id, thread_ts)
            if ok:
                return True, "ok(update)"
            if "message_not_found" not in reason and "cant_update_message" not in reason:
                return False, reason

        target_channel = channel_id
        if target_channel:
            ok, reason = _post_message(target_channel, thread_ts)
            if ok:
                return True, "ok"
            if "not_in_channel" not in reason and "channel_not_found" not in reason:
                return False, reason

        dm_channel, dm_reason = _open_dm_channel()
        if not dm_channel:
            return False, dm_reason
        return _post_message(dm_channel)

    ok, reason = await asyncio.to_thread(_post)
    if ok:
        print(
            f"[{datetime.now()}] plan-submit notification sent: "
            f"user_id={user_id} channel={channel_id or '(dm)'} tasks={len(scheduled_tasks)}"
        )
        await _send_notification_stimulus(
            user_id=user_id,
            source="plan-submit",
            reason="plan: 今日のプランを登録してください",
        )
    else:
        print(f"[{datetime.now()}] plan-submit notification failed: {reason}")


async def _send_notification_stimulus(
    user_id: str,
    source: str,
    reason: str = "",
) -> None:
    """Send per-user Pavlok stimulus for Slack notification events."""
    if not user_id:
        return

    def _send() -> dict[str, Any]:
        from backend.pavlok_lib import stimulate_notification_for_user

        result = stimulate_notification_for_user(user_id=user_id, reason=reason)
        return result if isinstance(result, dict) else {"success": False, "error": str(result)}

    result = await asyncio.to_thread(_send)
    if result.get("success"):
        print(
            f"[{datetime.now()}] notification-stimulus sent: "
            f"user_id={user_id} source={source} "
            f"type={result.get('type')} value={result.get('value')} "
            f"reason={result.get('reason') or reason}"
        )
    else:
        print(
            f"[{datetime.now()}] notification-stimulus failed: "
            f"user_id={user_id} source={source} detail={result}"
        )


async def _run_agent_call(schedule_ids: list[str]) -> None:
    """Run scripts/agent_call.py to fill schedule comments."""
    if not schedule_ids:
        return

    def _run() -> tuple[bool, str]:
        repo_root = Path(__file__).resolve().parents[2]
        script_path = repo_root / "scripts" / "agent_call.py"
        if not script_path.is_file():
            return False, f"agent_call script not found: {script_path}"

        env = os.environ.copy()
        env["SCHEDULE_IDS_JSON"] = json.dumps(schedule_ids, ensure_ascii=False)
        result = subprocess.run(
            [sys.executable, str(script_path)],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"exit={result.returncode}"
            return False, detail
        return True, (result.stdout or "ok").strip()

    ok, reason = await asyncio.to_thread(_run)
    if ok:
        print(
            f"[{datetime.now()}] agent_call succeeded: "
            f"schedule_count={len(schedule_ids)} detail={reason}"
        )
    else:
        print(f"[{datetime.now()}] agent_call failed: {reason}")


def _current_commitments_from_view(view: Dict[str, Any]) -> list[dict[str, str]]:
    """Extract current modal input values from Slack view payload."""
    blocks = view.get("blocks", [])
    state_values = view.get("state", {}).get("values", {})

    row_count = sum(
        1
        for block in blocks
        if str(block.get("block_id", "")).startswith("commitment_")
    )
    row_count = max(3, row_count)

    commitments: list[dict[str, str]] = []
    for idx in range(1, row_count + 1):
        task = ""
        selected_time = ""

        task_block = state_values.get(f"commitment_{idx}", {})
        task_input = task_block.get(f"task_{idx}", {})
        if isinstance(task_input, dict):
            task = task_input.get("value", "") or ""

        time_block = state_values.get(f"time_{idx}", {})
        time_input = time_block.get(f"time_{idx}", {})
        if isinstance(time_input, dict):
            selected_time = time_input.get("selected_time", "") or ""

        commitments.append({"task": task, "time": selected_time})

    return commitments


async def process_commitment_add_row(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle "+ 追加" in base_commit modal.
    For block_actions in modals, we update the view via views.update API.
    If view_id/token is unavailable, fall back to response_action=update.
    """
    from backend.slack_ui import base_commit_modal

    view = payload_data.get("view", {})
    commitments = _current_commitments_from_view(view)
    if len(commitments) < MAX_COMMITMENT_ROWS:
        commitments.append({"task": "", "time": ""})

    updated_view = base_commit_modal(commitments)
    return await _apply_modal_update(view, updated_view, "commitment_add_row")


async def process_commitment_remove_row(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle "- 削除" in base_commit modal.
    Removes the last commitment row while keeping at least MIN_COMMITMENT_ROWS.
    """
    from backend.slack_ui import base_commit_modal

    view = payload_data.get("view", {})
    commitments = _current_commitments_from_view(view)
    if len(commitments) > MIN_COMMITMENT_ROWS:
        commitments = commitments[:-1]

    updated_view = base_commit_modal(commitments)
    return await _apply_modal_update(view, updated_view, "commitment_remove_row")


def _load_active_commitments_for_user(user_id: str) -> list[dict[str, str]]:
    """Load active commitments for a user, sorted by time."""
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
        return [{"id": str(row.id), "task": row.task, "time": row.time} for row in rows]
    finally:
        session.close()


def _resolve_commitment_task_name_for_schedule(session, schedule) -> str:
    """Resolve task name from commitment_id linked to schedule."""
    commitment_id = getattr(schedule, "commitment_id", None)
    if not commitment_id:
        fallback = str(getattr(schedule, "comment", "") or "").strip()
        return fallback or "タスク"

    row = (
        session.query(Commitment.task)
        .filter(
            Commitment.id == str(commitment_id),
        )
        .first()
    )
    if row and row[0]:
        return str(row[0])
    fallback = str(getattr(schedule, "comment", "") or "").strip()
    return fallback or "タスク"


def _extract_schedule_id_from_action(payload_data: Dict[str, Any]) -> str:
    """Extract schedule_id from block action value JSON."""
    actions = payload_data.get("actions", [])
    if not actions:
        return ""

    value = actions[0].get("value", "")
    if not value:
        return ""
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ""
    if isinstance(parsed, dict):
        raw = parsed.get("schedule_id")
        if isinstance(raw, str):
            return raw
    return ""


def _open_slack_modal(trigger_id: str, view: Dict[str, Any]) -> tuple[bool, str]:
    """Open a modal using Slack views.open API."""
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


async def process_plan_open_modal(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle plan_open_modal button and open plan input modal via views.open.
    """
    from backend.slack_ui import plan_input_modal

    trigger_id = payload_data.get("trigger_id", "")
    user_id = payload_data.get("user", {}).get("id", "")
    channel_id = payload_data.get("container", {}).get("channel_id", "")
    schedule_id = _extract_schedule_id_from_action(payload_data)

    if not trigger_id:
        print(f"[{datetime.now()}] plan_open_modal failed: missing trigger_id")
        # Ack the action to avoid Slack client error; modal cannot be opened without trigger_id.
        return {"status": "success"}

    commitments = _load_active_commitments_for_user(user_id)
    modal_view = plan_input_modal(commitments)
    metadata = {
        "user_id": user_id,
        "channel_id": channel_id,
    }
    if schedule_id:
        metadata["schedule_id"] = schedule_id
    modal_view["private_metadata"] = json.dumps(metadata, ensure_ascii=False)

    ok, reason = await asyncio.to_thread(_open_slack_modal, trigger_id, modal_view)
    if not ok:
        print(f"[{datetime.now()}] plan_open_modal views.open failed: {reason}")
    else:
        print(
            f"[{datetime.now()}] plan_open_modal views.open succeeded: "
            f"user_id={user_id} schedule_id={schedule_id}"
        )

    # Ack block_actions regardless; modal opening is handled via Web API.
    return {"status": "success"}


async def _apply_modal_update(
    view: Dict[str, Any], updated_view: Dict[str, Any], action_name: str
) -> Dict[str, Any]:
    """Update modal via views.update, or fallback to response_action update."""

    # Keep metadata flags that may be set by previous view state.
    for key in ("private_metadata", "clear_on_close", "notify_on_close", "external_id"):
        if key in view:
            updated_view[key] = view[key]

    view_id = view.get("id")
    view_hash = view.get("hash")
    bot_token = os.getenv("SLACK_BOT_USER_OAUTH_TOKEN")

    # Best-effort fallback for local tests or environments without view_id/token.
    if not view_id or not bot_token:
        if not view_id:
            print(f"[{datetime.now()}] {action_name} fallback: missing view_id")
        if not bot_token:
            print(
                f"[{datetime.now()}] {action_name} fallback: "
                "SLACK_BOT_USER_OAUTH_TOKEN is not configured"
            )
        return {
            "response_action": "update",
            "view": updated_view,
        }

    def _call_views_update() -> tuple[bool, str]:
        payload: Dict[str, Any] = {
            "view_id": view_id,
            "view": updated_view,
        }
        if view_hash:
            payload["hash"] = view_hash

        try:
            response = requests.post(
                "https://slack.com/api/views.update",
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
                timeout=2.5,
            )
        except requests.RequestException as exc:
            return False, f"views.update request failed: {exc}"

        try:
            body = response.json()
        except ValueError:
            return False, f"views.update non-JSON response: status={response.status_code}"

        if not body.get("ok"):
            error = body.get("error", "views.update failed")
            details = body.get("response_metadata", {}).get("messages", [])
            if details:
                return False, f"{error} ({'; '.join(details)})"
            return False, error
        return True, "ok"

    ok, reason = await asyncio.to_thread(_call_views_update)
    if not ok:
        print(f"[{datetime.now()}] {action_name} views.update failed: {reason}")
        # Try a fallback response for resilience, though Slack may ignore this path for block_actions.
        return {
            "response_action": "update",
            "view": updated_view,
        }

    print(f"[{datetime.now()}] {action_name} views.update succeeded")
    # Acknowledge block_actions. Modal update has already been done via Web API.
    return {
        "status": "success",
    }


async def process_plan_submit(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    プラン登録処理（インタラクティブ）

    Args:
        payload_data: Slackペイロードデータ

    Returns:
        Dict[str, Any]: 処理結果
    """
    user_id = payload_data.get("user", {}).get("id", "")
    view = payload_data.get("view", {})
    state_values = view.get("state", {}).get("values", {})

    if not user_id:
        return {
            "response_action": "errors",
            "errors": {"commitment_1": "ユーザー情報を取得できませんでした。"},
        }

    commitments = _extract_commitments_from_submission(state_values)
    validation_errors: Dict[str, str] = {}
    normalized_rows: list[dict[str, str]] = []

    for row in commitments:
        idx = row["index"]
        task = row["task"].strip()
        selected_time = _normalize_time(row["time"])

        if not task and not selected_time:
            continue
        if task and not selected_time:
            validation_errors[f"time_{idx}"] = "時刻を選択してください。"
            continue
        if selected_time and not task:
            validation_errors[f"commitment_{idx}"] = "タスク名を入力してください。"
            continue

        normalized_rows.append(
            {
                "task": task,
                "time": selected_time,
            }
        )

    if validation_errors:
        return {
            "response_action": "errors",
            "errors": validation_errors,
        }

    session = _get_session()
    try:
        session.query(Commitment).filter(Commitment.user_id == user_id).delete(
            synchronize_session=False
        )
        for row in normalized_rows:
            session.add(
                Commitment(
                    user_id=user_id,
                    task=row["task"],
                    time=row["time"],
                    active=True,
                )
            )
        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"[{datetime.now()}] process_plan_submit DB error: {exc}")
        return {
            "response_action": "errors",
            "errors": {
                "commitment_1": "保存に失敗しました。もう一度試してください。"
            },
        }
    finally:
        session.close()

    print(
        f"[{datetime.now()}] process_plan_submit saved commitments: "
        f"user_id={user_id} count={len(normalized_rows)} db={_SESSION_DB_URL}"
    )

    # Notify user in channel (or DM fallback) without delaying modal close response.
    metadata = _extract_submission_metadata(payload_data)
    channel_id = metadata.get("channel_id", "")
    response_url = metadata.get("response_url", "")
    asyncio.create_task(
        _notify_commitment_saved(
            channel_id=channel_id,
            user_id=user_id,
            commitments=normalized_rows,
            response_url=response_url,
        )
    )

    # Slack view_submission success response must be a modal response payload.
    # Keep it minimal to avoid "invalid_command_response"/modal close failures.
    return {
        "response_action": "clear",
    }


def _extract_plan_task_indices(state_values: Dict[str, Any]) -> list[int]:
    """Extract task indices from plan modal state keys like task_1_date."""
    indices: set[int] = set()
    for block_id in state_values.keys():
        parts = str(block_id).split("_")
        if len(parts) < 3:
            continue
        if parts[0] != "task":
            continue
        if not parts[1].isdigit():
            continue
        if parts[2] not in {"date", "time", "skip"}:
            continue
        indices.add(int(parts[1]))
    return sorted(indices)


def _extract_static_select_value(
    state_values: Dict[str, Any],
    block_id: str,
    action_id: str,
) -> str:
    """Read selected_option.value from a static_select input."""
    payload = state_values.get(block_id, {}).get(action_id, {})
    if not isinstance(payload, dict):
        return ""
    option = payload.get("selected_option", {})
    if not isinstance(option, dict):
        return ""
    value = option.get("value", "")
    return value if isinstance(value, str) else ""


def _extract_timepicker_value(
    state_values: Dict[str, Any],
    block_id: str,
    action_id: str,
) -> str:
    """Read selected_time from a timepicker input."""
    payload = state_values.get(block_id, {}).get(action_id, {})
    if not isinstance(payload, dict):
        return ""
    selected_time = payload.get("selected_time", "")
    return selected_time if isinstance(selected_time, str) else ""


def _extract_skip_flag(
    state_values: Dict[str, Any],
    block_id: str,
    action_id: str,
) -> bool:
    """Read skip checkbox state."""
    payload = state_values.get(block_id, {}).get(action_id, {})
    if not isinstance(payload, dict):
        return False
    options = payload.get("selected_options", [])
    if not isinstance(options, list):
        return False
    for option in options:
        if isinstance(option, dict) and option.get("value") == "skip":
            return True
    return False


def _resolve_relative_datetime(date_value: str, normalized_time: str) -> datetime:
    """Convert today/tomorrow + HH:MM:SS to absolute datetime."""
    now = datetime.now()
    base_date = now.date()
    if date_value == "tomorrow":
        base_date = base_date + timedelta(days=1)

    hh, mm, ss = normalized_time.split(":")
    return datetime.combine(
        base_date,
        dt_time(hour=int(hh), minute=int(mm), second=int(ss)),
    )


def _parse_plan_submission_state(state_values: Dict[str, Any]) -> tuple[
    list[dict[str, Any]],
    dict[str, str],
    Dict[str, str],
]:
    """
    Parse plan modal submission payload.
    Returns:
    - task rows [{index, date, time, skip}]
    - next_plan {date, time}
    - validation errors keyed by block_id
    """
    errors: Dict[str, str] = {}
    task_rows: list[dict[str, Any]] = []

    for idx in _extract_plan_task_indices(state_values):
        date_value = _extract_static_select_value(
            state_values, f"task_{idx}_date", "date"
        )
        time_value = _extract_timepicker_value(
            state_values, f"task_{idx}_time", "time"
        )
        skip = _extract_skip_flag(state_values, f"task_{idx}_skip", "skip")
        normalized_time = _normalize_time(time_value)

        if date_value not in {"today", "tomorrow"}:
            errors[f"task_{idx}_date"] = "実行日を選択してください。"
        if not normalized_time:
            errors[f"task_{idx}_time"] = "実行時間を選択してください。"

        task_rows.append(
            {
                "index": idx,
                "date": date_value,
                "time": normalized_time,
                "skip": skip,
            }
        )

    next_plan_date = _extract_static_select_value(
        state_values,
        "next_plan_date",
        "date",
    )
    next_plan_time = _normalize_time(
        _extract_timepicker_value(state_values, "next_plan_time", "time")
    )

    if next_plan_date not in {"today", "tomorrow"}:
        errors["next_plan_date"] = "次回計画の実行日を選択してください。"
    if not next_plan_time:
        errors["next_plan_time"] = "次回計画の実行時間を選択してください。"

    return task_rows, {"date": next_plan_date, "time": next_plan_time}, errors


async def process_plan_modal_submit(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle plan modal (callback_id=plan_submit):
    - mark opened plan schedule done
    - register remind schedules for selected tasks (non-skip)
    - register next plan schedule
    """
    user_id = payload_data.get("user", {}).get("id", "")
    view = payload_data.get("view", {})
    state_values = view.get("state", {}).get("values", {})

    if not user_id:
        return {
            "response_action": "errors",
            "errors": {"next_plan_date": "ユーザー情報を取得できませんでした。"},
        }

    task_rows, next_plan, validation_errors = _parse_plan_submission_state(state_values)
    if validation_errors:
        return {
            "response_action": "errors",
            "errors": validation_errors,
        }

    active_commitments = _load_active_commitments_for_user(user_id)

    remind_rows_to_save: list[dict[str, Any]] = []
    skipped_task_names: list[str] = []
    scheduled_tasks_for_message: list[dict[str, str]] = []
    mapping_errors: Dict[str, str] = {}
    for row in task_rows:
        commitment_idx = row["index"] - 1
        if commitment_idx < 0 or commitment_idx >= len(active_commitments):
            mapping_errors[f"task_{row['index']}_time"] = (
                "コミットメント情報の整合性が取れませんでした。"
                "/base_commit から再設定してください。"
            )
            continue

        mapped_commitment = active_commitments[commitment_idx]
        commitment_id = str(mapped_commitment.get("id", "")).strip()
        task_name = mapped_commitment.get("task", "").strip() or f"タスク{row['index']}"
        if not commitment_id:
            mapping_errors[f"task_{row['index']}_time"] = (
                "コミットメントIDを解決できませんでした。"
                "/base_commit から再設定してください。"
            )
            continue

        if row["skip"]:
            skipped_task_names.append(task_name)
            continue

        run_at = _resolve_relative_datetime(row["date"], row["time"])
        remind_rows_to_save.append(
            {
                "run_at": run_at,
                "task": task_name,
                "commitment_id": commitment_id,
            }
        )

        scheduled_tasks_for_message.append(
            {
                "task": task_name,
                "date": _to_relative_day_label(row["date"]),
                "time": row["time"][:5],
            }
        )

    if mapping_errors:
        return {
            "response_action": "errors",
            "errors": mapping_errors,
        }

    metadata = _extract_submission_metadata(payload_data)
    schedule_id = metadata.get("schedule_id", "")
    channel_id = metadata.get("channel_id", "")
    next_plan_for_message = {
        "date": _to_relative_day_label(next_plan["date"]),
        "time": next_plan["time"][:5],
    }
    now = datetime.now()
    thread_ts = ""
    inflight_canceled = 0
    inserted_remind_schedule_ids: list[str] = []
    opened_plan_schedule_id = ""

    session = _get_session()
    try:
        if schedule_id:
            opened_plan_schedule = (
                session.query(Schedule)
                .filter(
                    Schedule.id == schedule_id,
                    Schedule.user_id == user_id,
                    Schedule.event_type == EventType.PLAN,
                )
                .first()
            )
            if opened_plan_schedule:
                thread_ts = opened_plan_schedule.thread_ts or ""
                opened_plan_schedule.state = ScheduleState.DONE
                opened_plan_schedule.updated_at = now
                opened_plan_schedule_id = str(opened_plan_schedule.id)

        # Wash phase: mark all inflight schedules for this user as canceled.
        # Keep ordering: opened schedule is marked DONE first.
        inflight_canceled = (
            session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.state.in_([ScheduleState.PENDING, ScheduleState.PROCESSING]),
            )
            .update(
                {
                    Schedule.state: ScheduleState.CANCELED,
                    Schedule.updated_at: now,
                },
                synchronize_session=False,
            )
        )

        # INSERT phase: reminders.
        inserted_remind_schedules: list[Schedule] = []
        for reminder in remind_rows_to_save:
            remind_schedule = Schedule(
                user_id=user_id,
                event_type=EventType.REMIND,
                commitment_id=reminder["commitment_id"],
                run_at=reminder["run_at"],
                state=ScheduleState.PENDING,
                retry_count=0,
                comment=reminder["task"],
            )
            session.add(remind_schedule)
            inserted_remind_schedules.append(remind_schedule)

        # Ensure UUIDs are materialized before forwarding IDs to agent_call.
        session.flush()
        inserted_remind_schedule_ids = [
            str(s.id) for s in inserted_remind_schedules if getattr(s, "id", None)
        ]

        # INSERT phase: next plan.
        next_plan_run_at = _resolve_relative_datetime(
            next_plan["date"],
            next_plan["time"],
        )
        session.add(
            Schedule(
                user_id=user_id,
                event_type=EventType.PLAN,
                run_at=next_plan_run_at,
                state=ScheduleState.PENDING,
                retry_count=0,
                comment="next plan",
            )
        )

        # Record explicit "skip" decisions in action_logs.
        if opened_plan_schedule_id:
            for _task_name in skipped_task_names:
                session.add(
                    ActionLog(
                        schedule_id=opened_plan_schedule_id,
                        result=ActionResult.NO,
                    )
                )

        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"[{datetime.now()}] process_plan_modal_submit DB error: {exc}")
        return {
            "response_action": "errors",
            "errors": {
                "next_plan_time": "保存に失敗しました。もう一度試してください。"
            },
        }
    finally:
        session.close()

    print(
        f"[{datetime.now()}] process_plan_modal_submit saved schedules: "
        f"inflight_canceled={inflight_canceled} "
        f"user_id={user_id} remind_count={len(remind_rows_to_save)} "
        f"next_plan={next_plan['date']} {next_plan['time']} "
        f"db={_SESSION_DB_URL}"
    )

    # Notify user in channel/thread without delaying modal close response.
    asyncio.create_task(
        _notify_plan_saved(
            channel_id=channel_id,
            user_id=user_id,
            scheduled_tasks=scheduled_tasks_for_message,
            next_plan=next_plan_for_message,
            thread_ts=thread_ts,
        )
    )
    asyncio.create_task(_run_agent_call(inserted_remind_schedule_ids))

    return {
        "response_action": "clear",
    }


def _extract_commitments_from_submission(state_values: Dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract commitment rows from Slack view_submission state.
    Supports:
    - Current structure: commitment_N/task_N + time_N/time_N
    - Legacy test structure: task_N with {task, time}
    """
    indices: set[int] = set()
    for block_id in state_values.keys():
        for prefix in ("commitment_", "time_", "task_"):
            if block_id.startswith(prefix):
                suffix = block_id[len(prefix):]
                if suffix.isdigit():
                    indices.add(int(suffix))

    if not indices:
        return []

    rows: list[dict[str, Any]] = []
    for idx in sorted(indices):
        task = ""
        selected_time = ""

        # Current modal shape.
        task_payload = state_values.get(f"commitment_{idx}", {}).get(f"task_{idx}", {})
        if isinstance(task_payload, dict):
            task = task_payload.get("value", "") or ""

        time_payload = state_values.get(f"time_{idx}", {}).get(f"time_{idx}", {})
        if isinstance(time_payload, dict):
            selected_time = time_payload.get("selected_time", "") or ""

        # Legacy/test shape fallback.
        legacy_task_block = state_values.get(f"task_{idx}", {})
        if isinstance(legacy_task_block, dict):
            if not task:
                task = legacy_task_block.get("task", "") or ""
            if not selected_time:
                selected_time = legacy_task_block.get("time", "") or ""

        rows.append(
            {
                "index": idx,
                "task": task,
                "time": selected_time,
            }
        )

    return rows


def _normalize_time(raw_time: str) -> str:
    """Normalize Slack timepicker value to HH:MM:SS."""
    value = (raw_time or "").strip()
    if not value:
        return ""
    if len(value) == 5 and ":" in value:
        hh, mm = value.split(":", 1)
        if hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
            return f"{hh.zfill(2)}:{mm.zfill(2)}:00"
        return ""
    if len(value) == 8 and value.count(":") == 2:
        hh, mm, ss = value.split(":")
        if (
            hh.isdigit() and mm.isdigit() and ss.isdigit()
            and 0 <= int(hh) <= 23
            and 0 <= int(mm) <= 59
            and 0 <= int(ss) <= 59
        ):
            return f"{hh.zfill(2)}:{mm.zfill(2)}:{ss.zfill(2)}"
    return ""


def _extract_schedule_id_from_action(payload_data: Dict[str, Any]) -> str:
    """Extract schedule_id from block action payload value JSON."""
    actions = payload_data.get("actions", [])
    if not isinstance(actions, list) or not actions:
        return ""
    first_action = actions[0]
    if not isinstance(first_action, dict):
        return ""

    raw_value = first_action.get("value", "")
    if not isinstance(raw_value, str) or not raw_value:
        return ""

    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        # Backward-compatible fallback: treat value itself as schedule_id.
        return raw_value.strip()

    if not isinstance(parsed, dict):
        return ""
    schedule_id = parsed.get("schedule_id", "")
    return schedule_id if isinstance(schedule_id, str) else ""


def _extract_action_channel_id(payload_data: Dict[str, Any]) -> str:
    """Extract channel_id from interactive payload."""
    container = payload_data.get("container", {})
    if isinstance(container, dict):
        channel_id = container.get("channel_id", "")
        if isinstance(channel_id, str) and channel_id:
            return channel_id

    channel = payload_data.get("channel", {})
    if isinstance(channel, dict):
        channel_id = channel.get("id", "")
        if isinstance(channel_id, str):
            return channel_id
    return ""


def _extract_action_thread_ts(payload_data: Dict[str, Any]) -> str:
    """Extract thread timestamp from interactive payload."""
    container = payload_data.get("container", {})
    if isinstance(container, dict):
        for key in ("thread_ts", "message_ts"):
            value = container.get(key, "")
            if isinstance(value, str) and value:
                return value

    message = payload_data.get("message", {})
    if isinstance(message, dict):
        for key in ("thread_ts", "ts"):
            value = message.get(key, "")
            if isinstance(value, str) and value:
                return value
    return ""


def _calc_no_streak_count(session, user_id: str) -> int:
    """
    Count consecutive NO responses for remind events.
    Traverses action_logs from newest and stops at the latest YES.
    """
    rows = (
        session.query(ActionLog.result)
        .join(Schedule, ActionLog.schedule_id == Schedule.id)
        .filter(Schedule.user_id == user_id, Schedule.event_type == EventType.REMIND)
        .order_by(ActionLog.created_at.desc())
        .limit(200)
        .all()
    )

    streak = 0
    for (result,) in rows:
        if result == ActionResult.NO:
            streak += 1
            continue
        if result == ActionResult.YES:
            break
    return max(streak, 1)


def _safe_int(value: object, default: int) -> int:
    """Convert config-like value to int with fallback."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _count_today_zap_executions(session, user_id: str) -> int:
    """Count today's zap executions represented in punishment records."""
    from sqlalchemy import and_, or_

    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    return (
        session.query(Punishment.id)
        .join(Schedule, Punishment.schedule_id == Schedule.id)
        .filter(
            Schedule.user_id == user_id,
            Punishment.created_at >= day_start,
            Punishment.created_at < day_end,
            or_(
                Punishment.mode == PunishmentMode.NO,
                and_(
                    Punishment.mode == PunishmentMode.IGNORE,
                    Punishment.count >= 2,
                ),
            ),
        )
        .count()
    )


def _load_punishment_for_no(session, user_id: str, no_count: int) -> dict[str, Any]:
    """Build punishment display data from user config and NO streak count."""
    config_rows = (
        session.query(Configuration)
        .filter(
            Configuration.user_id == user_id,
            Configuration.key.in_(
                ["PAVLOK_TYPE_PUNISH", "PAVLOK_VALUE_PUNISH", "LIMIT_PAVLOK_ZAP_VALUE"]
            ),
        )
        .all()
    )
    config_map = {row.key: str(row.value) for row in config_rows}

    punish_type = config_map.get("PAVLOK_TYPE_PUNISH", "zap")
    try:
        base_value = int(config_map.get("PAVLOK_VALUE_PUNISH", "35"))
    except ValueError:
        base_value = 50
    try:
        limit_value = int(config_map.get("LIMIT_PAVLOK_ZAP_VALUE", "100"))
    except ValueError:
        limit_value = 100

    value = min(base_value + (10 * max(no_count - 1, 0)), limit_value)
    value = max(value, 0)
    return {"type": punish_type, "value": value}


async def _send_no_punishment(
    user_id: str,
    schedule_id: str,
    punishment: dict[str, Any],
) -> None:
    """Send Pavlok stimulus for NO response."""
    stimulus_type = str(punishment.get("type", "zap")).strip().lower()
    if stimulus_type not in {"zap", "beep", "vibe"}:
        stimulus_type = "zap"

    try:
        value = int(punishment.get("value", 35))
    except (TypeError, ValueError):
        value = 35
    value = max(0, min(100, value))

    if stimulus_type == "zap":
        from backend.worker.config_cache import get_config

        session = _get_session()
        try:
            zap_limit = _safe_int(
                get_config("LIMIT_DAY_PAVLOK_COUNTS", 100, session=session),
                100,
            )
            if zap_limit <= 0:
                zap_limit = 1
            zap_count = _count_today_zap_executions(session, user_id)
        except Exception as exc:
            print(
                f"[{datetime.now()}] no-punishment skipped: "
                f"user_id={user_id} schedule_id={schedule_id} "
                f"reason=failed to evaluate daily zap limit detail={exc}"
            )
            return
        finally:
            session.close()

        # NO punishment row is inserted before this async sender runs,
        # so ">" keeps the current trigger allowed and blocks excess sends.
        if zap_count > zap_limit:
            print(
                f"[{datetime.now()}] no-punishment skipped: "
                f"user_id={user_id} schedule_id={schedule_id} "
                f"reason=daily zap limit reached limit={zap_limit} count={zap_count}"
            )
            return

    reason_text = ""
    try:
        from backend.pavlok_lib import build_reason_for_schedule_id

        reason_text = build_reason_for_schedule_id(schedule_id)
    except Exception:
        reason_text = ""

    def _send() -> tuple[bool, str]:
        try:
            from backend.pavlok_lib import PavlokClient
            client = PavlokClient()
            result = client.stimulate(
                stimulus_type=stimulus_type,
                value=value,
                reason=reason_text,
            )
        except Exception as exc:
            return False, str(exc)

        if isinstance(result, dict) and result.get("success"):
            return True, "ok"
        return False, str(result)

    ok, detail = await asyncio.to_thread(_send)
    if ok:
        print(
            f"[{datetime.now()}] no-punishment sent: "
            f"user_id={user_id} schedule_id={schedule_id} "
            f"type={stimulus_type} value={value} "
            f"reason={reason_text or '-'}"
        )
    else:
        print(
            f"[{datetime.now()}] no-punishment failed: "
            f"user_id={user_id} schedule_id={schedule_id} "
            f"type={stimulus_type} value={value} detail={detail}"
        )


async def _notify_remind_result(
    channel_id: str,
    user_id: str,
    thread_ts: str,
    text: str,
    blocks: list[dict[str, Any]],
    reason_text: str = "",
) -> None:
    """Post remind result as a threaded Slack message."""
    bot_token = os.getenv("SLACK_BOT_USER_OAUTH_TOKEN")
    if not bot_token:
        print(
            f"[{datetime.now()}] skip remind-result notification: "
            "SLACK_BOT_USER_OAUTH_TOKEN is not configured"
        )
        return

    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    def _post() -> tuple[bool, str]:
        if not channel_id:
            return False, "missing channel_id for threaded response"

        payload_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<@{user_id}>",
                },
            },
            *blocks,
        ]

        post_payload: dict[str, Any] = {
            "channel": channel_id,
            "text": text,
            "blocks": payload_blocks,
            "unfurl_links": False,
            "unfurl_media": False,
        }
        if thread_ts:
            post_payload["thread_ts"] = thread_ts
            post_payload["reply_broadcast"] = False

        try:
            post_resp = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json=post_payload,
                timeout=2.5,
            )
            post_body = post_resp.json()
        except (requests.RequestException, ValueError) as exc:
            return False, f"chat.postMessage failed: {exc}"

        if not post_body.get("ok"):
            return False, f"chat.postMessage error: {post_body.get('error')}"
        return True, "ok"

    ok, post_detail = await asyncio.to_thread(_post)
    if ok:
        print(
            f"[{datetime.now()}] remind-result notification sent: "
            f"user_id={user_id} channel={channel_id} thread_ts={thread_ts or '-'}"
        )
        await _send_notification_stimulus(
            user_id=user_id,
            source="remind-result",
            reason=reason_text,
        )
    else:
        print(f"[{datetime.now()}] remind-result notification failed: {post_detail}")


async def process_remind_response(payload_data: Dict[str, Any], action: str = "YES") -> Dict[str, Any]:
    """
    リマインド応答処理（YES/NO）

    Args:
        payload_data: Slackペイロードデータ
        action: "YES" or "NO"

    Returns:
        Dict[str, Any]: 処理結果
    """
    user_id = payload_data.get("user", {}).get("id", "")
    schedule_id = _extract_schedule_id_from_action(payload_data)
    channel_id = _extract_action_channel_id(payload_data)
    thread_ts = _extract_action_thread_ts(payload_data)
    action_value = "YES" if action == "YES" else "NO"

    if not user_id or not schedule_id:
        return {
            "status": "success",
            "detail": "対象が見つかりませんでした。",
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "対象が見つかりませんでした。",
        }

    session = _get_session()
    try:
        schedule = (
            session.query(Schedule)
            .filter(Schedule.id == schedule_id, Schedule.user_id == user_id)
            .first()
        )
        if not schedule:
            return {
                "status": "success",
                "detail": "対象スケジュールが見つかりませんでした。",
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "対象スケジュールが見つかりませんでした。",
            }

        existing_action = (
            session.query(ActionLog.id)
            .filter(
                ActionLog.schedule_id == schedule.id,
                ActionLog.result.in_([ActionResult.YES, ActionResult.NO]),
            )
            .first()
        )
        if existing_action:
            return {
                "status": "success",
                "detail": "すでに応答済みです。",
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "すでに応答済みです。",
            }

        action_result = ActionResult.YES if action_value == "YES" else ActionResult.NO
        session.add(
            ActionLog(
                schedule_id=schedule.id,
                result=action_result,
            )
        )
        if action_value == "NO":
            existing_no_punishment = (
                session.query(Punishment.id)
                .filter(
                    Punishment.schedule_id == schedule.id,
                    Punishment.mode == PunishmentMode.NO,
                    Punishment.count == 1,
                )
                .first()
            )
            if not existing_no_punishment:
                session.add(
                    Punishment(
                        schedule_id=schedule.id,
                        mode=PunishmentMode.NO,
                        count=1,
                    )
                )
        schedule.state = ScheduleState.DONE
        schedule.updated_at = datetime.now()
        session.commit()

        task_name = _resolve_commitment_task_name_for_schedule(session, schedule)
        if action_value == "YES":
            detail = "やりました！"
            text = f"<@{user_id}> {task_name} を完了として記録しました。"
            from backend.slack_ui import remind_yes_response

            blocks = remind_yes_response(
                task_name=task_name,
                comment=schedule.yes_comment or "よくやった。この調子で継続しよう。",
            )
        else:
            detail = "できませんでした..."
            text = f"<@{user_id}> {task_name} は未達として記録しました。"
            no_count = _calc_no_streak_count(session, user_id)
            punishment = _load_punishment_for_no(session, user_id, no_count)
            from backend.slack_ui import remind_no_response

            blocks = remind_no_response(
                task_name=task_name,
                no_count=no_count,
                punishment=punishment,
                comment=schedule.no_comment or "次の一手をいま決めよう。",
            )

    except Exception as exc:
        session.rollback()
        print(f"[{datetime.now()}] process_remind_response DB error: {exc}")
        return {
            "status": "success",
            "detail": "処理に失敗しました。",
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "処理に失敗しました。再度お試しください。",
        }
    finally:
        session.close()

    asyncio.create_task(
        _notify_remind_result(
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=thread_ts,
            text=text,
            blocks=blocks,
            reason_text=f"remind: {task_name}",
        )
    )
    if action_value == "NO":
        asyncio.create_task(
            _send_no_punishment(
                user_id=user_id,
                schedule_id=schedule_id,
                punishment=punishment,
            )
        )

    # Slack block_actions ack payload (valid message response).
    return {
        "status": "success",
        "detail": detail,
        "response_type": "ephemeral",
        "replace_original": False,
        "text": detail,
    }


async def process_ignore_response(payload_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    無視応答処理（今やりました/やっぱり）

    Args:
        payload_data: Slackペイロードデータ

    Returns:
        Dict[str, Any]: 処理結果
    """
    # TODO: Implement actual ignore response processing with database
    actions = payload_data.get("actions", [])
    if actions:
        action_value = actions[0].get("value", "")
        try:
            import json
            value_data = json.loads(action_value)
            action_type = "yes" if "yes" in actions[0].get("action_id", "") else "no"
        except (json.JSONDecodeError, TypeError):
            action_type = "yes"
    else:
        action_type = "yes"

    if action_type == "yes":
        return {
            "status": "success",
            "detail": "今やりました"
        }
    else:
        return {
            "status": "success",
            "detail": "やっぱり..."
        }
