import json

from db import models
import scripts.add_schedules as add_schedules


def test_add_schedules_inserts(db_session, monkeypatch, capsys):
    records = [
        {
            "prompt_name": "remind_ask",
            "input_value": "{}",
            "scheduled_date": "2026-01-11 10:00",
        }
    ]
    monkeypatch.setattr(add_schedules, "load_records", lambda raw: records)

    add_schedules.main(argv=["-"])

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["inserted"] == 1

    saved = db_session.query(models.Schedule).first()
    assert saved is not None
    assert saved.prompt_name == "remind_ask"
    assert saved.state == "pending"
