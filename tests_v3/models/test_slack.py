# v0.3 Slack BlockKit Tests (TDD)
import pytest
import json
from backend.slack_lib import BlockKitBuilder


class TestBlockKitBuilder:
    """Test BlockKit JSON generation for v0.3 Slack UI"""

    def test_plan_open_notification_blocks(self):
        """Test plan open notification blocks generation"""
        user_id = "U03JBULT484"
        ignore_interval_minutes = 10
        blocks = BlockKitBuilder.plan_open_notification(
            schedule_id="test-schedule-123",
            user_id=user_id,
            ignore_interval_minutes=ignore_interval_minutes,
        )

        assert isinstance(blocks, list)
        assert len(blocks) >= 3  # header, section, actions, context

        # Check header block
        header = blocks[0]
        assert header["type"] == "header"
        assert header["text"]["text"] == "📅 今日の予定を登録しましょう"

        mention_sections = [
            b for b in blocks
            if b.get("type") == "section"
            and b.get("text", {}).get("text") == f"<@{user_id}>"
        ]
        assert len(mention_sections) == 1

        # Check actions block with trigger button
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        assert actions[0]["block_id"] == "plan_trigger"
        button = actions[0]["elements"][0]
        assert button["action_id"] == "plan_open_modal"
        # Parse the JSON value to verify structure
        value_dict = json.loads(button["value"])
        assert value_dict["schedule_id"] == "test-schedule-123"

        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        assert f"{ignore_interval_minutes}分後" in context_blocks[0]["elements"][0]["text"]

    def test_remind_notification_blocks(self):
        """Test remind notification blocks with YES/NO buttons"""
        task_name = "朝の瞑想"
        task_time = "07:00"
        description = "静かな場所で5分間、呼吸に集中しましょう。準備はできましたか？"
        ignore_interval_minutes = 10

        blocks = BlockKitBuilder.remind_notification(
            schedule_id="test-schedule-456",
            task_name=task_name,
            task_time=task_time,
            description=description,
            ignore_interval_minutes=ignore_interval_minutes,
        )

        assert isinstance(blocks, list)

        # Check header
        header = blocks[0]
        assert header["type"] == "header"
        assert header["text"]["text"] == "🔔 リマインド"

        # Check task section
        task_section = [b for b in blocks if b.get("type") == "section"][0]
        assert task_name in task_section["text"]["text"]
        assert task_time in task_section["text"]["text"]
        assert description in task_section["text"]["text"]

        # Check actions block with YES/NO buttons
        actions = [b for b in blocks if b.get("type") == "actions"][0]
        assert actions["block_id"] == "remind_response"
        assert len(actions["elements"]) == 2

        # YES button
        yes_btn = actions["elements"][0]
        assert yes_btn["action_id"] == "remind_yes"
        assert yes_btn["style"] == "primary"
        assert '"schedule_id": "test-schedule-456"' in yes_btn["value"]
        assert '"event_type": "remind"' in yes_btn["value"]

        # NO button
        no_btn = actions["elements"][1]
        assert no_btn["action_id"] == "remind_no"
        assert no_btn["style"] == "danger"

        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        assert f"{ignore_interval_minutes}分ごと" in context_blocks[0]["elements"][0]["text"]

    def test_ignore_notification_blocks(self):
        """Test ignore notification blocks"""
        blocks = BlockKitBuilder.ignore_notification(
            schedule_id="test-schedule-789",
            task_name="朝の瞑想",
            task_time="07:00",
            ignore_time=15,
            ignore_count=1,
            stimulation_type="vibe",
            stimulation_value=100
        )

        assert isinstance(blocks, list)

        # Check header
        header = blocks[0]
        assert header["type"] == "header"
        assert "応答待ち" in header["text"]["text"]

        # Check actions block
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        assert actions[0]["block_id"] == "ignore_response"

        # Check buttons
        assert len(actions[0]["elements"]) == 2
        yes_btn = actions[0]["elements"][0]
        assert yes_btn["action_id"] == "ignore_yes"

    def test_base_commit_modal_blocks(self):
        """Test base_commit modal blocks generation"""
        commitments = [
            {"id": "c1", "time": "07:00", "task": "朝の瞑想"},
            {"id": "c2", "time": "09:00", "task": "メールチェック"},
            {"id": "c3", "time": "22:00", "task": "振り返り"},
        ]

        modal = BlockKitBuilder.base_commit_modal(commitments=commitments)

        assert modal["type"] == "modal"
        assert modal["callback_id"] == "base_commit_submit"
        assert modal["title"]["text"] == "📋 コミットメント管理"

        blocks = modal["blocks"]
        assert isinstance(blocks, list)

        # Check for input blocks (minimum 3)
        input_blocks = [b for b in blocks if b.get("type") == "input"]
        assert len(input_blocks) >= 3

    def test_config_modal_blocks(self):
        """Test config modal blocks generation"""
        config_values = {
            "PAVLOK_TYPE_PUNISH": "zap",
            "PAVLOK_VALUE_PUNISH": "50",
            "PAVLOK_TYPE_NOTION": "vibe",
            "PAVLOK_VALUE_NOTION": "35",
            "IGNORE_INTERVAL": "900",
            "COACH_CHARACTOR": "ラムちゃん",
        }

        modal = BlockKitBuilder.config_modal(config_values=config_values)

        assert modal["type"] == "modal"
        assert modal["callback_id"] == "config_submit"
        assert "⚙️ Oni System 設定" in modal["title"]["text"]

        blocks = modal["blocks"]
        assert isinstance(blocks, list)

        # Check for input blocks with config keys
        input_blocks = [b for b in blocks if b.get("type") == "input"]
        assert len(input_blocks) > 0

        coach_block = next(
            (b for b in blocks if b.get("block_id") == "COACH_CHARACTOR"),
            None,
        )
        assert coach_block is not None
        assert coach_block["element"]["initial_value"] == "ラムちゃん"
        notion_block = next(
            (b for b in blocks if b.get("block_id") == "PAVLOK_TYPE_NOTION"),
            None,
        )
        assert notion_block is not None

    def test_stop_notification_ephemeral(self):
        """Test stop command ephemeral notification"""
        blocks = BlockKitBuilder.stop_notification()

        assert isinstance(blocks, list)
        assert len(blocks) >= 1

        section = blocks[0]
        assert section["type"] == "section"
        assert "鬼コーチを停止" in section["text"]["text"]
        assert "/restart" in section["text"]["text"]

    def test_restart_notification_ephemeral(self):
        """Test restart command ephemeral notification"""
        blocks = BlockKitBuilder.restart_notification()

        assert isinstance(blocks, list)
        assert len(blocks) >= 2  # section + context

        section = blocks[0]
        assert section["type"] == "section"
        assert "鬼コーチを再開" in section["text"]["text"]

    def test_yes_response_blocks(self):
        """Test YES response blocks after remind"""
        blocks = BlockKitBuilder.yes_response(
            task_name="朝の瞑想",
            comment="静かな心は最高の準備です。"
        )

        assert isinstance(blocks, list)
        assert len(blocks) >= 1

        section = blocks[0]
        assert section["type"] == "section"
        assert "朝の瞑想" in section["text"]["text"]
        assert "完了しました" in section["text"]["text"]
        assert "静かな心は最高の準備です" in section["text"]["text"]

    def test_no_response_blocks(self):
        """Test NO response blocks after remind"""
        blocks = BlockKitBuilder.no_response(
            task_name="朝の瞑想",
            no_count=2,
            punishment_mode="zap",
            punishment_value=45,
            comment="明日こそは、一緒に頑張りましょう。"
        )

        assert isinstance(blocks, list)
        assert len(blocks) >= 2  # section + context

        section = blocks[0]
        assert section["type"] == "section"
        assert "朝の瞑想" in section["text"]["text"]
        assert "できませんでした" in section["text"]["text"]
        assert "NO回数: 2回" in section["text"]["text"]
        assert "zap 45%" in section["text"]["text"]

        # Check context block with Pavlok notification
        context = [b for b in blocks if b.get("type") == "context"]
        assert len(context) == 1
        assert "Pavlokから刺激を送信しました" in context[0]["elements"][0]["text"]

    def test_plan_submit_confirmation_blocks(self):
        """Test plan submit confirmation blocks"""
        scheduled_tasks = [
            {"task": "朝の瞑想", "date": "today", "time": "07:00"},
            {"task": "メールチェック", "date": "today", "time": "09:00"},
            {"task": "振り返り", "date": "today", "time": "22:00"},
        ]
        next_plan = {"date": "tomorrow", "time": "07:00"}

        blocks = BlockKitBuilder.plan_submit_confirmation(
            scheduled_tasks=scheduled_tasks,
            next_plan=next_plan
        )

        assert isinstance(blocks, list)

        # Check header
        header = blocks[0]
        assert header["type"] == "header"
        assert "本日の予定を登録しました" in header["text"]["text"]

        # Check section with task list (second section after header)
        sections = [b for b in blocks if b.get("type") == "section"]
        assert len(sections) == 2  # task list section + next plan section

        task_section = sections[0]
        assert "朝の瞑想" in task_section["text"]["text"]
        assert "メールチェック" in task_section["text"]["text"]
        assert "振り返り" in task_section["text"]["text"]

        next_plan_section = sections[1]
        assert "次回計画" in next_plan_section["text"]["text"]

    def test_auto_canceled_notification_blocks(self):
        """Test auto canceled notification when max ignore reached"""
        blocks = BlockKitBuilder.auto_canceled_notification(
            task_name="朝の瞑想",
            task_time="07:00",
            final_punishment_mode="zap",
            final_punishment_value=100
        )

        assert isinstance(blocks, list)

        header = blocks[0]
        assert header["type"] == "header"
        assert "自動キャンセル" in header["text"]["text"]

        section = [b for b in blocks if b.get("type") == "section"][0]
        assert "長時間無視が続いたため" in section["text"]["text"]
        assert "自動的にキャンセル" in section["text"]["text"]
        assert "zap 100%" in section["text"]["text"]

    def test_error_notification_blocks(self):
        """Test error notification blocks"""
        blocks = BlockKitBuilder.error_notification(error_message="設定の保存中にエラーが発生しました。")

        assert isinstance(blocks, list)
        assert len(blocks) >= 2  # header + section + actions

        header = blocks[0]
        assert header["type"] == "header"
        assert "エラーが発生しました" in header["text"]["text"]

    def test_daily_limit_reached_blocks(self):
        """Test daily ZAP limit reached notification"""
        blocks = BlockKitBuilder.daily_limit_reached(limit_count=100)

        assert isinstance(blocks, list)
        assert len(blocks) >= 2  # header + section

        header = blocks[0]
        assert header["type"] == "header"
        assert "罰上限に到達" in header["text"]["text"]

        section = [b for b in blocks if b.get("type") == "section"][0]
        assert "100回" in section["text"]["text"]
        assert "安全のため" in section["text"]["text"]
