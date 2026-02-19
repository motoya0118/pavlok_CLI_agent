from scripts import slack as slack_script


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"ok": True, "message": {"ts": "123.456"}}


def test_post_message_triggers_notification_stimulus(monkeypatch):
    calls = {"stimulus_user_id": "", "post_called": False}

    def _fake_post(url, headers, json, timeout):
        calls["post_called"] = True
        return _FakeResponse()

    def _fake_stimulus(user_id: str):
        calls["stimulus_user_id"] = user_id
        return {"success": True, "type": "vibe", "value": 100}

    monkeypatch.setattr("scripts.slack.requests.post", _fake_post)
    monkeypatch.setattr(
        "backend.pavlok_lib.stimulate_notification_for_user",
        _fake_stimulus,
    )

    slack_script.post_message(
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}],
        channel="C_TEST",
        token="xoxb-test",
        user_id="U_TEST",
    )

    assert calls["post_called"] is True
    assert calls["stimulus_user_id"] == "U_TEST"


def test_post_message_skips_notification_stimulus_without_user_id(monkeypatch):
    calls = {"stimulus_called": False}

    def _fake_post(url, headers, json, timeout):
        return _FakeResponse()

    def _fake_stimulus(user_id: str):
        calls["stimulus_called"] = True
        return {"success": True, "type": "vibe", "value": 100}

    monkeypatch.setattr("scripts.slack.requests.post", _fake_post)
    monkeypatch.setattr(
        "backend.pavlok_lib.stimulate_notification_for_user",
        _fake_stimulus,
    )

    slack_script.post_message(
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}],
        channel="C_TEST",
        token="xoxb-test",
    )

    assert calls["stimulus_called"] is False
