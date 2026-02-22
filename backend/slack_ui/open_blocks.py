"""Slack UI Package for Oni System v0.3"""

from typing import Any

# ============================================================================
# Slack BlockKit Components
# ============================================================================


def open_base_commitment_modal(user_id: str | None = None) -> dict[str, Any]:
    """
    Generate a base commitment modal for Slack BlockKit.

    Args:
        user_id: User ID (optional, for testing)

    Returns:
        Modal response dictionary
    """
    # Get existing commitments
    # TODO: Implement database query
    # For now, return mock data
    commitments = [
        {
            "id": "test-id-1",
            "user_id": "U01",
            "time": "09:00",
            "task": "テストタスク",
            "active": True,
        },
        {"id": "test-id-2", "user_id": "U01", "time": "10:00", "task": "テスト2", "active": True},
    ]

    # Calculate index (min 3)
    max(len(commitments), 3) + 1

    # Create blocks
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "毎日実行するコミットメントを設定します。入力内容はplan_APIに送信されます。",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "+ 追加"},
                    "style": "primary",
                    "action_id": "commitment_add_row",
                }
            ],
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "コミットは毎日指定時刻にplanイベントとして登録されます"}
            ],
        },
    ]

    # Create modal response
    return {
        "type": "modal",
        "trigger_id": "base_commit_submit",
        "view": {
            "type": "modal",
            "callback_id": "base_commit_submit",
            "title": {"type": "plain_text", "text": "ベースコミット管理"},
            "submit": {"type": "plain_text", "text": "送信"},
            "blocks": blocks,
        },
    }


def open_plan_modal(schedule_id: str) -> dict[str, Any]:
    """
    Generate a plan modal for confirming schedule.

    Args:
        schedule_id: Schedule ID

    Returns:
        Modal response dictionary
    """
    # Calculate suggested times based on schedule time
    # TODO: Get schedule from database
    # For now, return mock data
    suggested_times = ["09:00", "10:00", "15:00"]

    # Create blocks
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "確認時間をお選択してください。\\n現在の予定:"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "radio_button",
                    "text": {"type": "plain_text", "text": time},
                    "value": time,
                }
                for time in suggested_times
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "送信"},
                    "style": "primary",
                    "action_id": "plan_submit",
                }
            ],
        },
    ]

    return {
        "type": "modal",
        "trigger_id": "plan_submit",
        "view": {
            "type": "modal",
            "callback_id": "plan_submit",
            "title": {"type": "plain_text", "text": "予定確認"},
            "submit": {"type": "plain_text", "text": "送信"},
            "blocks": blocks,
        },
    }


def remind_blocks(schedule_id: str, thread_ts: str | None = None) -> list[dict[str, Any]]:
    """
    Generate remind blocks with YES/NO buttons and thread reference.

    Args:
        schedule_id: Schedule ID
        thread_ts: Thread timestamp for message update (optional)

    Returns:
        List of BlockKit block dictionaries
    """
    blocks = []

    # YES button
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "やりました"},
                    "style": "primary",
                    "action_id": "remind_yes",
                    "value": "yes",
                }
            ],
        }
    )

    # NO button
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "できません"},
                    "style": "danger",
                    "action_id": "remind_no",
                    "value": "no",
                }
            ],
        }
    )

    # Divider
    blocks.append({"type": "divider"})

    # Add thread_ts if provided
    if thread_ts:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"スレッド: {thread_ts}"}]}
        )

    return blocks
