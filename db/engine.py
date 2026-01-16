import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

Base = declarative_base()


def init_engine(database_url: str | None = None) -> None:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./app.db")
    global engine
    engine = create_engine(url, future=True)
    SessionLocal.configure(bind=engine)


engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./app.db"), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
