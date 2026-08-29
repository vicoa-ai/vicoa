from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import settings

engine = create_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=20,
    pool_timeout=30,
    # Recycle every 5 min. Flycast drops idle TCP at 60s; keepalives below
    # keep connections alive in the meantime, and recycle ensures no
    # connection lives long enough to drift into trouble.
    pool_recycle=300,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000",
        # Client-side TCP keepalives (libpq). Mirrors the server-side
        # settings on vicoa-backend-db so both ends detect dead sockets
        # within ~60s instead of the kernel default 2h.
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
