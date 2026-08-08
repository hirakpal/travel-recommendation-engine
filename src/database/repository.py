from sqlalchemy.orm import Session

from src.database.models import Activity, Hotel, Restaurant


class HotelRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_city_and_budget(
        self,
        city: str,
        min_price: float,
        max_price: float,
    ) -> list[Hotel]:
        return (
            self.db.query(Hotel)
            .filter(
                Hotel.city.ilike(city),
                Hotel.price_per_night >= min_price,
                Hotel.price_per_night <= max_price,
            )
            .all()
        )


class ActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_city(self, city: str) -> list[Activity]:
        return (
            self.db.query(Activity)
            .filter(Activity.city.ilike(city))
            .all()
        )


class RestaurantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_city(self, city: str) -> list[Restaurant]:
        return (
            self.db.query(Restaurant)
            .filter(Restaurant.city.ilike(city))
            .all()
        )
