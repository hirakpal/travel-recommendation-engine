"""SQLAlchemy database configuration for the Master Trip Register."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.seed import seed_reference_data

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./travel.db",
)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Create the Master Trip Register tables on first startup.
# This is suitable for the Streamlit/SQLite deployment. For production
# schema changes, use a migration tool such as Alembic.
Base.metadata.create_all(bind=engine)
seed_reference_data(engine)


def get_db():
    """Yield a database session and close it after use."""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
