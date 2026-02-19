from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Configuration, ConfigValueType
from scripts.plan import resolve_ignore_interval_minutes


def test_resolve_ignore_interval_minutes_from_user_config(tmp_path):
    db_path = tmp_path / "plan_script_interval.sqlite3"
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
            value="1200",
            value_type=ConfigValueType.INT,
        )
    )
    session.commit()

    minutes = resolve_ignore_interval_minutes(session, user_id)
    assert minutes == 20
    session.close()
