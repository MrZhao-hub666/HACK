"""Run inbox tests in disposable PostgreSQL schemas with their own quote ledger."""
import os
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch
from uuid import uuid4

from psycopg import sql

from src.backend.app import main as catalogue
from src.backend.app.storage import db


@asynccontextmanager
async def no_excel_watch(app):
    yield


@contextmanager
def test_workspace():
    name = "test_sales_" + uuid4().hex
    schema = sql.Identifier(name)
    with db() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        conn.execute(sql.SQL("""CREATE TABLE {}.quote_draft (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, snapshot jsonb NOT NULL, request_key uuid UNIQUE
        )""").format(schema))
    try:
        with patch.dict(os.environ, SALES_SCHEMA=name), patch.object(catalogue, "lifespan", no_excel_watch):
            yield
    finally:
        with db() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(schema))
