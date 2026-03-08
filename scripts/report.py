#!/usr/bin/env python3
# ruff: noqa: E402
"""
v0.3 Report Event Script

reportイベント実行:
- monthly/weekly 判定
- 期間算出
- remind実績集計
- Markdown表 + LLMコメント投稿
- report_deliveries 保存
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from backend.models import (
    ActionLog,
    ActionResult,
    Commitment,
    EventType,
    ReportDelivery,
    Schedule,
    ScheduleState,
)
from backend.slack_ui import report_post
from scripts import slack
from scripts.agent_call import load_coach_charactor, run_codex_exec

REPORT_PROMPT_PATH = ROOT / "prompts" / "report_comment.md"
REPORT_SCHEMA_VERSION = "report_comment_v1"


def previous_month_period(run_date: date) -> tuple[date, date]:
    """Return previous month start/end dates."""
    this_month_start = run_date.replace(day=1)
    prev_month_end = this_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    return prev_month_start, prev_month_end


def is_previous_monthly_delivered(session, user_id: str, run_date: date) -> bool:
    """Check whether previous month's monthly report was posted."""
    prev_start, prev_end = previous_month_period(run_date)
    row = (
        session.query(ReportDelivery.id)
        .filter(
            ReportDelivery.user_id == user_id,
            ReportDelivery.report_type == "monthly",
            ReportDelivery.period_start == prev_start,
            ReportDelivery.period_end == prev_end,
            ReportDelivery.posted_at.isnot(None),
        )
        .first()
    )
    return row is not None


def decide_report_type(session, user_id: str, run_date: date) -> str:
    """Resolve report type at execution time."""
    if is_previous_monthly_delivered(session, user_id, run_date):
        return "weekly"
    return "monthly"


def resolve_report_period(
    session, user_id: str, run_date: date, report_type: str
) -> tuple[date, date]:
    """Resolve aggregation period for monthly/weekly report."""
    if report_type == "monthly":
        return previous_month_period(run_date)

    last_weekly_end = (
        session.query(func.max(ReportDelivery.period_end))
        .filter(
            ReportDelivery.user_id == user_id,
            ReportDelivery.report_type == "weekly",
            ReportDelivery.posted_at.isnot(None),
        )
        .scalar()
    )
    if isinstance(last_weekly_end, date):
        period_start = last_weekly_end + timedelta(days=1)
    else:
        period_start = run_date.replace(day=1)
    period_end = run_date - timedelta(days=1)
    return period_start, period_end


def aggregate_report_stats(
    session,
    user_id: str,
    period_start: date,
    period_end: date,
) -> dict[str, float | int]:
    """Aggregate success/failure/success_rate per commitment task from remind schedules."""
    remind_rows = (
        session.query(
            Schedule.id,
            Schedule.commitment_id,
            Commitment.task,
            Schedule.comment,
        )
        .outerjoin(
            Commitment,
            Commitment.id == Schedule.commitment_id,
        )
        .filter(
            Schedule.user_id == user_id,
            Schedule.event_type == EventType.REMIND,
            Schedule.thread_ts.isnot(None),
            func.date(Schedule.run_at) >= str(period_start),
            func.date(Schedule.run_at) <= str(period_end),
        )
        .order_by(Schedule.run_at.asc(), Schedule.created_at.asc())
        .all()
    )
    target_ids = [str(row[0]) for row in remind_rows]
    total_count = len(target_ids)
    if total_count == 0:
        return {
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "by_commitment": [],
        }

    success_schedule_ids = {
        str(row[0])
        for row in (
            session.query(ActionLog.schedule_id)
            .filter(
                ActionLog.schedule_id.in_(target_ids),
                ActionLog.result == ActionResult.YES,
            )
            .distinct()
            .all()
        )
    }

    by_commitment: dict[str, dict[str, float | int | str]] = {}
    for schedule_id, commitment_id, commitment_task, schedule_comment in remind_rows:
        task_name = str(commitment_task or schedule_comment or "不明").strip() or "不明"
        group_key = str(commitment_id) if commitment_id else f"task:{task_name}"
        if group_key not in by_commitment:
            by_commitment[group_key] = {
                "task": task_name,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
            }
        if str(schedule_id) in success_schedule_ids:
            by_commitment[group_key]["success_count"] = (
                int(by_commitment[group_key]["success_count"]) + 1
            )
        else:
            by_commitment[group_key]["failure_count"] = (
                int(by_commitment[group_key]["failure_count"]) + 1
            )

    commitment_rows: list[dict[str, float | int | str]] = []
    for row in by_commitment.values():
        success = int(row["success_count"])
        failure = int(row["failure_count"])
        total = success + failure
        rate = round((100.0 * success) / total, 1) if total else 0.0
        row["success_rate"] = rate
        commitment_rows.append(row)

    success_count = sum(int(row["success_count"]) for row in commitment_rows)
    failure_count = sum(int(row["failure_count"]) for row in commitment_rows)
    success_rate = round((100.0 * success_count) / total_count, 1) if total_count else 0.0
    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "by_commitment": commitment_rows,
    }


