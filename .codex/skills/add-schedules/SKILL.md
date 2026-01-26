---
name: add-schedules
description: Insert schedule rows into the local database (schedules) from a JSON array. Use when bulk-loading schedule entries with prompt_name, input_value, and scheduled_date via scripts/add_schedules.py.
---

# Add Schedules

Use `scripts/add_schedules.py` to insert multiple records into `schedules`.

## Run

```bash
uv run scripts/add_schedules.py '[{"prompt_name":"remind_ask","input_value":"パチンコ行ってないか確認","scheduled_date":"2026-01-10 09:30"}]'
```

```bash
cat schedules.json | uv run scripts/add_schedules.py -
```

## Inputs

Each record must be an object with:

- `prompt_name` (string)
- `input_value` (string)
- `scheduled_date` as `YYYYMMDD`, `YYYYMMDDhhmm`, `YYYY-MM-DD`, `YYYY-MM-DD hh:mm`, or `YYYY-MM-DDTHH:MM` (minute precision). Integers are accepted for the numeric formats.

`id` and `state` are ignored if present. Any other extra fields cause an error.

## Outputs

Prints a single line of JSON:

```
{"inserted": 2}
```

## Notes

- Database URL comes from `DATABASE_URL` (default: `sqlite:///./app.db`).
