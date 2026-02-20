"""Slack署名検証ミドルウェア"""

import hashlib
import hmac
import os

from fastapi import HTTPException, Request


class SignatureVerificationError(Exception):
    pass


def verify_slack_signature(timestamp, signature, request_body=None):
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    if not signing_secret:
        raise HTTPException(status_code=500, detail="SLACK_SIGNING_SECRET not configured")

    base_str = timestamp + "v0:" + signing_secret
    if request_body is None:
        expected_b64 = f"v0:{hashlib.sha256(base_str.encode()).hexdigest()}"
    else:
        body_bytes = request_body.encode() if isinstance(request_body, str) else request_body
        expected_b64 = f"v0:{hmac.new(signing_secret.encode(), msg=body_bytes, digestmod=hashlib.sha256).hexdigest()}"

    if signature != expected_b64:
        raise SignatureVerificationError("Invalid signature")
    return True


async def verify_signature_middleware(request: Request, call_next):
    skip_paths = ["/internal/", "/health", "/docs"]
    if request.url.path in skip_paths:
        return await call_next(request)

    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    body = await request.body()

    try:
        if not verify_slack_signature(timestamp, signature, body):
            raise SignatureVerificationError("Invalid signature")
    except SignatureVerificationError as e:
        raise HTTPException(status_code=401, detail=str(e))
