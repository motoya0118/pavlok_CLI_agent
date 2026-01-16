import argparse
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_API_BASE = "https://slack.com/api"


def require_bot_token() -> str:
    token = os.getenv("SLACK_BOT_USER_OAUTH_TOKEN")
    if not token:
        raise SystemExit(
            "SLACK_BOT_USER_OAUTH_TOKEN is not set. Add it to .env or the environment."
        )
    return token


def get_reply_token(bot_token: str) -> str:
    return os.getenv("SLACK_USER_OAUTH_TOKEN") or bot_token


def normalize_channel(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("#"):
        return channel
    if channel and channel[0] in {"C", "G", "D", "W"} and channel.isalnum():
        return channel
    return f"#{channel}"


def require_channel(override: str | None = None) -> str:
    channel = override or os.getenv("SLACK_CHANNEL")
    if not channel:
        raise SystemExit(
            "SLACK_CHANNEL is not set. Add it to .env or the environment."
        )
    return channel


def build_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def parse_response(response: requests.Response) -> dict:
    try:
        return response.json()
    except ValueError as exc:
        raise SystemExit(f"Slack API error: {response.text}") from exc


def unescape_cli_text(text: str) -> str:
    return text.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")


def post_question(
    question: str, token: str, add_reply_hint: bool, channel: str
) -> tuple:
    url = f"{SLACK_API_BASE}/chat.postMessage"
    text = question
    if add_reply_hint:
        text = f"{question}\n\nReply in thread."
    payload = {"channel": normalize_channel(channel), "text": text}

    response = requests.post(
        url, data=payload, headers=build_headers(token), timeout=10
    )
    data = parse_response(response)
    if not data.get("ok"):
        raise SystemExit(f"Slack API error: {data.get('error', 'unknown_error')}")
    return data["channel"], data["ts"]


def post_reply(text: str, thread_ts: str, token: str, channel: str) -> str:
    url = f"{SLACK_API_BASE}/chat.postMessage"
    payload = {
        "channel": normalize_channel(channel),
        "text": text,
        "thread_ts": thread_ts,
    }

    response = requests.post(
        url, data=payload, headers=build_headers(token), timeout=10
    )
    data = parse_response(response)
    if not data.get("ok"):
        raise SystemExit(f"Slack API error: {data.get('error', 'unknown_error')}")
    return data["ts"]


def fetch_replies(channel: str, thread_ts: str, token: str) -> list:
    url = f"{SLACK_API_BASE}/conversations.replies"
    params = {
        "channel": channel,
        "ts": thread_ts,
        "inclusive": True,
        "limit": 100,
    }

    response = requests.get(url, params=params, headers=build_headers(token), timeout=10)
    data = parse_response(response)
    if not data.get("ok"):
        if data.get("error") == "missing_scope":
            raise SystemExit(
                "Slack API error: missing_scope. Add history scopes to the bot token "
                "(channels:history, groups:history, im:history, mpim:history) and "
                "reinstall the app."
            )
        raise SystemExit(f"Slack API error: {data.get('error', 'unknown_error')}")
    return data.get("messages", [])


def find_user_reply(messages: list, thread_ts: str) -> str | None:
    for message in messages:
        if message.get("ts") == thread_ts:
            continue
        if message.get("subtype"):
            continue
        if "user" not in message:
            continue
        return message.get("text", "")
    return None


def wait_for_reply(
    channel: str,
    thread_ts: str,
    token: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> str | None:
    deadline = time.monotonic() + timeout_sec
    while True:
        reply = find_user_reply(fetch_replies(channel, thread_ts, token), thread_ts)
        if reply is not None:
            return reply
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_sec)


def build_result(
    question: str,
    answer: str | None,
    is_answer: bool,
    thread_ts: str,
    message_ts: str,
) -> dict:
    return {
        "assistant_question": question,
        "user_answer": answer,
        "is_answer": is_answer,
        "thread_ts": thread_ts,
        "message_ts": message_ts,
    }


def print_result(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def run_ask(
    question: str,
    timeout: float,
    interval: float,
    no_reply_hint: bool,
    channel_override: str | None,
) -> None:
    bot_token = require_bot_token()
    channel = require_channel(channel_override)
    reply_token = get_reply_token(bot_token)
    channel_id, thread_ts = post_question(
        question, bot_token, not no_reply_hint, channel
    )
    reply = wait_for_reply(channel_id, thread_ts, reply_token, timeout, interval)
    if reply is None:
        payload = build_result(question, None, False, thread_ts, thread_ts)
    else:
        payload = build_result(question, reply, True, thread_ts, thread_ts)
    print_result(payload)


def run_reply(question: str, thread_ts: str, channel_override: str | None) -> None:
    bot_token = require_bot_token()
    channel = require_channel(channel_override)
    message_ts = post_reply(question, thread_ts, bot_token, channel)
    payload = build_result(question, None, False, thread_ts, message_ts)
    print_result(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post a question to Slack and wait for a reply.",
    )
    parser.add_argument(
        "question", help="Message text (question in ask mode, reply in reply mode)."
    )
    parser.add_argument(
        "--mode",
        choices=("ask", "reply"),
        default="ask",
        help="ask: post a question and wait; reply: post to a thread.",
    )
    parser.add_argument(
        "--thread-ts",
        help="Thread timestamp to reply to (required in reply mode).",
    )
    parser.add_argument(
        "--channel",
        help="Slack channel name or ID (defaults to SLACK_CHANNEL).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="Seconds to wait for a reply.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2,
        help="Polling interval in seconds.",
    )
    parser.add_argument(
        "--no-reply-hint",
        action="store_true",
        help="Do not append a reply hint line.",
    )
    args = parser.parse_args()

    question = unescape_cli_text(args.question)

    if args.mode == "ask":
        run_ask(
            question=question,
            timeout=args.timeout,
            interval=args.interval,
            no_reply_hint=args.no_reply_hint,
            channel_override=args.channel,
        )
    else:
        if not args.thread_ts:
            raise SystemExit("--thread-ts is required in reply mode.")
        run_reply(question, args.thread_ts, args.channel)


if __name__ == "__main__":
    main()
