import json
from datetime import datetime

from db import models
import scripts.behavior_log as behavior_log


def test_behavior_log_write(db_session, monkeypatch, capsys):
    monkeypatch.setattr(behavior_log, "parse_pavlok_log", lambda raw: {"ok": True})

    behavior_log.main(argv=["write", "good", "--coach-comment", "well done"])

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert "id" in payload

    saved = db_session.query(models.BehaviorLog).first()
    assert saved is not None
    assert saved.behavior == "good"


def test_behavior_log_read(db_session, monkeypatch, capsys):
    yesterday = datetime(2026, 1, 10, 12, 0)

    log = models.BehaviorLog(
        behavior="bad",
        related_date=yesterday.date(),
        pavlok_log={"ok": True},
        coach_comment="note",
        created_at=yesterday,
    )
    db_session.add(log)
    db_session.commit()

    monkeypatch.setattr(behavior_log, "now_jst", lambda: datetime(2026, 1, 11, 9, 0))

    behavior_log.main(argv=["read", "2"])

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert len(payload) == 1
    assert payload[0]["behavior"] == "bad"
