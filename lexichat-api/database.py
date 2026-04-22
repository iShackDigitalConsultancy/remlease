from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os

db_url = os.environ.get("DATABASE_URL")
env_mode = os.environ.get("ENVIRONMENT")

if db_url:
    if db_url.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URL = db_url.replace("postgres://", "postgresql://", 1)
    else:
        SQLALCHEMY_DATABASE_URL = db_url
else:
    if env_mode == "development":
        print("WARNING: Running on SQLite in development mode")
        SQLALCHEMY_DATABASE_URL = "sqlite:///./rem-leases.db"
    else:
        raise RuntimeError("FATAL: DATABASE_URL is not set. Refusing to start without a persistent database connection.")

# SQLite strictly needs check_same_thread=False
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
