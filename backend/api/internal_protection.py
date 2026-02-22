"""Internal Protection Middleware"""

import os

from fastapi import HTTPException, Request, status


class InternalProtectionError(Exception):
    """Internal Protection Error"""

    pass


async def verify_internal_request(request: Request) -> bool:
    """
    内部リクエストの検証

    Args:
        request: FastAPIリクエスト

    Returns:
        bool: 検証OKならTrue

    Raises:
        HTTPException: 検証失敗の場合
    """
    valid_secret = os.getenv("ONI_INTERNAL_SECRET")
    if not valid_secret:
        # 開発中はヘッダーがない場合401を返す
        secret = request.headers.get("X-Internal-Secret")
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing secret header (dev mode)"
            )
        # ヘッダーがあっても無効なら401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="ONI_INTERNAL_SECRET is not configured"
        )

    # Check secret header
    secret = request.headers.get("X-Internal-Secret")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing secret header"
        )

    # Verify secret
    if secret != valid_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")

    return True
