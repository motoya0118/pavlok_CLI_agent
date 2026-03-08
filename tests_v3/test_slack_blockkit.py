"""
v0.3 BlockKit UI Tests

Tests for BlockKit JSON generation for Slack UI components.
Following TDD: Red -> Green -> Refactor
"""

from datetime import datetime


class TestBlockKitBaseCommit:
    """Test /base_commit modal UI"""

    def test_base_commit_modal_structure(self):
        """Base commit modal should have correct structure"""
        from backend.slack_ui import base_commit_modal

        commitments = [
            {"id": "1", "time": "07:00", "task": "朝の瞑想"},
            {"id": "2", "time": "09:00", "task": "メールチェック"},
            {"id": "3", "time": "22:00", "task": "振り返り"},
        ]

        modal = base_commit_modal(commitments)

        assert modal["type"] == "modal"
        assert modal["callback_id"] == "base_commit_submit"
        assert "📋" in modal["title"]["text"]
        assert modal["submit"]["text"] == "送信"

        # Should have at least 3 commitment rows
        blocks = modal["blocks"]
        assert len(blocks) >= 3 * 3 + 3  # 3 commitments * 3 blocks + header/divider/footer

    def test_base_commit_modal_with_empty_commitments(self):
        """Modal should show minimum 3 rows even with no commitments"""
        from backend.slack_ui import base_commit_modal

        modal = base_commit_modal([])

        blocks = modal["blocks"]
        # Should still have input blocks for 3 commitments
        task_blocks = [b for b in blocks if b.get("block_id", "").startswith("commitment_")]
        assert len(task_blocks) == 3

    def test_base_commit_modal_action_ids(self):
        """Modal should have correct action_ids"""
        from backend.slack_ui import base_commit_modal

        modal = base_commit_modal([])

        # Check add/remove row buttons
        actions_blocks = [b for b in modal["blocks"] if b.get("type") == "actions"]
        add_button = None
        remove_button = None
        for block in actions_blocks:
            for elem in block.get("elements", []):
                if elem.get("action_id") == "commitment_add_row":
                    add_button = elem
                if elem.get("action_id") == "commitment_remove_row":
                    remove_button = elem

        assert add_button is not None
        assert add_button["text"]["text"] == "+ 追加"
        assert add_button["style"] == "primary"
        assert remove_button is not None
        assert remove_button["text"]["text"] == "- 削除"
        assert remove_button["style"] == "danger"

    def test_base_commit_modal_task_inputs_are_optional(self):
        """Task inputs should be optional so blank added rows don't fail validation."""
        from backend.slack_ui import base_commit_modal

        modal = base_commit_modal([])
        task_blocks = [
            b for b in modal["blocks"] if b.get("block_id", "").startswith("commitment_")
        ]
        assert len(task_blocks) >= 3
        for block in task_blocks:
            assert block.get("optional") is True


class TestBlockKitStopRestart:
    """Test /stop and /restart notification UI"""

    def test_stop_notification_ephemeral(self):
        """Stop notification should be ephemeral"""
        from backend.slack_ui import stop_notification

        blocks = stop_notification()

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "section"
        assert "⏸️" in blocks[0]["text"]["text"]
        assert "鬼コーチを停止しました" in blocks[0]["text"]["text"]
        assert "/restart" in blocks[0]["text"]["text"]

    def test_restart_notification_ephemeral(self):
        """Restart notification should be ephemeral"""
        from backend.slack_ui import restart_notification

        blocks = restart_notification()

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "section"
        assert "▶️" in blocks[0]["text"]["text"]
        assert "鬼コーチを再開しました" in blocks[0]["text"]["text"]

    def test_help_notification_ephemeral(self):
        """Help notification should include guidance and safety note."""
        from backend.slack_ui import help_notification

        blocks = help_notification()

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "/help" in blocks[0]["text"]["text"]

        text_blob = "\n".join(
            b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
        )
        assert "/base_commit" in text_blob
        assert "/plan" in text_blob
        assert "/config" in text_blob
        assert "/stop" in text_blob
        assert "/restart" in text_blob
        assert "安全上の注意" in text_blob