def _normalize_commitment_rows(stats: dict[str, float | int]) -> list[dict[str, float | int | str]]:
    """Normalize commitment rows for rendering/storage."""
    rows = stats.get("by_commitment", [])
    if not isinstance(rows, list):
        rows = []
    normalized: list[dict[str, float | int | str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "task": str(row.get("task", "不明")).strip() or "不明",
                "success_count": int(row.get("success_count", 0)),
                "failure_count": int(row.get("failure_count", 0)),
                "success_rate": float(row.get("success_rate", 0.0)),
            }
        )
    if not normalized:
        normalized = [
            {
                "task": "（対象なし）",
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
            }
        ]
    return normalized


def format_report_summary_text(stats: dict[str, float | int]) -> str:
    """Format plain-text summary for DB storage/report trace."""
    success_count = int(stats.get("success_count", 0))
    failure_count = int(stats.get("failure_count", 0))
    success_rate = float(stats.get("success_rate", 0.0))
    rows = _normalize_commitment_rows(stats)
    lines = [
        f"合計: 成功 {success_count} / 失敗 {failure_count} / 成功率 {success_rate:.1f}%",
    ]
    for row in rows:
        lines.append(
            f"- {row['task']}: "
            f"成功 {int(row['success_count'])} / "
            f"失敗 {int(row['failure_count'])} / "
            f"成功率 {float(row['success_rate']):.1f}%"
        )
    return "\n".join(lines)


def build_comment_payload(
    report_type: str,
    period_start: date,
    period_end: date,
    stats: dict[str, float | int],
) -> dict[str, Any]:
    """Build JSON payload for report comment generation."""
    commitment_rows = stats.get("by_commitment", [])
    if not isinstance(commitment_rows, list):
        commitment_rows = []
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": report_type,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "stats": {
            "success_count": int(stats.get("success_count", 0)),
            "failure_count": int(stats.get("failure_count", 0)),
            "success_rate": float(stats.get("success_rate", 0.0)),
        },
        "commitment_stats": [
            {
                "task": str(row.get("task", "不明")),
                "success_count": int(row.get("success_count", 0)),
                "failure_count": int(row.get("failure_count", 0)),
                "success_rate": float(row.get("success_rate", 0.0)),
            }
            for row in commitment_rows
        ],
    }


def render_report_comment_prompt(payload: dict[str, Any], charactor: str) -> str:
    """Render prompt text for codex exec."""
    if not REPORT_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Prompt template not found: {REPORT_PROMPT_PATH}")

    template = REPORT_PROMPT_PATH.read_text(encoding="utf-8")
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    prompt = template.replace("{{charactor}}", charactor)
    prompt = prompt.replace("{{payload_json}}", payload_json)
    return prompt


def fallback_report_comment(report_type: str, stats: dict[str, float | int]) -> str:
    """Fallback comment when codex execution fails."""
    success_rate = float(stats.get("success_rate", 0.0))
    report_label = "月次" if report_type == "monthly" else "週次"
    if success_rate >= 80:
        return f"{report_label}の達成率は高水準です。この調子で継続しましょう。"
    if success_rate >= 50:
        return f"{report_label}の達成率は安定しています。次は失敗要因を1つ減らしましょう。"
    return f"{report_label}の達成率は伸びしろがあります。次回は最初の1件を早めに完了しましょう。"


def generate_report_comment(
    payload: dict[str, Any],
    report_type: str,
    stats: dict[str, float | int],
    charactor: str,
) -> tuple[str, dict[str, Any]]:
    """Generate LLM comment using codex exec (with fallback)."""
    prompt = render_report_comment_prompt(payload, charactor=charactor)
    codex_result = run_codex_exec(prompt)
    if codex_result.get("ok"):
        comment = str(codex_result.get("stdout", "") or "").strip()
        if comment:
            return comment, codex_result
    return fallback_report_comment(report_type, stats), codex_result


def build_report_blocks(
    schedule_id: str,
    user_id: str,
    report_type: str,
    period_start: date,
    period_end: date,
    stats: dict[str, float | int],
    llm_comment: str,
) -> list[dict[str, Any]]:
    """Build Slack blocks for report post."""
    commitment_rows = _normalize_commitment_rows(stats)
    summary_text = (
        f"成功 {int(stats.get('success_count', 0))} / "
        f"失敗 {int(stats.get('failure_count', 0))} / "
        f"成功率 {float(stats.get('success_rate', 0.0)):.1f}%"
    )
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<@{user_id}>",
            },
        },
        *report_post(
            schedule_id=schedule_id,
            report_type=report_type,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            summary_text=summary_text,
            commitment_stats=commitment_rows,
            llm_comment=llm_comment,
        ),
    ]


def _extract_slack_post_ts(payload: dict[str, Any]) -> str:
    """Extract ts from chat.postMessage response payload."""
    if not isinstance(payload, dict):
        return ""

    top_level_ts = payload.get("ts")
    if isinstance(top_level_ts, str) and top_level_ts.strip():
        return top_level_ts.strip()

    message = payload.get("message")
    if isinstance(message, dict):
        message_ts = message.get("ts")
        if isinstance(message_ts, str) and message_ts.strip():
            return message_ts.strip()

    return ""


