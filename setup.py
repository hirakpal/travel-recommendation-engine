from setuptools import setup, find_packages

setup(
    name="travel-planner-ai,
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
        "anthropic",
        "python-dotenv",
    ],
)
