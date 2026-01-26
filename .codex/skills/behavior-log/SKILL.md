---
name: behavior-log
description: Insert or read behavior log rows in the local database (behavior_logs). Use when recording a good/bad behavior entry, attaching a Pavlok API response JSON, adding a coach comment, or fetching recent logs via scripts/behavior_log.py.
---

# Behavior Log

Use `scripts/behavior_log.py` to insert one record into `behavior_logs` or read recent logs.

## Run

```bash
uv run scripts/behavior_log.py write good --coach-comment "Kept focus"
```

```bash
uv run scripts/behavior_log.py write bad --pavlok-log '{"stimulusType":"zap","stimulusValue":30}'
```

```bash
echo '{"stimulusType":"beep","stimulusValue":100}' | uv run scripts/behavior_log.py write bad --pavlok-log -
```

```bash
uv run scripts/behavior_log.py write good --related-date 2026-01-26
```

```bash
uv run scripts/behavior_log.py read 2
```

## Inputs

- `write` mode: `behavior` must be `good` or `bad`.
- `write` mode: `--related-date` accepts `YYYY-MM-DD` or `YYYYMMDD`.
- `write` mode: `--pavlok-log` expects a JSON object string; use `-` to read from stdin.
- `write` mode: `--coach-comment` is optional free text.
- `read` mode: `days` is a positive integer (1 = today, 2 = today + yesterday).

## Outputs

Write mode prints a single line of JSON:

```
{"id": 10}
```

Read mode prints a JSON array:

```
[{"id": 10, "behavior": "good", "related_date": "2026-01-26", "pavlok_log": null, "coach_comment": null, "created_at": "2026-01-26T09:00:00"}]
```

## Notes

- Database URL comes from `DATABASE_URL` (default: `sqlite:///./app.db`).
