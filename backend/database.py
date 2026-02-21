"""Database engine setup and session management."""

from sqlmodel import Session, SQLModel, create_engine

from backend.config import settings

engine_kwargs = {"echo": False}
if settings.DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update(pool_size=5, max_overflow=10, pool_pre_ping=True)
engine = create_engine(settings.DATABASE_URL, **engine_kwargs)


def create_db_and_tables() -> None:
    """Create all database tables from SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Yield a database session for FastAPI Depends()."""
    with Session(engine) as session:
        yield session
