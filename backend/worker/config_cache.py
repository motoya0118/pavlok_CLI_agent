"""Config Cache Module"""
import os
import json
from typing import Any, Dict
from datetime import datetime, timedelta


# Cache storage: {key: (value, expire_time)}
_config_cache: Dict[str, tuple[Any, datetime]] = {}
CACHE_TTL = timedelta(seconds=60)  # 60秒キャッシュ
ENV_ONLY_KEYS = {"TIMEOUT_REMIND", "TIMEOUT_REVIEW", "RETRY_DELAY"}
ENV_FALLBACK_KEYS = {
    "RETRY_DELAY": ("RETRY_DELAY", "RETRY_DELAY_MIN"),
}


def _parse_value(value: str, value_type: str) -> Any:
    """
    設定値を型に応じてパースする

    Args:
        value: 設定値（文字列）
        value_type: 型（str, int, float, bool, json）

    Returns:
        パースされた値
    """
    if value_type == "int":
        return int(value)
    elif value_type == "float":
        return float(value)
    elif value_type == "bool":
        return value.lower() in ("true", "1", "yes")
    elif value_type == "json":
        return json.loads(value)
    else:
        return value


def _coerce_env_value(raw: str, default: Any) -> Any:
    """Coerce env string into the same type as default when possible."""
    if isinstance(default, bool):
        return raw.lower() in ("true", "1", "yes", "on")
    if isinstance(default, int):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default
    if isinstance(default, (dict, list)):
        try:
            return json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return default
    return raw


def _read_env_raw(key: str) -> str | None:
    """Read env raw string with optional fallback key aliases."""
    names = ENV_FALLBACK_KEYS.get(key, (key,))
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        return raw
    return None


def get_config(key: str, default: Any = None, session=None) -> Any:
    """
    設定値を取得する（キャッシュ考慮）

    優先順位: DB > 環境変数 > デフォルト値

    Args:
        key: 設定キー
        default: デフォルト値
        session: DBセッション（オプション）

    Returns:
        設定値
    """
    now = datetime.now()

    # Check cache
    if key in _config_cache:
        value, expire_time = _config_cache[key]
        if now < expire_time:
            return value
        # Cache expired, remove
        del _config_cache[key]

    # Env-only operational keys (do not read DB).
    if key in ENV_ONLY_KEYS:
        raw = _read_env_raw(key)
        value = _coerce_env_value(raw, default) if raw is not None else default
        _config_cache[key] = (value, now + CACHE_TTL)
        return value

    # Try to get from DB if session provided
    if session is not None:
        try:
            from backend.models import Configuration

            config = session.query(Configuration).filter_by(key=key).first()
            if config:
                value = _parse_value(config.value, config.value_type)
                # Cache with TTL
                _config_cache[key] = (value, now + CACHE_TTL)
                return value
        except Exception:
            # DB access failed, continue to env var
            pass

    # Try environment variable
    raw = _read_env_raw(key)
    if raw is not None:
        value = _coerce_env_value(raw, default)
        # Cache with TTL
        _config_cache[key] = (value, now + CACHE_TTL)
        return value

    # Return default
    return default


def invalidate_config_cache(key: str = None) -> None:
    """
    設定キャッシュを無効化する

    Args:
        key: 無効化するキー（省略時は全て）
    """
    if key is None:
        _config_cache.clear()
    elif key in _config_cache:
        del _config_cache[key]
