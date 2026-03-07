from pathlib import Path

from app.db.base import Base
from app.db.session import engine


def pytest_sessionstart(session):
    db_path = Path(__file__).resolve().parents[1] / 'parlay_bot.db'
    if db_path.exists():
        db_path.unlink()
    Base.metadata.create_all(bind=engine)