class TestBlockKitConfig:
    """Test /config modal UI"""

    def test_config_modal_structure(self):
        """Config modal should have all sections"""
        from backend.slack_ui import config_modal

        config_values = {
            "PAVLOK_TYPE_PUNISH": "zap",
            "PAVLOK_VALUE_PUNISH": "50",
            "PAVLOK_TYPE_NOTION": "vibe",
            "PAVLOK_VALUE_NOTION": "35",
            "LIMIT_DAY_PAVLOK_COUNTS": "100",
            "LIMIT_PAVLOK_ZAP_VALUE": "100",
            "IGNORE_INTERVAL": "900",
            "IGNORE_JUDGE_TIME": "3",
            "IGNORE_MAX_RETRY": "5",
        }

        modal = config_modal(config_values)

        assert modal["type"] == "modal"
        assert modal["callback_id"] == "config_submit"
        assert "⚙️" in modal["title"]["text"]

        # Should have section headers for 罰, Ignore, Coach
        headers = [b for b in modal["blocks"] if b.get("type") == "header"]
        assert len(headers) >= 3

        coach_block = next(
            (b for b in modal["blocks"] if b.get("block_id") == "COACH_CHARACTOR"),
            None,
        )
        assert coach_block is not None
        assert not any(
            b.get("block_id") in {"TIMEOUT_REMIND", "TIMEOUT_REVIEW", "RETRY_DELAY"}
            for b in modal["blocks"]
        )

    def test_config_modal_punishment_values(self):
        """Punishment config should have correct initial values"""
        from backend.slack_ui import config_modal

        config_values = {
            "PAVLOK_TYPE_PUNISH": "vibe",
            "PAVLOK_VALUE_PUNISH": "70",
            "PAVLOK_TYPE_NOTION": "beep",
            "PAVLOK_VALUE_NOTION": "80",
        }

        modal = config_modal(config_values)
        blocks = modal["blocks"]

        # Find PAVLOK_TYPE_PUNISH block
        type_block = next((b for b in blocks if b.get("block_id") == "PAVLOK_TYPE_PUNISH"), None)
        assert type_block is not None
        # Should have initial_option with vibe selected
        element = type_block["element"]
        assert element["action_id"] == "PAVLOK_TYPE_PUNISH_select"

        # Find PAVLOK_VALUE_PUNISH block
        value_block = next((b for b in blocks if b.get("block_id") == "PAVLOK_VALUE_PUNISH"), None)
        assert value_block is not None
        assert value_block["element"]["initial_value"] == "70"

        notion_type_block = next(
            (b for b in blocks if b.get("block_id") == "PAVLOK_TYPE_NOTION"), None
        )
        assert notion_type_block is not None
        assert notion_type_block["element"]["action_id"] == "PAVLOK_TYPE_NOTION_select"
        assert notion_type_block["element"]["initial_option"]["value"] == "beep"

        notion_value_block = next(
            (b for b in blocks if b.get("block_id") == "PAVLOK_VALUE_NOTION"), None
        )
        assert notion_value_block is not None
        assert notion_value_block["element"]["initial_value"] == "80"

    def test_config_modal_orders_limits_before_notification(self):
        """Max count/value should be grouped before notification settings."""
        from backend.slack_ui import config_modal

        modal = config_modal({})
        block_ids = [b.get("block_id") for b in modal["blocks"] if b.get("block_id")]

        assert block_ids.index("PAVLOK_TYPE_PUNISH") < block_ids.index("PAVLOK_VALUE_PUNISH")
        assert block_ids.index("PAVLOK_VALUE_PUNISH") < block_ids.index("LIMIT_DAY_PAVLOK_COUNTS")
        assert block_ids.index("LIMIT_DAY_PAVLOK_COUNTS") < block_ids.index(
            "LIMIT_PAVLOK_ZAP_VALUE"
        )
        assert block_ids.index("LIMIT_PAVLOK_ZAP_VALUE") < block_ids.index("PAVLOK_TYPE_NOTION")
        assert block_ids.index("PAVLOK_TYPE_NOTION") < block_ids.index("PAVLOK_VALUE_NOTION")

    def test_config_modal_reset_and_history_buttons(self):
        """Config modal should have reset and history buttons"""
        from backend.slack_ui import config_modal

        modal = config_modal({})
        value_block = next(
            (b for b in modal["blocks"] if b.get("block_id") == "PAVLOK_VALUE_PUNISH"),
            None,
        )
        assert value_block is not None
        assert value_block["element"]["initial_value"] == "35"
        notion_value_block = next(
            (b for b in modal["blocks"] if b.get("block_id") == "PAVLOK_VALUE_NOTION"),
            None,
        )
        assert notion_value_block is not None
        assert notion_value_block["element"]["initial_value"] == "35"

        actions_blocks = [b for b in modal["blocks"] if b.get("type") == "actions"]
        assert len(actions_blocks) >= 1

        actions = actions_blocks[0]["elements"]
        reset_btn = next((e for e in actions if e.get("action_id") == "config_reset_all"), None)
        history_btn = next((e for e in actions if e.get("action_id") == "config_history"), None)

        assert reset_btn is not None
        assert reset_btn["style"] == "danger"
        assert history_btn is not None