def _ensure_delivery_schedule(session, schedule: Schedule) -> Schedule:
    """Ensure report delivery uses a schedule_id that has no existing delivery row."""
    existing = (
        session.query(ReportDelivery.id)
        .filter(
            ReportDelivery.schedule_id == str(schedule.id),
        )
        .first()
    )
    if not existing:
        return schedule

    replacement = Schedule(
        user_id=str(schedule.user_id),
        event_type=EventType.REPORT,
        run_at=schedule.run_at,
        state=ScheduleState.PROCESSING,
        thread_ts=None,
        input_value=schedule.input_value,
        comment=schedule.comment,
        yes_comment=schedule.yes_comment,
        no_comment=schedule.no_comment,
        retry_count=int(schedule.retry_count or 0),
    )
    session.add(replacement)
    schedule.state = ScheduleState.DONE
    session.flush()
    print(
        "report schedule reused; allocated replacement schedule: "
        f"original={schedule.id} replacement={replacement.id}"
    )
    return replacement


def main() -> None:
    """reportイベントメイン処理"""
    schedule_id = os.getenv("SCHEDULE_ID", "").strip()
    if not schedule_id:
        print("Error: SCHEDULE_ID environment variable not set")
        sys.exit(1)

    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///oni.db"))
    session_factory = sessionmaker(bind=engine)

    session = session_factory()
    try:
        schedule = session.query(Schedule).filter(Schedule.id == schedule_id).first()
        if not schedule:
            print(f"Error: Schedule {schedule_id} not found")
            sys.exit(1)
        if schedule.event_type != EventType.REPORT:
            print(f"Error: Schedule {schedule_id} is not report event")
            sys.exit(1)
        if schedule.state != ScheduleState.PROCESSING:
            print(f"Error: Schedule {schedule_id} is not processing state")
            sys.exit(1)

        run_date = (
            schedule.run_at.date()
            if isinstance(schedule.run_at, datetime)
            else datetime.now().date()
        )
        user_id = str(schedule.user_id)
        report_type = decide_report_type(session, user_id, run_date)
        period_start, period_end = resolve_report_period(session, user_id, run_date, report_type)
        existing_period = (
            session.query(ReportDelivery.id, ReportDelivery.schedule_id)
            .filter(
                ReportDelivery.user_id == user_id,
                ReportDelivery.report_type == report_type,
                ReportDelivery.period_start == period_start,
                ReportDelivery.period_end == period_end,
                ReportDelivery.posted_at.isnot(None),
            )
            .first()
        )
        if existing_period:
            schedule.state = ScheduleState.DONE
            session.commit()
            print(
                "report skipped (already delivered): "
                f"schedule_id={schedule.id} type={report_type} "
                f"period={period_start.isoformat()}..{period_end.isoformat()} "
                f"existing_schedule_id={existing_period[1]}"
            )
            return

        delivery_schedule = _ensure_delivery_schedule(session, schedule)
        stats = aggregate_report_stats(session, user_id, period_start, period_end)
        markdown_table = format_report_summary_text(stats)
        payload = build_comment_payload(report_type, period_start, period_end, stats)
        charactor = load_coach_charactor(session, user_id)
        llm_comment, codex_result = generate_report_comment(
            payload=payload,
            report_type=report_type,
            stats=stats,
            charactor=charactor,
        )

        channel = slack.require_channel()
        token = slack.require_bot_token()
        blocks = build_report_blocks(
            schedule_id=str(delivery_schedule.id),
            user_id=user_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            stats=stats,
            llm_comment=llm_comment,
        )
        report_label = "月次レポート" if report_type == "monthly" else "週次レポート"
        response = slack.post_message(
            blocks=blocks,
            channel=channel,
            token=token,
            text=f"{report_label} ({period_start.isoformat()} ~ {period_end.isoformat()})",
            user_id=user_id,
            reason=f"report: {report_type}",
        )
        response_payload = response.json()
        thread_ts = _extract_slack_post_ts(response_payload)
        if not thread_ts:
            raise RuntimeError(
                "chat.postMessage succeeded but ts was missing: "
                f"keys={sorted(response_payload.keys()) if isinstance(response_payload, dict) else 'n/a'}"
            )

        delivery_schedule.thread_ts = thread_ts
        session.add(
            ReportDelivery(
                schedule_id=str(delivery_schedule.id),
                user_id=user_id,
                report_type=report_type,
                period_start=period_start,
                period_end=period_end,
                posted_at=datetime.now(),
                thread_ts=thread_ts,
                markdown_table=markdown_table,
                llm_comment=llm_comment,
            )
        )
        session.commit()

        print(
            "report completed: "
            f"schedule_id={schedule_id} "
            f"delivery_schedule_id={delivery_schedule.id} "
            f"type={report_type} "
            f"period={period_start.isoformat()}..{period_end.isoformat()} "
            f"success={int(stats['success_count'])} "
            f"failure={int(stats['failure_count'])} "
            f"rate={float(stats['success_rate']):.1f} "
            f"codex_ok={bool(codex_result.get('ok'))} "
            f"thread_ts={thread_ts}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
