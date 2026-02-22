"""Mock Classes for v0.3 Testing"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class APICallRecord:
    method: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    result: Any = None

    def __repr__(self) -> str:
        return f"APICallRecord(method={self.method}, args={self.args}, kwargs={self.kwargs})"


class MockSlackClient:
    def __init__(self):
        self._call_records = []
        self._messages = {}
        self._next_ts = "1234567890.123456"

    def _record_call(self, method: str, *args, **kwargs):
        record = APICallRecord(method=method, args=args, kwargs=kwargs)
        self._call_records.append(record)
        return record

    def get_call_history(self, method: str = None):
        if method:
            return [r for r in self._call_records if r.method == method]
        return self._call_records.copy()

    def assert_called(self, method: str, times: int = None):
        calls = self.get_call_history(method)
        if times is not None:
            assert len(calls) == times, (
                f"{method} should be called {times} times, but was {len(calls)}"
            )
        else:
            assert len(calls) > 0, f"{method} should be called at least once"

    def assert_not_called(self, method: str):
        calls = self.get_call_history(method)
        assert len(calls) == 0, f"{method} should not be called"

    def reset(self):
        self._call_records.clear()
        self._messages.clear()

    def post_message(self, channel: str, text: str = None, blocks: list = None, **kwargs) -> dict:
        self._record_call("post_message", channel, text, blocks, **kwargs)
        ts = self._next_ts
        self._next_ts = str(float(ts) + 1)
        return {"ok": True, "ts": ts, "channel": channel}

    def update_message(
        self, channel: str, ts: str, text: str = None, blocks: list = None, **kwargs
    ) -> dict:
        self._record_call("update_message", channel, ts, text, blocks, **kwargs)
        return {"ok": True, "ts": ts, "channel": channel}

    def post_ephemeral(
        self, channel: str, user: str, text: str, blocks: list = None, **kwargs
    ) -> dict:
        self._record_call("post_ephemeral", channel, user, text, blocks, **kwargs)
        return {"ok": True}

    def open_modal(self, trigger_id: str, view: dict, **kwargs) -> dict:
        self._record_call("open_modal", trigger_id, view, **kwargs)
        return {"ok": True}

    def update_view(self, view_id: str, view: dict, **kwargs) -> dict:
        self._record_call("update_view", view_id, view, **kwargs)
        return {"ok": True}


class MockPavlokClient:
    def __init__(self):
        self._call_records = []
        self._zap_count = 0
        self._vibe_count = 0
        self._beep_count = 0
        self._should_fail = False

    def _record_call(self, method: str, *args, **kwargs):
        record = APICallRecord(method=method, args=args, kwargs=kwargs)
        self._call_records.append(record)
        return record

    def get_call_history(self, method: str = None):
        if method:
            return [r for r in self._call_records if r.method == method]
        return self._call_records.copy()

    def assert_called(self, method: str, times: int = None):
        calls = self.get_call_history(method)
        if times is not None:
            assert len(calls) == times, (
                f"{method} should be called {times} times, but was {len(calls)}"
            )
        else:
            assert len(calls) > 0, f"{method} should be called at least once"

    def assert_not_called(self, method: str):
        calls = self.get_call_history(method)
        assert len(calls) == 0, f"{method} should not be called"

    def set_fail_mode(self, should_fail: bool):
        self._should_fail = should_fail

    def reset(self):
        self._call_records.clear()
        self._zap_count = 0
        self._vibe_count = 0
        self._beep_count = 0

    def get_zap_count(self) -> int:
        return self._zap_count

    def get_vibe_count(self) -> int:
        return self._vibe_count

    def get_beep_count(self) -> int:
        return self._beep_count

    def stimulate(self, stimulus_type: str, value: int = 50, **kwargs) -> dict:
        self._record_call("stimulate", stimulus_type, value, **kwargs)
        if self._should_fail:
            return {"success": False, "error": "Test failure"}

        if stimulus_type == "zap":
            self._zap_count += 1
        elif stimulus_type == "vibe":
            self._vibe_count += 1
        elif stimulus_type == "beep":
            self._beep_count += 1

        return {"success": True, "type": stimulus_type, "value": value}

    def zap(self, value: int = 50, **kwargs) -> dict:
        return self.stimulate("zap", value, **kwargs)

    def vibe(self, value: int = 100, **kwargs) -> dict:
        return self.stimulate("vibe", value, **kwargs)

    def beep(self, value: int = 100, **kwargs) -> dict:
        return self.stimulate("beep", value, **kwargs)

    def get_status(self, **kwargs) -> dict:
        self._record_call("get_status")
        return {"success": True, "battery": 85, "is_charging": False}


class MockAgentClient:
    def __init__(self):
        self._call_records = []
        self._default_response = "Generated response by agent"

    def _record_call(self, method: str, *args, **kwargs):
        record = APICallRecord(method=method, args=args, kwargs=kwargs)
        self._call_records.append(record)
        return record

    def get_call_history(self, method: str = None):
        if method:
            return [r for r in self._call_records if r.method == method]
        return self._call_records.copy()

    def reset(self):
        self._call_records.clear()

    def set_default_response(self, response: str):
        self._default_response = response

    async def run_skill(self, skill: str, prompt: str, **kwargs) -> str:
        self._record_call("run_skill", skill, prompt, **kwargs)
        return self._default_response

    async def generate_comment(self, task: str, result: str, **kwargs) -> str:
        self._record_call("generate_comment", task, result, **kwargs)
        return f"Comment for task: {task}, result: {result}"
