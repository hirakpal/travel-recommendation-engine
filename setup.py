from setuptools import find_packages, setup

setup(
    name="travel-planner-ai",
    version="0.1.0",
    description="Multi-agent AI travel recommendations",
    author="Hirak Pal",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "fastapi==0.104.1",
        "uvicorn==0.24.0",
        "pydantic==2.5.0",
        "openai>=1.0.0",
        "python-dotenv==1.0.0",
        "sqlalchemy==2.0.0",
        "psycopg2-binary==2.9.12",
    ],
)
