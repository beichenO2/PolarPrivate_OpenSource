"""Smoke tests for database fixtures."""

from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SQLITE_MAX_OVERFLOW, SQLITE_POOL_SIZE, create_sync_engine


def test_db_session_fixture_yields_session(db_session: Session) -> None:
    assert db_session.bind is not None


def test_sqlite_file_pool_allows_100_slots(tmp_path: Path) -> None:
    engine = create_sync_engine(f"sqlite:///{tmp_path / 'pool.db'}")
    try:
        pool = engine.pool
        assert pool.size() == SQLITE_POOL_SIZE == 100
        assert pool._max_overflow == SQLITE_MAX_OVERFLOW == 0
    finally:
        engine.dispose()
