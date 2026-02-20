"""
v0.3 BlockKit UI Components

Slack BlockKit JSON generators for Oni System v0.3 UI components.
Following v0.3_slack_ui_spec.md specifications.
"""
from datetime import datetime
from typing import Any


# ============================================================================
# Helper Functions
# ============================================================================

def format_timestamp_jst(dt: datetime) -> str:
    """Format datetime to JST string for display"""
    return dt.strftime("%Y-%m-%d %H:%M")


def punishment_display_text(punishment: dict[str, Any]) -> str:
    """Format punishment for display"""
    p_type = punishment.get("type", "zap")
    value = punishment.get("value", 0)

    type_emoji = {
        "zap": "⚡",
        "vibe": "📳",
        "beep": "🔊",
    }
    type_name = {
        "zap": "zap",
        "vibe": "vibe",
        "beep": "beep",
    }

    emoji = type_emoji.get(p_type, "⚡")
    name = type_name.get(p_type, "zap")

    return f"{emoji} {name} {value}%"


# ============================================================================
# Base Commit Modal (/base_commit)
# ============================================================================

def _commitment_row_blocks(index: int, commitment: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Generate blocks for a single commitment row"""
    task = commitment.get("task", "") if commitment else ""
    time = commitment.get("time", "") if commitment else ""

    task_element = {
        "type": "plain_text_input",
        "action_id": f"task_{index}",
        "placeholder": {
            "type": "plain_text",
            "text": "タスク名",
        },
        "max_length": 100,
    }
    if task:
        task_element["initial_value"] = task

    time_element = {
        "type": "timepicker",
        "action_id": f"time_{index}",
        "placeholder": {
            "type": "plain_text",
            "text": "時間を選択",
        },
    }
    if time and len(time) >= 5:
        candidate = time[:5]
        hh, mm = candidate.split(":") if ":" in candidate else ("", "")
        if hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
            time_element["initial_time"] = candidate

    return [
        {
            "type": "input",
            "block_id": f"commitment_{index}",
            "label": {
                "type": "plain_text",
                "text": f"コミットメント {index}",
            },
            "element": task_element,
            "dispatch_action": True,
            "optional": True,
        },
        {
            "type": "input",
            "block_id": f"time_{index}",
            "label": {
                "type": "plain_text",
                "text": f"時刻 {index}",
            },
            "element": time_element,
            "optional": True,
        },
    ]


def base_commit_modal(commitments: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate /base_commit modal"""
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "毎日実行するコミットメントを設定します。入力内容はplan_APIに送信されます。",
            },
        },
        {
            "type": "divider",
        },
    ]

    # Add commitment rows (minimum 3)
    display_count = max(3, len(commitments))
    for i in range(1, display_count + 1):
        commitment = commitments[i - 1] if i <= len(commitments) else None
        blocks.extend(_commitment_row_blocks(i, commitment))
        if i < display_count:
            blocks.append({"type": "divider"})

    # Add action buttons
    blocks.extend([
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "+ 追加",
                    },
                    "style": "primary",
                    "action_id": "commitment_add_row",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "- 削除",
                    },
                    "style": "danger",
                    "action_id": "commitment_remove_row",
                }
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 コミットメントは毎日指定時刻にplanイベントとして登録されます",
                }
            ],
        },
    ])

    return {
        "type": "modal",
        "callback_id": "base_commit_submit",
        "title": {
            "type": "plain_text",
            "text": "📋 コミットメント管理",
        },
        "submit": {
            "type": "plain_text",
            "text": "送信",
        },
        "blocks": blocks,
    }


# ============================================================================
# Stop/Restart/Help Notifications (/stop, /restart, /help)
# ============================================================================

def stop_notification() -> list[dict[str, Any]]:
    """Generate /stop notification blocks"""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⏸️ *鬼コーチを停止しました*\n\n再開するには `/restart` を実行してください。",
            },
        }
    ]


def restart_notification() -> list[dict[str, Any]]:
    """Generate /restart notification blocks"""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "▶️ *鬼コーチを再開しました*",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "次回のWorkerサイクルから通常運用が再開されます",
                }
            ],
        },
    ]


