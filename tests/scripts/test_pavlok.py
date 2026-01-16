import json

from db import models
import scripts.pavlok as pavlok


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)
        self.status_code = 200

    def json(self):
        return self._payload



def test_pavlok_limits_and_clamp(db_session, monkeypatch):
    monkeypatch.setenv("PAVLOK_API_KEY", "dummy")
    monkeypatch.setenv("LIMIT_DAY_PAVLOK_COUNTS", "2")
    monkeypatch.setenv("LIMIT_PAVLOK_ZAP_VALUE", "50")

    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return DummyResponse({"ok": True})

    monkeypatch.setattr(pavlok.requests, "post", fake_post)

    result1 = pavlok.call("zap", 80, "reason")
    result2 = pavlok.call("zap", 80, "reason")
    result3 = pavlok.call("zap", 80, "reason")

    assert result1.get("ok") is True
    assert result2.get("ok") is True
    assert result3.get("skipped") is True
    assert result3.get("reason") == "limit_reached"
    assert len(calls) == 2
    assert calls[0]["json"]["stimulus"]["stimulusValue"] == 50

    count = db_session.query(models.PavlokCount).first()
    assert count is not None
    assert count.zap_count == 3
