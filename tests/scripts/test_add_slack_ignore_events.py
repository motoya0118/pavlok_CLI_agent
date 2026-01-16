import json

import scripts.add_slack_ignore_events as add_ignore


def test_add_slack_ignore_events_increments(db_session, capsys, monkeypatch):
    monkeypatch.setenv("TIMEZONE", "JST")

    add_ignore.add_event("1700000000.0001")
    add_ignore.add_event("1700000000.0002")

    add_ignore.main(argv=["1700000000.0003"])

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["remaining_total"] == 3
