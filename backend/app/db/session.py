"""Database engine and per-request session."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Every connection works in UTC (spec section 2: PostgreSQL stores UTC).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"options": "-c timezone=UTC"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