class TestBlockKitAudit:
    """Test /audit display UI"""

    def test_audit_log_display(self):
        """Audit log should display recent changes"""
        from backend.slack_ui import audit_log_display

        audit_logs = [
            {
                "changed_at": datetime(2026, 2, 13, 20, 30),
                "config_key": "PAVLOK_VALUE_PUNISH",
                "old_value": "50",
                "new_value": "70",
                "changed_by": "U03JBULT484",
            },
            {
                "changed_at": datetime(2026, 2, 12, 15, 0),
                "config_key": "IGNORE_INTERVAL",
                "old_value": "900",
                "new_value": "600",
                "changed_by": "U03JBULT484",
            },
        ]

        blocks = audit_log_display(audit_logs)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "📋" in blocks[0]["text"]["text"]
        assert "設定変更履歴" in blocks[0]["text"]["text"]

        # Should have section blocks for each log
        sections = [b for b in blocks if b.get("type") == "section"]
        assert len(sections) >= len(audit_logs)


class TestBlockKitPlan:
    """Test plan event UI"""

    def test_plan_start_notification(self):
        """Plan start notification should trigger modal"""
        from backend.slack_ui import plan_start_notification

        schedule_id = "123"
        user_id = "U03JBULT484"
        ignore_interval_minutes = 10
        blocks = plan_start_notification(
            schedule_id,
            user_id=user_id,
            ignore_interval_minutes=ignore_interval_minutes,
        )

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "📅" in blocks[0]["text"]["text"]

        mention_sections = [
            b
            for b in blocks
            if b.get("type") == "section" and b.get("text", {}).get("text") == f"<@{user_id}>"
        ]
        assert len(mention_sections) == 1

        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        assert f"{ignore_interval_minutes}分後" in context_blocks[0]["elements"][0]["text"]

        # Should have button to open modal
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) >= 1
        button = actions[0]["elements"][0]
        assert button["action_id"] == "plan_open_modal"
        assert schedule_id in button.get("value", "")

    def test_plan_input_modal(self):
        """Plan input modal should have task inputs"""
        from backend.slack_ui import plan_input_modal

        commitments = [
            {"id": "1", "time": "07:00", "task": "朝の瞑想"},
            {"id": "2", "time": "09:00", "task": "メールチェック"},
        ]

        modal = plan_input_modal(commitments)

        assert modal["type"] == "modal"
        assert modal["callback_id"] == "plan_submit"
        assert "📅" in modal["title"]["text"]

        # Should have input blocks for each commitment
        blocks = modal["blocks"]
        task_sections = [b for b in blocks if b.get("type") == "section"]
        # Should have at least the commitments + next_plan section
        assert len(task_sections) >= len(commitments)

    def test_plan_input_modal_with_report_fields(self):
        """Plan modal should reuse date/time UI for report input when enabled."""
        from backend.slack_ui import plan_input_modal

        commitments = [{"id": "1", "time": "07:00", "task": "朝の瞑想"}]
        modal = plan_input_modal(
            commitments,
            report_input={"show": True, "date": "tomorrow", "time": "06:30"},
        )

        blocks = modal["blocks"]
        report_date = next((b for b in blocks if b.get("block_id") == "report_date"), None)
        report_time = next((b for b in blocks if b.get("block_id") == "report_time"), None)

        assert report_date is not None
        assert report_time is not None
        assert report_date["element"]["initial_option"]["value"] == "tomorrow"
        assert [opt["value"] for opt in report_date["element"]["options"]] == ["today", "tomorrow"]
        assert report_time["element"]["initial_time"] == "06:30"

    def test_plan_complete_notification(self):
        """Plan complete notification should show scheduled tasks"""
        from backend.slack_ui import plan_complete_notification

        scheduled_tasks = [
            {"task": "朝の瞑想", "time": "07:00", "date": "今日"},
            {"task": "メールチェック", "time": "09:00", "date": "今日"},
        ]
        next_plan = {"date": "明日", "time": "07:00"}

        blocks = plan_complete_notification(scheduled_tasks, next_plan)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "登録しました" in blocks[0]["text"]["text"]

        # Should have section with task list
        sections = [b for b in blocks if b.get("type") == "section"]
        assert len(sections) >= 1
        assert all("レポート予定" not in str(s.get("text", {}).get("text", "")) for s in sections)

    def test_plan_complete_notification_includes_report_when_present(self):
        """Plan complete notification should show report schedule when provided."""
        from backend.slack_ui import plan_complete_notification

        scheduled_tasks = [
            {"task": "朝の瞑想", "time": "07:00", "date": "今日"},
        ]
        next_plan = {"date": "明日", "time": "07:00"}
        report_plan = {"date": "明日", "time": "08:45"}

        blocks = plan_complete_notification(
            scheduled_tasks,
            next_plan,
            report_plan=report_plan,
        )

        report_sections = [
            b
            for b in blocks
            if b.get("type") == "section"
            and "レポート予定" in str(b.get("text", {}).get("text", ""))
        ]
        assert len(report_sections) == 1
        assert "明日 08:45" in report_sections[0]["text"]["text"]


