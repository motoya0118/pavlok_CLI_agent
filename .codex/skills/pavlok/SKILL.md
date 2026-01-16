---
name: pavlok
description: Send a Pavlok stimulus via the Pavlok API using scripts/pavlok.py. Use when you need to trigger vibe/beep/zap with a numeric value in this repo and print the API response.
---

# Pavlok Stimulus

Use `scripts/pavlok.py` to send a stimulus to the Pavlok API.

## Run

```bash
uv run scripts/pavlok.py zap 30 "reason for trigger"
```

## Inputs

- `stimulusType` is a string such as `vibe`, `beep`, or `zap`.
- `stimulusValue` is an integer.
- `reason` is required by the CLI parser but is not currently sent to the API.

## Notes

- Requires `PAVLOK_API_KEY` in `.env` or the environment.
- `scripts/pavlok.py` currently defines `call(stimulus_type, stimulus_value, reason)` but calls it with only two args. If you hit a `TypeError`, update the call site or function signature before running.
