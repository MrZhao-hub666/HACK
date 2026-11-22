import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from psycopg import sql

from src.backend.app.storage import db as connect_db

HERE = Path(__file__).resolve().parent


def utc(value=None):
    return (
        (value or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
    )


def sales_schema():
    return os.getenv("SALES_SCHEMA", "sales")


@contextmanager
def database(write=False):
    schema = sales_schema()
    with connect_db() as conn:
        conn.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        if write:
            # Preserve atomic event deduplication, assignment and account changes across workers.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(current_database()),hashtext(%s))", (schema,))
        yield conn


def initialize():
    with database(True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(sales_schema())))
        conn.execute((HERE / "schema.sql").read_text(encoding="utf8"))


def one(db, sql, params=()):
    from fastapi import HTTPException

    row = db.execute(sql, params).fetchone()
    if row is None:
        raise HTTPException(404, "记录不存在")
    return dict(row)


def audit(db, inquiry, actor, action, detail=""):
    db.execute(
        "INSERT INTO history(inquiry_id,at,actor,action,detail) VALUES (%s,%s,%s,%s,%s)",
        (inquiry, utc(), actor, action, detail),
    )
