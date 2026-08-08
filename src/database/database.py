"""Database configuration for the Master Trip Register."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./travel.db",
)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Create all database tables, including the trips table.
Base.metadata.create_all(bind=engine)


def get_db():
    """Yield a database session and close it afterward."""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