def help_notification() -> list[dict[str, Any]]:
    """Generate /help notification blocks."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "👹 鬼コーチ /help",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*アプリ概要*\n"
                    "鬼コーチは、毎日の習慣を続けるためのサポートアプリです。\n"
                    "Slack通知とPavlokを使って、行動を最後までやり切れるように支援します。"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*はじめかた（最短1ステップ）*\n"
                    "1. `/base_commit` で「毎日やること」を登録\n\n"
                    "※ 通常はこの後、自動で plan 通知が届きます。\n"
                    "※ すぐに編集したい場合は `/plan` を使って手動で開けます。"
                ),
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*コマンド一覧*\n"
                    "`/base_commit` 毎日やることを登録・編集します\n"
                    "`/plan` 今日の予定（実行時刻）を手動で確認・更新します\n"
                    "`/config` 通知や刺激の強さなどを設定します\n"
                    "`/stop` 鬼コーチを一時停止します\n"
                    "`/restart` 鬼コーチを再開します\n"
                    "`/help` このヘルプを表示します"
                ),
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*毎日の流れ*\n"
                    "1. 予定決め: 鬼コーチから届く「予定を登録」通知で、今日の実行時刻を決める（通常はコマンド不要）\n"
                    "2. 実行確認: 指定時刻に通知が届くので `やりました` / `やれません` を選ぶ\n"
                    "3. 次の日へ: 回答内容をもとに次の行動につなげる"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*刺激（ペナルティ）について*\n"
                    "• 通知を無視した場合: 一定時間（初期値: 15分）ごとに再通知され、"
                    "反応があるまで監視が続きます。無視が続くと刺激が段階的に強くなります。\n"
                    "• `やれません` を選んだ場合: その場で刺激が実行されます。"
                    "連続回数が増えるほど強くなります。"
                ),
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*安全上の注意（必読）*\n"
                    "車・自転車・バイクなどの運転中に強い刺激が発生すると、"
                    "重大な事故につながるおそれがあります。\n"
                    "Slack通知の時刻は、運転時間と重ならないように必ず設定してください。\n"
                    "運転する可能性がある時間帯は `/stop` で一時停止し、"
                    "終了後に `/restart` で再開してください。"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "必要なときはいつでも `/config` で設定を調整してください。",
                }
            ],
        },
    ]


# ============================================================================
# Config Modal (/config)
# ============================================================================

def _punishment_section(config_values: dict[str, str]) -> list[dict[str, Any]]:
    """Generate punishment configuration section"""
    current_type = config_values.get("PAVLOK_TYPE_PUNISH", "zap")
    current_notion_type = config_values.get("PAVLOK_TYPE_NOTION", "vibe")
    type_options = [
        {"text": {"type": "plain_text", "text": "⚡ zap (電気ショック)"}, "value": "zap"},
        {"text": {"type": "plain_text", "text": "📳 vibe (振動)"}, "value": "vibe"},
        {"text": {"type": "plain_text", "text": "🔊 beep (音)"}, "value": "beep"},
    ]

    # Find initial option
    initial_option = None
    for opt in type_options:
        if opt["value"] == current_type:
            initial_option = opt
            break
    notion_initial_option = None
    for opt in type_options:
        if opt["value"] == current_notion_type:
            notion_initial_option = opt
            break

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔴 罰設定",
            },
        },
        {
            "type": "input",
            "block_id": "PAVLOK_TYPE_PUNISH",
            "label": {
                "type": "plain_text",
                "text": "デフォルト罰スタイル",
            },
            "element": {
                "type": "static_select",
                "action_id": "PAVLOK_TYPE_PUNISH_select",
                "initial_option": initial_option or type_options[0],
                "options": type_options,
            },
        },
        {
            "type": "input",
            "block_id": "PAVLOK_VALUE_PUNISH",
            "label": {
                "type": "plain_text",
                "text": "デフォルト罰強度 (0-100)",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "PAVLOK_VALUE_PUNISH_input",
                "initial_value": config_values.get("PAVLOK_VALUE_PUNISH", "35"),
                "placeholder": {
                    "type": "plain_text",
                    "text": "0-100の数値",
                },
                "min_length": 1,
                "max_length": 3,
            },
            "hint": {
                "type": "plain_text",
                "text": ":warning: 80以上は非常に強力です。十分に注意してください。",
            },
        },
        {
            "type": "input",
            "block_id": "LIMIT_DAY_PAVLOK_COUNTS",
            "label": {
                "type": "plain_text",
                "text": "1日の最大ZAP回数",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "LIMIT_DAY_PAVLOK_COUNTS_input",
                "initial_value": config_values.get("LIMIT_DAY_PAVLOK_COUNTS", "100"),
                "placeholder": {
                    "type": "plain_text",
                    "text": "例: 100",
                },
                "min_length": 1,
                "max_length": 4,
            },
        },
        {
            "type": "input",
            "block_id": "LIMIT_PAVLOK_ZAP_VALUE",
            "label": {
                "type": "plain_text",
                "text": "最大ZAP強度 (安全リミット)",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "LIMIT_PAVLOK_ZAP_VALUE_input",
                "initial_value": config_values.get("LIMIT_PAVLOK_ZAP_VALUE", "100"),
                "placeholder": {
                    "type": "plain_text",
                    "text": "0-100の数値",
                },
                "min_length": 1,
                "max_length": 3,
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔔 通知設定",
            },
        },
        {
            "type": "input",
            "block_id": "PAVLOK_TYPE_NOTION",
            "label": {
                "type": "plain_text",
                "text": "通知時のPavlokタイプ",
            },
            "element": {
                "type": "static_select",
                "action_id": "PAVLOK_TYPE_NOTION_select",
                "initial_option": notion_initial_option or type_options[1],
                "options": type_options,
            },
        },
        {
            "type": "input",
            "block_id": "PAVLOK_VALUE_NOTION",
            "label": {
                "type": "plain_text",
                "text": "通知時のPavlok強度 (0-100)",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "PAVLOK_VALUE_NOTION_input",
                "initial_value": config_values.get("PAVLOK_VALUE_NOTION", "35"),
                "placeholder": {
                    "type": "plain_text",
                    "text": "0-100の数値",
                },
                "min_length": 1,
                "max_length": 3,
            },
        },
    ]


def _ignore_section(config_values: dict[str, str]) -> list[dict[str, Any]]:
    """Generate ignore mode configuration section"""
    interval_options = [
        {"text": {"type": "plain_text", "text": "5分 (300秒)"}, "value": "300"},
        {"text": {"type": "plain_text", "text": "10分 (600秒)"}, "value": "600"},
        {"text": {"type": "plain_text", "text": "15分 (900秒)"}, "value": "900"},
        {"text": {"type": "plain_text", "text": "30分 (1800秒)"}, "value": "1800"},
    ]

    current_interval = config_values.get("IGNORE_INTERVAL", "900")
    initial_option = None
    for opt in interval_options:
        if opt["value"] == current_interval:
            initial_option = opt
            break

    return [
        {
            "type": "divider",
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚡ Ignoreモード設定",
            },
        },
        {
            "type": "input",
            "block_id": "IGNORE_INTERVAL",
            "label": {
                "type": "plain_text",
                "text": "検知間隔 (秒)",
            },
            "element": {
                "type": "static_select",
                "action_id": "IGNORE_INTERVAL_select",
                "initial_option": initial_option or interval_options[2],
                "options": interval_options,
            },
        },
        {
            "type": "input",
            "block_id": "IGNORE_JUDGE_TIME",
            "label": {
                "type": "plain_text",
                "text": "判定時間 (秒)",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "IGNORE_JUDGE_TIME_input",
                "initial_value": config_values.get("IGNORE_JUDGE_TIME", "3"),
                "placeholder": {
                    "type": "plain_text",
                    "text": "例: 3",
                },
                "min_length": 1,
                "max_length": 3,
            },
        },
        {
            "type": "input",
            "block_id": "IGNORE_MAX_RETRY",
            "label": {
                "type": "plain_text",
                "text": "最大再試行回数",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "IGNORE_MAX_RETRY_input",
                "initial_value": config_values.get("IGNORE_MAX_RETRY", "5"),
                "placeholder": {
                    "type": "plain_text",
                    "text": "例: 5",
                },
                "min_length": 1,
                "max_length": 2,
            },
        },
    ]


def _coach_section(config_values: dict[str, str]) -> list[dict[str, Any]]:
    """Generate coach character configuration section."""
    return [
        {
            "type": "divider",
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "💬 コーチ口調設定",
            },
        },
        {
            "type": "input",
            "block_id": "COACH_CHARACTOR",
            "label": {
                "type": "plain_text",
                "text": "キャラクター",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "COACH_CHARACTOR_input",
                "initial_value": config_values.get(
                    "COACH_CHARACTOR",
                    "うる星やつらのラムちゃん",
                ),
                "placeholder": {
                    "type": "plain_text",
                    "text": "例: うる星やつらのラムちゃん",
                },
                "min_length": 1,
                "max_length": 100,
            },
            "hint": {
                "type": "plain_text",
                "text": "agent_callのコメント生成時に使用されます。",
            },
        },
    ]


def config_modal(config_values: dict[str, str]) -> dict[str, Any]:
    """Generate /config modal"""
    blocks = []
    blocks.extend(_punishment_section(config_values))
    blocks.extend(_ignore_section(config_values))
    blocks.extend(_coach_section(config_values))

    # Add action buttons
    blocks.append({
        "type": "divider",
    })
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "🔄 全リセット",
                },
                "style": "danger",
                "action_id": "config_reset_all",
                "confirm": {
                    "title": {
                        "type": "plain_text",
                        "text": "確認",
                    },
                    "text": {
                        "type": "plain_text",
                        "text": "全ての設定をデフォルト値にリセットします。よろしいですか？",
                    },
                    "confirm": {
                        "type": "plain_text",
                        "text": "リセット",
                    },
                    "deny": {
                        "type": "plain_text",
                        "text": "キャンセル",
                    },
                },
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📋 変更履歴",
                },
                "action_id": "config_history",
            },
        ],
    })

    return {
        "type": "modal",
        "callback_id": "config_submit",
        "title": {
            "type": "plain_text",
            "text": "⚙️ Oni System 設定",
        },
        "submit": {
            "type": "plain_text",
            "text": "保存",
        },
        "blocks": blocks,
    }


# ============================================================================
# Audit Log Display (/audit)
# ============================================================================

def audit_log_display(audit_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate /audit display blocks"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📋 設定変更履歴 (直近7日間)",
            },
        },
    ]

    for log in audit_logs[:10]:  # Show last 10
        changed_at = log.get("changed_at", datetime.now())
        if isinstance(changed_at, datetime):
            changed_str = format_timestamp_jst(changed_at)
        else:
            changed_str = str(changed_at)

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{changed_str}*\n`{log.get('config_key', '')}`: {log.get('old_value', '-')} → {log.get('new_value', '-')}\nby @{log.get('changed_by', 'user')}",
            },
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "もっと見る",
                },
                "action_id": "audit_more",
            },
        ],
    })

    return blocks


# ============================================================================
# Plan Event UI
# ============================================================================

def plan_start_notification(
    schedule_id: str,
    user_id: str = "",
    ignore_interval_minutes: int = 15,
) -> list[dict[str, Any]]:
    """Generate plan start notification blocks"""
    if ignore_interval_minutes < 1:
        ignore_interval_minutes = 1

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📅 今日の予定を登録しましょう",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "おはようございます！今日の計画を立てましょう。\n以下のボタンをクリックして予定を登録してください。",
            },
        },
    ]

    if user_id:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<@{user_id}>",
                },
            }
        )

    blocks.extend(
        [
        {
            "type": "actions",
            "block_id": "plan_trigger",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📝 予定を登録",
                    },
                    "style": "primary",
                    "action_id": "plan_open_modal",
                    "value": f'{{"schedule_id": "{schedule_id}"}}',
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"⏰ 応答がない場合、"
                        f"{ignore_interval_minutes}分後に催促が始まります"
                    ),
                },
            ],
        },
    ]
    )
    return blocks


def _plan_task_blocks(index: int, commitment: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate blocks for a single task in plan modal"""
    task_emoji = {
        "朝の瞑想": "🧘",
        "メールチェック": "📧",
        "振り返り": "📝",
    }

    task = commitment.get("task", f"タスク {index}")
    time = commitment.get("time", "09:00")
    date_value = commitment.get("date", "today")
    if date_value not in {"today", "tomorrow"}:
        date_value = "today"

    # Use default time if commitment exists
    initial_time = time[:5] if len(time) >= 5 else "09:00"

    date_options = [
        {"text": {"type": "plain_text", "text": "今日"}, "value": "today"},
        {"text": {"type": "plain_text", "text": "明日"}, "value": "tomorrow"},
    ]
    initial_date_option = date_options[0]
    for option in date_options:
        if option["value"] == date_value:
            initial_date_option = option
            break

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{task_emoji.get(task, '📋')} {task}*",
            },
        },
        {
            "type": "input",
            "block_id": f"task_{index}_date",
            "label": {
                "type": "plain_text",
                "text": "実行日",
            },
            "element": {
                "type": "static_select",
                "action_id": "date",
                "initial_option": initial_date_option,
                "options": date_options,
            },
        },
        {
            "type": "input",
            "block_id": f"task_{index}_time",
            "label": {
                "type": "plain_text",
                "text": "実行時間",
            },
            "element": {
                "type": "timepicker",
                "action_id": "time",
                "initial_time": initial_time,
            },
        },
        {
            "type": "input",
            "block_id": f"task_{index}_skip",
            "label": {
                "type": "plain_text",
                "text": "やらない",
            },
            "element": {
                "type": "checkboxes",
                "action_id": "skip",
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "今日は実行しない"},
                        "value": "skip",
                    },
                ],
            },
            "optional": True,
        },
        {
            "type": "divider",
        },
    ]


