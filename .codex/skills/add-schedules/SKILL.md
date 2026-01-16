---
name: add-schedules
description: Insert schedule rows into the local database (schedules) from a JSON array. Use when bulk-loading schedule entries with script_name, input_value, and scheduled_date via scripts/add_schedules.py.
---

# Add Schedules

Use `scripts/add_schedules.py` to insert multiple records into `schedules`.

## Run

```bash
uv run scripts/add_schedules.py '[{"script_name":"pavlok","input_value":"zap 30","scheduled_date":"2026-01-10 09:30"}]'
```

```bash
cat schedules.json | uv run scripts/add_schedules.py -
```

## Inputs

Each record must be an object with:

- `script_name` (string)
- `input_value` (string)
- `scheduled_date` as `YYYYMMDD`, `YYYYMMDDhhmm`, `YYYY-MM-DD`, or `YYYY-MM-DD hh:mm` (minute precision)

`id` and `is_execute` are ignored if present. Any other extra fields cause an error.

## Notes

- Database URL comes from `DATABASE_URL` (default: `sqlite:///./app.db`).
