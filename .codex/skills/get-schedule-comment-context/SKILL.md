---
name: get-schedule-comment-context
description: Read target remind schedules and recent action_logs (last 3 days) as JSON for agent comment generation.
---

# Get Schedule Comment Context

Use `scripts/get_schedule_comment_context.py` to fetch schedule rows and recent behavior logs.

## Run

```bash
uv run scripts/get_schedule_comment_context.py '["schedule-id-1","schedule-id-2"]'
```

```bash
echo '["schedule-id-1","schedule-id-2"]' | uv run scripts/get_schedule_comment_context.py -
```

## Input

- JSON array of schedule IDs
- CLI arg, stdin (`-`), or env `SCHEDULE_IDS_JSON`

## Output

Single-line JSON:

```json
{"schedule_ids":["..."],"schedules":[...],"recent_action_logs":[...]}
```
