import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get the absolute path of the project root (where .env is located)
# Since database.py is in 'app/', the root is one level up.
basedir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(basedir, "..", ".env")

# Load environment variables
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv() # Fallback to CWD

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    # Fallback for local development if .env is missing
    SQLALCHEMY_DATABASE_URL = "postgresql://postgres:password@localhost/grocery_db"

# Fix: Only apply check_same_thread for SQLite
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args,pool_pre_ping=True,pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
