"""Helpers for running isolated FastAPI subprocesses in tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def _allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def run_api_server(*, extra_env: dict[str, str] | None = None) -> Iterator[str]:
    """Run the app in a subprocess with an isolated temp database."""
    port = _allocate_port()
    base_url = f"http://127.0.0.1:{port}"
    temp_dir = tempfile.TemporaryDirectory(prefix="oni-api-test-")
    db_path = Path(temp_dir.name) / "test.sqlite3"
    process: subprocess.Popen[str] | None = None

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path}",
            "SLACK_SIGNING_SECRET": "test_secret",
        }
    )
    if extra_env:
        env.update(extra_env)

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for _ in range(60):
            if process.poll() is not None:
                break
            try:
                response = requests.get(f"{base_url}/health", timeout=1)
                if response.status_code == 200:
                    yield base_url
                    return
            except requests.exceptions.RequestException:
                time.sleep(0.25)

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        output = ""
        if process.stdout is not None:
            try:
                output = process.stdout.read()
            except Exception:
                output = ""
        raise RuntimeError(f"Server failed to start: {output.strip()}")
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            elif process.stdout is not None:
                process.stdout.close()
        temp_dir.cleanup()
