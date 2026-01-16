import json

from db import models
import scripts.repentance as repentance


def test_repentance_executes_and_updates(db_session, monkeypatch, capsys):
    punishment = models.DailyPunishment(
        date=models.now_jst().date(),
        ignore_count=2,
        punishment_count=2,
        executed_count=0,
        state="pending",
    )
    db_session.add(punishment)
    db_session.commit()

    calls = []

    def fake_call(stimulus_type, stimulus_value, reason):
        calls.append((stimulus_type, stimulus_value, reason))
        return {"ok": True}

    monkeypatch.setattr(repentance.pavlok, "call", fake_call)
    monkeypatch.setenv("PAVLOK_TYPE_PUNISH", "zap")
    monkeypatch.setenv("PAVLOK_VALUE_PUNISH", "50")
    monkeypatch.setenv("PUNISH_INTERVAL_SEC", "0")

    repentance.main(argv=[])

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["executed"] == 2
    assert len(calls) == 2

    db_session.expire_all()
    refreshed = db_session.get(models.DailyPunishment, punishment.id)
    assert refreshed.state == "done"
    assert refreshed.executed_count == 2


def test_repentance_limit_failure(db_session, monkeypatch, capsys):
    punishment = models.DailyPunishment(
        date=models.now_jst().date(),
        ignore_count=1,
        punishment_count=1,
        executed_count=0,
        state="pending",
    )
    db_session.add(punishment)
    db_session.commit()

    def fake_call(stimulus_type, stimulus_value, reason):
        return {"skipped": True, "reason": "limit_reached"}

    monkeypatch.setattr(repentance.pavlok, "call", fake_call)
    monkeypatch.setenv("PAVLOK_TYPE_PUNISH", "zap")
    monkeypatch.setenv("PAVLOK_VALUE_PUNISH", "50")
    monkeypatch.setenv("PUNISH_INTERVAL_SEC", "0")

    repentance.main(argv=[])

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["executed"] == 0

    db_session.expire_all()
    refreshed = db_session.get(models.DailyPunishment, punishment.id)
    assert refreshed.state == "failed"
    assert refreshed.executed_count == 0
