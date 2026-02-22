---
name: update-schedule-comments
description: Update schedule comment fields (comment/yes_comment/no_comment) in bulk from JSON input.
---

# Update Schedule Comments

Use `scripts/update_schedule_comments.py` to write generated comments to `schedules`.

## Run

```bash
uv run scripts/update_schedule_comments.py '{"updates":[{"schedule_id":"id1","comment":"...","yes_comment":"...","no_comment":"..."}]}'
```

```bash
cat updates.json | uv run scripts/update_schedule_comments.py -
```

## Input

- JSON array of updates, or object with `updates` array
- each item requires `schedule_id`
- optional fields: `comment`, `yes_comment`, `no_comment`

## Output

Single-line JSON:

```json
{"updated":1,"requested":1}
```
