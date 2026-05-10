import os  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLALCHEMY_DATABASE_URL = "postgresql://postgres:password@localhost/grocery_db"
SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:npg_X2AcSzJBlCj1@ep-blue-firefly-anaq1p1s.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Fix: Only apply check_same_thread for SQLite
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
