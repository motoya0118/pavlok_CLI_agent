import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from db import engine as db_engine
from db import models as db_models


@pytest.fixture()
def db_setup(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("TIMEZONE", "JST")

    db_engine.init_engine(db_url)
    db_models.Base.metadata.drop_all(bind=db_engine.engine)
    db_models.Base.metadata.create_all(bind=db_engine.engine)
    yield


@pytest.fixture()
def db_session(db_setup):
    session = db_engine.SessionLocal()
    try:
        yield session
    finally:
        session.close()
