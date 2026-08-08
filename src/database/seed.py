"""Seed reference travel data into the SQLAlchemy database."""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Activity, Hotel, Restaurant

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        logger.warning("Seed file not found: %s", path)
        return {}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def seed_reference_data(engine) -> None:
    """Insert JSON reference data once; safe to run on every startup."""

    SessionLocal = sessionmaker(bind=engine)
    db: Session = SessionLocal()

    try:
        hotel_count = _seed_hotels(db, _load_json("hotels.json"))
        activity_count = _seed_activities(
            db,
            _load_json("activities.json"),
        )
        restaurant_count = _seed_restaurants(
            db,
            _load_json("restaurants.json"),
        )

        db.commit()

        logger.info(
            "REFERENCE_DATA_READY hotels=%s activities=%s restaurants=%s",
            hotel_count,
            activity_count,
            restaurant_count,
        )
    except Exception:
        db.rollback()
        logger.exception("REFERENCE_DATA_SEED_FAILED")
        raise
    finally:
        db.close()


def _seed_hotels(db: Session, grouped_data: dict) -> int:
    inserted = 0

    for records in grouped_data.values():
        for item in records:
            item_id = str(item["id"])

            if db.get(Hotel, item_id) is not None:
                continue

            db.add(
                Hotel(
                    id=item_id,
                    name=item.get("name", "Unnamed Hotel"),
                    city=item.get("city", ""),
                    country=item.get("country"),
                    rating=item.get(
                        "rating",
                        item.get("rating_score", item.get("star_rating")),
                    ),
                    price_per_night=float(
                        item.get("price_per_night", 0)
                    ),
                    currency=item.get("currency", "USD"),
                    amenities=item.get("amenities", []),
                    address=item.get("address"),
                    phone=item.get("phone"),
                    website=item.get(
                        "website",
                        item.get("booking_url"),
                    ),
                )
            )
            inserted += 1

    return inserted


def _seed_activities(db: Session, grouped_data: dict) -> int:
    inserted = 0

    for records in grouped_data.values():
        for item in records:
            item_id = str(item["id"])

            if db.get(Activity, item_id) is not None:
                continue

            db.add(
                Activity(
                    id=item_id,
                    name=item.get("name", "Unnamed Activity"),
                    city=item.get("city", ""),
                    category=item.get("category"),
                    description=item.get("description"),
                    duration_minutes=item.get("duration_minutes"),
                    cost=float(item.get("cost", 0) or 0),
                    currency=item.get("currency", "USD"),
                    difficulty_level=item.get(
                        "difficulty_level",
                        item.get("difficulty"),
                    ),
                    rating=item.get(
                        "rating",
                        item.get("rating_score"),
                    ),
                    best_time=item.get("best_time"),
                    location=item.get("location"),
                )
            )
            inserted += 1

    return inserted


def _seed_restaurants(db: Session, grouped_data: dict) -> int:
    inserted = 0

    for records in grouped_data.values():
        for item in records:
            item_id = str(item["id"])

            if db.get(Restaurant, item_id) is not None:
                continue

            dietary_options = []
            if item.get("vegetarian_options"):
                dietary_options.append("vegetarian")
            if item.get("vegan_options"):
                dietary_options.append("vegan")

            db.add(
                Restaurant(
                    id=item_id,
                    name=item.get("name", "Unnamed Restaurant"),
                    city=item.get("city", ""),
                    cuisine=item.get(
                        "cuisine",
                        item.get("cuisine_type"),
                    ),
                    description=item.get("description"),
                    rating=item.get(
                        "rating",
                        item.get("rating_score"),
                    ),
                    price_range=str(item.get("price_level", "")),
                    average_cost=item.get("average_cost"),
                    currency=item.get("currency", "USD"),
                    dietary_options=dietary_options,
                    address=item.get("address"),
                    website=item.get("website")
                    or item.get("booking_url"),
                )
            )
            inserted += 1

    return inserted
