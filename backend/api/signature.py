"""Slack署名検証"""

import hashlib
import hmac
import os

from fastapi import HTTPException, Request, status


class SignatureVerificationError(Exception):
    """署名検証エラー"""

    pass


async def verify_slack_signature(request: Request) -> bool:
    """
    Slackリクエストの署名を検証

    Args:
        request: FastAPIリクエスト

    Returns:
        bool: 署名が有効ならTrue

    Raises:
        HTTPException: 署名が無効な場合

    参考: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    if not signing_secret:
        # 開発中は署名ヘッダーがない場合401を返す
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")
        if not timestamp or not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing signature headers (dev mode)",
            )
        # ヘッダーがあっても無効なら401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="SLACK_SIGNING_SECRET not configured"
        )

    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature headers"
        )

    # Get request body
    body = await request.body()

    # DEBUG: Print signature info
    print(f"[DEBUG] timestamp={timestamp}")
    print(f"[DEBUG] signature={signature}")
    print(f"[DEBUG] body={body[:100] if body else None}")

    # Slack公式フォーマット: v0:timestamp:body
    # 参考: https://api.slack.com/authentication/verifying-requests-from-slack
    sig_basestring = f"v0:{timestamp}:{body.decode() if body else ''}"

    # Calculate expected signature
    expected_hash = hmac.new(
        signing_secret.encode(), msg=sig_basestring.encode(), digestmod=hashlib.sha256
    ).hexdigest()
    expected_signature = f"v0={expected_hash}"

    # DEBUG: Print expected signature
    print(f"[DEBUG] expected_signature={expected_signature}")

    # Verify signature
    if signature != expected_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    return True


async def verify_signature_middleware(request: Request, call_next):
    """
    Slack署名検証ミドルウェア

    Args:
        request: FastAPI Request
        call_next: 次のハンドラー

    Returns:
        call_nextの結果、またはHTTPExceptionをraise
    """
    try:
        await verify_slack_signature(request)
        return await call_next(request)
    except HTTPException:
        raise
