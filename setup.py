from setuptools import setup, find_packages
from src.database.repository import HotelRepository
from src.database.repository import ActivityRepository
from src.database.repository import RestaurantRepository
setup(
    name="travel-recommendation-engine",
    version="0.1.0",
    description="Multi-agent AI travel recommendations",
    author="Your Name",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "fastapi",
        "uvicorn",
        "pydantic",
        "openapi",
        "python-dotenv",
        "sqlalchemy",
        "psycopg2-binary",
    ],
)
