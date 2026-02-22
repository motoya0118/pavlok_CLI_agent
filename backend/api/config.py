"""Config API Endpoints"""

from typing import Any

from fastapi import Request


async def get_configurations(request: Request) -> dict[str, Any]:
    """
    設定値一覧取得

    Args:
        request: FastAPIリクエスト

    Returns:
        Dict[str, Any]: 設定値一覧
    """
    # TODO: Implement actual config retrieval from database
    return {
        "status": "success",
        "data": {
            "configurations": {
                "PAVLOK_TYPE_PUNISH": "beep",
                "PAVLOK_VALUE_PUNISH": 35,
                "IGNORE_LIMIT": 3,
                "REMIND_ENABLED": True,
            }
        },
    }


async def upsert_configuration(request: Request, config_data: dict[str, Any]) -> dict[str, Any]:
    """
    設定値更新・登録

    Args:
        request: FastAPIリクエスト
        config_data: 設定データ

    Returns:
        Dict[str, Any]: 更新後の設定値
    """
    # TODO: Implement actual config upsert to database with audit log
    updated = {}
    for key, value in config_data.items():
        # Convert string values to appropriate types
        if isinstance(value, str) and value.isdigit():
            updated[key] = int(value)
        else:
            updated[key] = value

    return {"status": "success", "detail": "設定を更新しました", "data": updated}


async def reset_configuration(request: Request, key: str = None) -> dict[str, Any]:
    """
    設定値リセット

    Args:
        request: FastAPIリクエスト
        key: リセット対象キー（省略時は全リセット）

    Returns:
        Dict[str, Any]: リセット結果
    """
    # TODO: Implement actual config reset with audit log
    return {
        "status": "success",
        "detail": f"設定{'(' + key + ')' if key else ''}をリセットしました",
    }
