import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def utc(value=None):
    return (
        (value or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
    )


@contextmanager
def database(write=False):
    path = Path(os.getenv("DB_PATH", "data/leads.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with database(True) as db:
        db.commit()
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript((HERE / "schema.sql").read_text(encoding="utf8"))
        db.execute("BEGIN IMMEDIATE")
        if "contact" not in {
            c["name"] for c in db.execute("PRAGMA table_info(companies)")
        }:
            db.execute(
                "ALTER TABLE companies ADD COLUMN contact TEXT NOT NULL DEFAULT ''"
            )
        if "owner" not in {
            c["name"] for c in db.execute("PRAGMA table_info(companies)")
        }:
            db.execute(
                "ALTER TABLE companies ADD COLUMN owner TEXT NOT NULL DEFAULT ''"
            )
        if "answered" not in {
            c["name"] for c in db.execute("PRAGMA table_info(messages)")
        }:
            db.execute(
                "ALTER TABLE messages ADD COLUMN answered INTEGER NOT NULL DEFAULT 0"
            )
            db.execute(
                "UPDATE messages SET answered=1 WHERE at<=(SELECT replied FROM inquiries WHERE id=messages.inquiry_id)"
            )


def one(db, sql, params=()):
    from fastapi import HTTPException

    row = db.execute(sql, params).fetchone()
    if row is None:
        raise HTTPException(404, "记录不存在")
    return dict(row)


def audit(db, inquiry, actor, action, detail=""):
    db.execute(
        "INSERT INTO history(inquiry_id,at,actor,action,detail) VALUES (?,?,?,?,?)",
        (inquiry, utc(), actor, action, detail),
    )