class TestBlockKitCalorie:
    """Test /cal modal UI"""

    def test_calorie_input_modal_structure(self):
        from backend.slack_ui import calorie_input_modal

        modal = calorie_input_modal()
        assert modal["type"] == "modal"
        assert modal["callback_id"] == "calorie_submit"
        assert modal["submit"]["text"] == "解析開始"

        blocks = modal["blocks"]
        image_input = next((b for b in blocks if b.get("block_id") == "calorie_image"), None)
        assert image_input is not None
        assert image_input["element"]["type"] == "file_input"
        assert image_input["element"]["max_files"] == 1
        assert "jpg" in image_input["element"]["filetypes"]


class TestBlockKitReport:
    """Test report event UI"""

    def test_report_post_has_read_button(self):
        from backend.slack_ui import report_post

        blocks = report_post(
            schedule_id="S_REPORT",
            report_type="weekly",
            period_start="2026-03-01",
            period_end="2026-03-07",
            summary_text="成功 1 / 失敗 0 / 成功率 100.0%",
            commitment_stats=[
                {
                    "task": "運動する",
                    "success_count": 1,
                    "failure_count": 0,
                    "success_rate": 100.0,
                }
            ],
            llm_comment="コメント",
        )

        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        button = actions[0]["elements"][0]
        assert button["action_id"] == "report_read"
        assert "S_REPORT" in button["value"]
        table_sections = [b for b in blocks if b.get("type") == "section"]
        assert len(table_sections) >= 3
        assert "集計サマリー" in table_sections[1]["text"]["text"]
        assert "運動する" in table_sections[2]["text"]["text"]
        assert any("コーチコメント" in s["text"]["text"] for s in table_sections)
        assert all(isinstance(s["text"]["text"], str) for s in table_sections)

    def test_report_read_response_varies_by_type(self):
        from backend.slack_ui import report_read_response

        weekly = report_read_response("weekly")
        monthly = report_read_response("monthly")
        assert "来週も頑張りましょう" in weekly[0]["text"]["text"]
        assert "来月も頑張りましょう" in monthly[0]["text"]["text"]