def plan_input_modal(
    commitments: list[dict[str, Any]],
    next_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate plan input modal"""
    blocks = []

    for i, commitment in enumerate(commitments, 1):
        blocks.extend(_plan_task_blocks(i, commitment))

    next_plan_data = next_plan or {}
    next_plan_date_value = str(next_plan_data.get("date", "tomorrow"))
    if next_plan_date_value not in {"today", "tomorrow"}:
        next_plan_date_value = "tomorrow"
    next_plan_time = str(next_plan_data.get("time", "07:00"))
    if len(next_plan_time) >= 5:
        next_plan_time = next_plan_time[:5]
    else:
        next_plan_time = "07:00"

    next_plan_date_options = [
        {"text": {"type": "plain_text", "text": "今日"}, "value": "today"},
        {"text": {"type": "plain_text", "text": "明日"}, "value": "tomorrow"},
    ]
    next_plan_initial_option = next_plan_date_options[1]
    for option in next_plan_date_options:
        if option["value"] == next_plan_date_value:
            next_plan_initial_option = option
            break

    # Add next plan section
    blocks.extend([
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🔁 次回計画 (event.plan)*",
            },
        },
        {
            "type": "input",
            "block_id": "next_plan_date",
            "label": {
                "type": "plain_text",
                "text": "実行日",
            },
            "element": {
                "type": "static_select",
                "action_id": "date",
                "initial_option": next_plan_initial_option,
                "options": next_plan_date_options,
            },
        },
        {
            "type": "input",
            "block_id": "next_plan_time",
            "label": {
                "type": "plain_text",
                "text": "実行時間",
            },
            "element": {
                "type": "timepicker",
                "action_id": "time",
                "initial_time": next_plan_time,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 次回計画は必須です。スキップできません。",
                },
            ],
        },
    ])

    return {
        "type": "modal",
        "callback_id": "plan_submit",
        "title": {
            "type": "plain_text",
            "text": "📅 今日の予定",
        },
        "submit": {
            "type": "plain_text",
            "text": "送信",
        },
        "blocks": blocks,
    }


def plan_complete_notification(
    scheduled_tasks: list[dict[str, Any]],
    next_plan: dict[str, str],
) -> list[dict[str, Any]]:
    """Generate plan complete notification blocks"""
    task_lines = []
    for task in scheduled_tasks:
        task_lines.append(f"*{task.get('task', '')}*\n🕐 {task.get('date', '今日')} {task.get('time', '')}")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📅 本日の予定を登録しました",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n\n".join(task_lines),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔁 次回計画: {next_plan.get('date', '明日')} {next_plan.get('time', '')}*",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 各時刻にリマインドされます",
                },
            ],
        },
    ]

    return blocks


# ============================================================================
# Remind Event UI
# ============================================================================

def remind_post(
    schedule_id: str,
    task_name: str,
    task_time: str,
    description: str,
    ignore_interval_minutes: int = 15,
) -> list[dict[str, Any]]:
    """Generate remind post blocks"""
    if ignore_interval_minutes < 1:
        ignore_interval_minutes = 1

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔔 リマインド",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{task_name}*\n🕐 {task_time}\n\n{description}\n準備はできましたか？",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "actions",
            "block_id": "remind_response",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✓ やりました！",
                    },
                    "style": "primary",
                    "action_id": "remind_yes",
                    "value": f'{{"schedule_id": "{schedule_id}", "event_type": "remind"}}',
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✕ やれません",
                    },
                    "style": "danger",
                    "action_id": "remind_no",
                    "value": f'{{"schedule_id": "{schedule_id}", "event_type": "remind"}}',
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ 応答がない場合、"
                        f"{ignore_interval_minutes}分ごとにPavlokが動作します"
                    ),
                },
            ],
        },
    ]


def remind_yes_response(task_name: str, comment: str) -> list[dict[str, Any]]:
    """Generate remind YES response blocks"""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎉 *{task_name}*\n✓ 完了しました！\n\n> {comment}",
            },
        },
    ]


def remind_no_response(
    task_name: str,
    no_count: int,
    punishment: dict[str, Any],
    comment: str,
) -> list[dict[str, Any]]:
    """Generate remind NO response blocks"""
    punishment_text = punishment_display_text(punishment)

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"😢 *{task_name}*\n✕ できませんでした...\n\n今回のNO回数: {no_count}回\n罰: {punishment_text}\n\n> {comment}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "⚡ Pavlokから刺激を送信しました",
                },
            ],
        },
    ]


# ============================================================================
# Ignore Detection UI
# ============================================================================

def ignore_detection_post(
    schedule_id: str,
    task_name: str,
    task_time: str,
    ignore_minutes: int,
    punishment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate ignore detection post blocks"""
    punishment_text = punishment_display_text(punishment)

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ 応答待ち",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{task_name}*\n🕐 {task_time}\n\n応答を待っています...\n\n無視時間: {ignore_minutes}分経過\ngentle reminder: {punishment_text}",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✓ 今やりました！",
                    },
                    "style": "primary",
                    "action_id": "ignore_yes",
                    "value": f'{{"schedule_id": "{schedule_id}", "event_type": "ignore"}}',
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✕ やれません",
                    },
                    "style": "danger",
                    "action_id": "ignore_no",
                    "value": f'{{"schedule_id": "{schedule_id}", "event_type": "ignore"}}',
                },
            ],
        },
    ]


def ignore_max_reached_post(
    task_name: str,
    task_time: str,
    final_punishment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate ignore max reached post blocks"""
    punishment_text = punishment_display_text(final_punishment)

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "❌ 自動キャンセル",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{task_name}*\n🕐 {task_time}\n\n長時間無視が続いたため、このタスクは自動的にキャンセルされました。\n\n最終罰: {punishment_text}\n\n> 次は一緒に頑張りましょう。",
            },
        },
    ]


# ============================================================================
# Error Notifications
# ============================================================================

def error_notification(
    error_message: str,
    retry_action_id: str = "retry",
) -> list[dict[str, Any]]:
    """Generate error notification blocks"""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "❌ エラーが発生しました",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"設定の保存中にエラーが発生しました。\n\n```\n{error_message}\n```",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "再試行",
                    },
                    "action_id": retry_action_id,
                },
            ],
        },
    ]


def daily_zap_limit_notification(limit: int) -> list[dict[str, Any]]:
    """Generate daily ZAP limit notification blocks"""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🛑 本日の罰上限に到達",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"本日のZAP回数が *{limit}回* に達しました。\n\n安全のため、これ以上の罰は実行されません。\n明日はリセットされます。",
            },
        },
    ]
