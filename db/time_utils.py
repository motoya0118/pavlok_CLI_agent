import os
from datetime import datetime
from zoneinfo import ZoneInfo


def _normalize_timezone(tz_name: str) -> str:
    if tz_name.upper() == "JST":
        return "Asia/Tokyo"
    return tz_name


def get_timezone() -> ZoneInfo:
    tz_name = os.getenv("TIMEZONE", "JST")
    tz_name = _normalize_timezone(tz_name)
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(get_timezone()).replace(tzinfo=None)