class TestBlockKitRemind:
    """Test remind event UI"""

    def test_remind_post_blocks(self):
        """Remind post should have YES/NO buttons"""
        from backend.slack_ui import remind_post

        schedule_id = "123"
        task_name = "朝の瞑想"
        task_time = "07:00"
        description = "静かな場所で5分間、呼吸に集中しましょう。\n準備はできましたか？"
        ignore_interval_minutes = 10

        blocks = remind_post(
            schedule_id,
            task_name,
            task_time,
            description,
            ignore_interval_minutes=ignore_interval_minutes,
        )

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "🔔" in blocks[0]["text"]["text"]

        # Should have YES/NO buttons
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) >= 1
        buttons = actions[0]["elements"]
        assert len(buttons) == 2

        yes_btn = next((b for b in buttons if b.get("action_id") == "remind_yes"), None)
        no_btn = next((b for b in buttons if b.get("action_id") == "remind_no"), None)

        assert yes_btn is not None
        assert yes_btn["style"] == "primary"
        assert no_btn is not None
        assert no_btn["style"] == "danger"
        assert schedule_id in yes_btn.get("value", "")
        assert schedule_id in no_btn.get("value", "")

        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        assert f"{ignore_interval_minutes}分ごと" in context_blocks[0]["elements"][0]["text"]

    def test_remind_yes_response(self):
        """YES response should show completion"""
        from backend.slack_ui import remind_yes_response

        task_name = "朝の瞑想"
        comment = "良い一日のスタートです！"

        blocks = remind_yes_response(task_name, comment)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "section"
        assert "✓" in blocks[0]["text"]["text"]
        assert task_name in blocks[0]["text"]["text"]

    def test_remind_no_response(self):
        """NO response should show punishment"""
        from backend.slack_ui import remind_no_response

        task_name = "朝の瞑想"
        no_count = 2
        punishment = {"type": "zap", "value": 45}
        comment = "明日こそは、一緒に頑張りましょう。"

        blocks = remind_no_response(task_name, no_count, punishment, comment)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "section"
        assert "✕" in blocks[0]["text"]["text"]
        assert task_name in blocks[0]["text"]["text"]
        assert str(no_count) in blocks[0]["text"]["text"]


class TestBlockKitIgnore:
    """Test ignore detection UI"""

    def test_ignore_detection_post(self):
        """Ignore detection post should have YES/NO buttons"""
        from backend.slack_ui import ignore_detection_post

        schedule_id = "123"
        task_name = "朝の瞑想"
        task_time = "07:00"
        ignore_minutes = 15
        punishment = {"type": "vibe", "value": 100}

        blocks = ignore_detection_post(
            schedule_id, task_name, task_time, ignore_minutes, punishment
        )

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "⚠️" in blocks[0]["text"]["text"] or "応答待ち" in blocks[0]["text"]["text"]

        # Should have YES/NO buttons
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) >= 1
        buttons = actions[0]["elements"]

        yes_btn = next((b for b in buttons if b.get("action_id") == "ignore_yes"), None)
        no_btn = next((b for b in buttons if b.get("action_id") == "ignore_no"), None)

        assert yes_btn is not None
        assert no_btn is not None

    def test_ignore_max_reached_post(self):
        """Max ignore reached should show cancellation"""
        from backend.slack_ui import ignore_max_reached_post

        task_name = "朝の瞑想"
        task_time = "07:00"
        final_punishment = {"type": "zap", "value": 100}

        blocks = ignore_max_reached_post(task_name, task_time, final_punishment)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "❌" in blocks[0]["text"]["text"] or "キャンセル" in blocks[0]["text"]["text"]


class TestBlockKitError:
    """Test error notification UI"""

    def test_error_notification(self):
        """Error notification should show error message"""
        from backend.slack_ui import error_notification

        error_message = "ValueError: 罰強度は0-100の範囲で指定してください"
        retry_action_id = "retry_config"

        blocks = error_notification(error_message, retry_action_id)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        assert "❌" in blocks[0]["text"]["text"] or "エラー" in blocks[0]["text"]["text"]

        # Should have retry button
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) >= 1
        retry_btn = actions[0]["elements"][0]
        assert retry_btn.get("action_id") == retry_action_id

    def test_daily_zap_limit_notification(self):
        """Daily ZAP limit notification should show warning"""
        from backend.slack_ui import daily_zap_limit_notification

        limit = 100

        blocks = daily_zap_limit_notification(limit)

        assert isinstance(blocks, list)
        assert blocks[0]["type"] == "header"
        # The limit value should appear somewhere in the blocks (might be in different block)
        all_text = str(blocks)
        assert str(limit) in all_text


class TestBlockKitHelpers:
    """Test helper functions"""

    def test_format_timestamp_jst(self):
        """Should format datetime to JST string"""
        from backend.slack_ui import format_timestamp_jst

        dt = datetime(2026, 2, 14, 7, 30)
        formatted = format_timestamp_jst(dt)

        assert "2026-02-14" in formatted
        assert "07:30" in formatted

    def test_punishment_display_text(self):
        """Should format punishment for display"""
        from backend.slack_ui import punishment_display_text

        punishment = {"type": "zap", "value": 50}
        text = punishment_display_text(punishment)

        assert "zap" in text.lower() or "⚡" in text
        assert "50" in text or "50%" in text
