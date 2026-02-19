"""
v0.3 Pavlok API Client

Pavlokデバイス刺激APIクライアント
https://pavlok-eu.readme.io/docs/api_reference.html
"""
import os
from typing import Any
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_SESSION_FACTORY = None
_SESSION_DB_URL = None


def _get_session():
    """Create DB session using current DATABASE_URL."""
    global _SESSION_FACTORY, _SESSION_DB_URL
    database_url = os.getenv("DATABASE_URL", "sqlite:///./oni.db")

    if _SESSION_FACTORY is None or _SESSION_DB_URL != database_url:
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        )
        _SESSION_FACTORY = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
        _SESSION_DB_URL = database_url

    return _SESSION_FACTORY()


def _safe_int(value: Any, default: int) -> int:
    """Best-effort int parse with fallback."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _load_notification_stimulus_settings(
    user_id: str,
    session,
) -> tuple[str, int]:
    """
    Resolve per-user notification stimulus settings from configurations.
    Defaults:
    - type: vibe
    - value: 35
    """
    default_type = "vibe"
    default_value = 35
    if not user_id:
        return default_type, default_value

    from backend.models import Configuration

    rows = (
        session.query(Configuration.key, Configuration.value)
        .filter(
            Configuration.user_id == user_id,
            Configuration.key.in_(["PAVLOK_TYPE_NOTION", "PAVLOK_VALUE_NOTION"]),
        )
        .all()
    )
    config_map = {str(k): str(v) for k, v in rows}

    stimulus_type = config_map.get("PAVLOK_TYPE_NOTION", default_type).strip().lower()
    if stimulus_type not in PavlokClient.VALID_STIMULUS_TYPES:
        stimulus_type = default_type

    stimulus_value = _safe_int(config_map.get("PAVLOK_VALUE_NOTION", default_value), default_value)
    if stimulus_value < 0:
        stimulus_value = 0
    if stimulus_value > 100:
        stimulus_value = 100

    return stimulus_type, stimulus_value


def _normalize_event_type(event_type: Any) -> str:
    """Normalize schedule event_type enum/string to lowercase text."""
    if hasattr(event_type, "value"):
        raw = getattr(event_type, "value")
    else:
        raw = event_type
    value = str(raw or "").strip().lower()
    return value


def _resolve_commitment_task_for_schedule(session, schedule) -> str:
    """Resolve commitment task using schedule.commitment_id."""
    from backend.models import Commitment

    commitment_id = str(getattr(schedule, "commitment_id", "") or "").strip()
    if not commitment_id:
        fallback = str(getattr(schedule, "comment", "") or "").strip()
        return fallback or "タスク"

    row = (
        session.query(Commitment.task)
        .filter(
            Commitment.id == commitment_id,
        )
        .first()
    )
    if row and row[0]:
        return str(row[0])
    fallback = str(getattr(schedule, "comment", "") or "").strip()
    return fallback or "タスク"


def build_reason_for_schedule(session, schedule) -> str:
    """
    Build Pavlok reason text from schedule.

    Rule:
    - plan: "plan: 今日のプランを登録してください"
    - otherwise: "{event}: {commitment_task}"
    """
    event_name = _normalize_event_type(getattr(schedule, "event_type", ""))
    if not event_name:
        event_name = "remind"

    if event_name == "plan":
        return "plan: 今日のプランを登録してください"

    task = _resolve_commitment_task_for_schedule(session, schedule)
    return f"{event_name}: {task}"


def build_reason_for_schedule_id(
    schedule_id: str,
    *,
    session=None,
) -> str:
    """Build Pavlok reason text by schedule id."""
    if not schedule_id:
        return ""

    from backend.models import Schedule

    own_session = False
    if session is None:
        session = _get_session()
        own_session = True

    try:
        schedule = session.query(Schedule).filter(Schedule.id == schedule_id).first()
        if not schedule:
            return ""
        return build_reason_for_schedule(session, schedule)
    finally:
        if own_session:
            session.close()


def stimulate_notification_for_user(
    user_id: str,
    *,
    session=None,
    reason: str = "",
    api_key: str | None = None,
    api_base: str | None = None,
    http_client: Any = None,
) -> dict[str, Any]:
    """
    Send notification Pavlok stimulus using per-user config values.

    Config keys:
    - PAVLOK_TYPE_NOTION (default: vibe)
    - PAVLOK_VALUE_NOTION (default: 35)
    """
    own_session = False
    if session is None:
        session = _get_session()
        own_session = True

    try:
        stimulus_type, stimulus_value = _load_notification_stimulus_settings(
            user_id=user_id,
            session=session,
        )
    except Exception as exc:
        return {
            "success": False,
            "type": "vibe",
            "value": 35,
            "error": f"failed to load notification settings: {exc}",
        }
    finally:
        if own_session:
            session.close()

    try:
        client = PavlokClient(
            api_key=api_key,
            api_base=api_base,
            http_client=http_client,
        )
    except Exception as exc:
        return {
            "success": False,
            "type": stimulus_type,
            "value": stimulus_value,
            "error": str(exc),
        }

    result = client.stimulate(
        stimulus_type=stimulus_type,
        value=stimulus_value,
        reason=reason,
    )
    if isinstance(result, dict):
        result.setdefault("type", stimulus_type)
        result.setdefault("value", stimulus_value)
        if reason:
            result.setdefault("reason", reason)
    return result


class PavlokClient:
    """Pavlok APIクライアントクラス"""

    PAVLOK_API_BASE = "https://api.pavlok.com/api/v5"

    VALID_STIMULUS_TYPES = ("zap", "beep", "vibe")

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        http_client: Any = None
    ):
        """
        Args:
            api_key: Pavlok APIキー。省略時は環境変数PAVLOK_API_KEYを使用
            api_base: APIベースURL（テスト用）
            http_client: HTTPクライアント（テスト用モック注入）
        """
        self.api_key = api_key or os.getenv("PAVLOK_API_KEY")
        self.api_base = api_base or os.getenv("PAVLOK_API_BASE") or self.PAVLOK_API_BASE
        self.http_client = http_client or requests

        if not self.api_key:
            raise ValueError(
                "PAVLOK_API_KEY is not set. "
                "Provide api_key parameter or set environment variable."
            )

    def _get_headers(self) -> dict[str, str]:
        """APIリクエストヘッダーを生成"""
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.api_key}"
        }

    def _post(self, url: str, payload: dict) -> requests.Response:
        """API POSTリクエストを実行"""
        return self.http_client.post(
            url,
            json=payload,
            headers=self._get_headers(),
            timeout=10
        )

    def _get(self, url: str) -> requests.Response:
        """API GETリクエストを実行"""
        return self.http_client.get(
            url,
            headers=self._get_headers(),
            timeout=10
        )

    def _validate_stimulus_type(self, stimulus_type: str) -> None:
        """刺激タイプのバリデーション"""
        if stimulus_type not in self.VALID_STIMULUS_TYPES:
            raise ValueError(
                f"Invalid stimulus type: {stimulus_type}. "
                f"Valid types are: {', '.join(self.VALID_STIMULUS_TYPES)}"
            )

    def _validate_value(self, value: int) -> None:
        """刺激値のバリデーション (0-100)"""
        if not 0 <= value <= 100:
            raise ValueError(f"Value must be between 0 and 100, got: {value}")

    def stimulate(
        self,
        stimulus_type: str,
        value: int = 50,
        reason: str = "",
        **kwargs
    ) -> dict[str, Any]:
        """
        刺激を送信

        Args:
            stimulus_type: 刺激タイプ ("zap", "beep", "vibe")
            value: 刺激強度 (0-100), デフォルト50
            **kwargs: 追加パラメータ

        Returns:
            dict: APIレスポンス {"success": bool, "type": str, "value": int, ...}
        """
        self._validate_stimulus_type(stimulus_type)
        self._validate_value(value)

        url = f"{self.api_base}/stimulus/send"
        payload = {
            "stimulus": {
                "stimulusType": stimulus_type,
                "stimulusValue": value
            }
        }
        if isinstance(reason, str) and reason.strip():
            payload["stimulus"]["reason"] = reason.strip()

        try:
            response = self._post(url, payload)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "type": stimulus_type,
                "value": value,
                "reason": reason.strip() if isinstance(reason, str) else "",
                "raw": data
            }
        except Exception as e:
            return {
                "success": False,
                "type": stimulus_type,
                "value": value,
                "reason": reason.strip() if isinstance(reason, str) else "",
                "error": str(e)
            }

    def zap(self, value: int = 50, **kwargs) -> dict[str, Any]:
        """ZAP刺激を送信（ショートカット）"""
        return self.stimulate(stimulus_type="zap", value=value, **kwargs)

    def vibe(self, value: int = 100, **kwargs) -> dict[str, Any]:
        """VIBE刺激を送信（振動）"""
        return self.stimulate(stimulus_type="vibe", value=value, **kwargs)

    def beep(self, value: int = 100, **kwargs) -> dict[str, Any]:
        """BEEP刺激を送信（音）"""
        return self.stimulate(stimulus_type="beep", value=value, **kwargs)

    def get_status(self, **kwargs) -> dict[str, Any]:
        """
        デバイス状態を取得

        Returns:
            dict: デバイス状態情報 {"success": bool, "battery": int, ...}
        """
        url = f"{self.api_base}/me"
        try:
            response = self._get(url)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "battery": data.get("battery", 0),
                "is_charging": data.get("isCharging", False),
                "raw": data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
