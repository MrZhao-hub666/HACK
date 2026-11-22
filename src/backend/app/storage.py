"""Shared PostgreSQL connection settings for the sales and catalogue modules."""
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from psycopg import connect
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")
_selector = dotenv_values(ROOT / "src/backend/.env.local")


def model_setting(name, default=None):
    return _selector.get(name) or os.getenv(name, default)


def db():
    url = os.getenv("DATABASE_URL") or _selector.get("DATABASE_URL")
    if url:
        return connect(url, row_factory=dict_row, connect_timeout=5)
    return connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT") or os.getenv("PG_PORT", "25432"),
        user=os.getenv("PGUSER", "catalog"), dbname=os.getenv("PGDATABASE", "catalog"),
        password=os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD", "catalog_local"),
        row_factory=dict_row, connect_timeout=5,
    )
