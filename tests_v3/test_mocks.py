# v0.3 Mocks Test
import pytest


class TestMockSlackClient:
    def test_post_message_records_call(self, mock_slack_client):
        result = mock_slack_client.post_message(channel="C123456", text="test message")
        assert result["ok"] is True
        mock_slack_client.assert_called("post_message", times=1)

    def test_assert_not_called(self, mock_slack_client):
        mock_slack_client.assert_not_called("update_message")


class TestMockAgentClient:
    @pytest.mark.asyncio
    async def test_run_skill(self, mock_agent_client):
        result = await mock_agent_client.run_skill(skill="plan_update", prompt="test")
        assert result == "Generated response by agent"
