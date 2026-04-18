import os
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

# Ensure the data directory exists before creating the engine.
Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.sqlite_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
