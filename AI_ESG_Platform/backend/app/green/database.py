"""SQLAlchemy database setup for the Green Software Intelligence module.

Uses a separate SQLite database file (green_software.db) so it does not
interfere with the existing ChromaDB vector store used by the document
intelligence features.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Database file location — relative to the backend directory.
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "green_db")
os.makedirs(_DB_DIR, exist_ok=True)
DB_PATH = os.getenv("GREEN_DB_PATH", os.path.join(_DB_DIR, "green_software.db"))

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once at import time."""
    # Import models so SQLAlchemy registers them on Base before create_all.
    from app.green import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


# Initialize tables when this module is imported.
init_db()
