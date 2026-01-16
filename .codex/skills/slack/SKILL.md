---
name: slack
description: Post a question to Slack and wait for a reply, or post a reply into a thread using scripts/slack.py.
---

# Slack Ask + Thread Reply

Use `scripts/slack.py` to post a question and wait for the first reply, or to post a reply into an existing thread.

## Run

```bash
uv run scripts/slack.py "Did you finish the task?" --timeout 120 --interval 2
```

```bash
uv run scripts/slack.py --mode reply --thread-ts 1700000000.000000 "Reply text"
```

## Inputs

- `question` is the message text (question in `ask` mode, reply in `reply` mode).
- `--mode` chooses behavior (`ask` default, `reply` posts into a thread).
- `--no-reply-hint` skips appending "Reply in thread."
- `ask` mode:
  - `--timeout` sets max wait time in seconds (default: 60).
  - `--interval` sets polling interval in seconds (default: 2).
  - `--thread-ts` and `--channel` are not required.
- `reply` mode:
  - `--thread-ts` is required.
  - `--channel` overrides `SLACK_CHANNEL` (accepts name or ID).
  - `--timeout` and `--interval` are not used.

## Outputs

Ask mode prints a single line:

```
{assistant_question: ..., user_answer: ..., is_answer: true|false}
```

If no reply arrives before timeout, `user_answer` is empty and `is_answer` is `false`.

Reply mode prints a single line:

```
{action: reply, channel: ..., thread_ts: ..., message_ts: ...}
```

## Notes

- Requires `SLACK_BOT_USER_OAUTH_TOKEN`.
- Optional `SLACK_USER_OAUTH_TOKEN` is used for reading replies; if unset, the bot token is reused.
- Missing history scopes will cause `missing_scope` errors; add `channels:history`, `groups:history`, `im:history`, and `mpim:history` as needed.
