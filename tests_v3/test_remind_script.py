from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Base,
    Commitment,
    Configuration,
    ConfigValueType,
    EventType,
    Schedule,
    ScheduleState,
)
from scripts.remind import build_remind_content, resolve_ignore_interval_minutes


def test_build_remind_content_matches_commitment_by_time_and_uses_comment(tmp_path):
    db_path = tmp_path / "remind_script.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    session = Session()
    user_id = "U03JBULT484"
    session.add_all(
        [
            Commitment(user_id=user_id, task="ジム行く", time="07:00:00", active=True),
            Commitment(user_id=user_id, task="スマホ置いて寝る", time="21:00:00", active=True),
        ]
    )
    schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REMIND,
        run_at=datetime(2026, 2, 16, 21, 0, 0),
        state=ScheduleState.PENDING,
        comment="スマホ置いて寝る時間だっちゃ。充電は部屋の外、布団に直行！",
        yes_comment="守れたのえらいっちゃ。明日の朝がラクになるよ。",
        no_comment="触っちゃったら、画面を伏せて30秒深呼吸だっちゃ。",
    )
    session.add(schedule)
    session.commit()

    task_name, task_time, description = build_remind_content(session, schedule)

    assert task_name == "スマホ置いて寝る"
    assert task_time == "21:00:00"
    assert description == "スマホ置いて寝る時間だっちゃ。充電は部屋の外、布団に直行！"
    session.close()


def test_resolve_ignore_interval_minutes_from_user_config(tmp_path):
    db_path = tmp_path / "remind_script_interval.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    session = Session()
    user_id = "U03JBULT484"
    session.add(
        Configuration(
            user_id=user_id,
            key="IGNORE_INTERVAL",
            value="600",
            value_type=ConfigValueType.INT,
        )
    )
    session.commit()

    minutes = resolve_ignore_interval_minutes(session, user_id)
    assert minutes == 10
    session.close()
