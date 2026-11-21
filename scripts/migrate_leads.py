"""One-time, verified import of a stopped legacy sales database into PostgreSQL."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from psycopg import sql

from src.api.db import database, initialize, sales_schema
from src.backend.app.catalog import init_db


TABLES = ("companies", "inquiries", "threads", "messages", "history", "cursors", "channel_sync",
          "users", "sessions", "login_limits", "alternative_buyers", "alternative_batches",
          "alternative_slots", "outreach_evidence", "outreach_contacts", "outreach_drafts", "domestic_signals")


def read_source(path):
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        source.execute("BEGIN")
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or source.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError(f"{path.name}: source integrity check failed")
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != set(TABLES):
            raise ValueError(f"Unexpected source tables: {tables ^ set(TABLES)}")
        return {t: [dict(r) for r in source.execute(f'SELECT * FROM "{t}"')] for t in TABLES}
    finally:
        source.close()


def ordered(rows):
    return sorted(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)


def demo_equivalent(first, second):
    times = {"companies": {"archived_at"}, "inquiries": {"created", "last_in"},
             "messages": {"at"}, "history": {"at"}}
    def normalized(data):
        return {t: ordered([{k:v for k,v in row.items() if k not in times.get(t, ())}
                            for row in rows if not (t=="cursors" and row["name"]=="selection-workspace")])
                for t,rows in data.items()}
    return (all(r["origin"] == "模拟数据" and r["account"] == "demo:showroom" for r in first["messages"])
            and normalized(first) == normalized(second))


def migrate(paths, backup_dir):
    sources = [read_source(p) for p in paths]
    primary = sources[0]
    for other in sources[1:]:
        if not demo_equivalent(primary, other):
            raise ValueError("旧库有不同的业务记录，需要明确合并映射；所有源库均已保留")
    raw = json.dumps(sources, sort_keys=True, ensure_ascii=False).encode()
    fingerprint = hashlib.sha256(raw).hexdigest()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"sales-before-postgres-{fingerprint[:12]}.json.gz"
    if not backup.exists():
        with tempfile.NamedTemporaryFile(dir=backup_dir, delete=False) as tmp:
            tmp.write(gzip.compress(raw))
        Path(tmp.name).replace(backup)
    if gzip.decompress(backup.read_bytes()) != raw:
        raise ValueError("备份校验失败")
    init_db()
    initialize()
    with database(True) as db:
        previous = db.execute("SELECT value FROM cursors WHERE name='legacy-import'").fetchone()
        if previous and previous["value"] == fingerprint:
            print("Already imported", fingerprint[:12])
            return
        for t in TABLES:
            query = sql.SQL("SELECT 1 FROM {}").format(sql.Identifier(t))
            if t == "cursors":
                query += sql.SQL(" WHERE name <> 'selection-workspace'")
            if db.execute(query + sql.SQL(" LIMIT 1")).fetchone():
                raise ValueError(f"目标表 {t} 已有业务数据，导入已取消")
        db.execute("DELETE FROM cursors WHERE name='selection-workspace'")
        for t in TABLES:
            rows = primary[t]
            table = sql.Identifier(t)
            if rows:
                keys = list(rows[0])
                stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(table,
                    sql.SQL(",").join(map(sql.Identifier, keys)), sql.SQL(",").join(sql.Placeholder() for _ in keys))
                with db.cursor() as cur:
                    cur.executemany(stmt, ([r[k] for k in keys] for r in rows))
            dest = db.execute(sql.SQL("SELECT * FROM {}").format(table)).fetchall()
            if ordered(dest) != ordered(rows):
                raise ValueError(f"{t} 数据校验失败")
        db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        for t, rows in primary.items():
            if rows and "id" in rows[0]:
                next_id = max(row["id"] for row in rows) + 1
                db.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN id RESTART WITH {}").format(sql.Identifier(t),sql.Literal(next_id)))
        workspaces = [next(r["value"] for r in data["cursors"] if r["name"]=="selection-workspace") for data in sources]
        db.execute("""INSERT INTO inquiry_quotes(quote_id,inquiry_id)
            SELECT q.id,(q.snapshot->>'inquiry_id')::integer FROM public.quote_draft q
            WHERE replace(q.snapshot->>'workspace','-','')=ANY(%s)""", (workspaces,))
        db.execute("INSERT INTO cursors(name,value) VALUES('legacy-import',%s)", (fingerprint,))
    print(f"Verified {len(TABLES)} tables in {sales_schema()}; backup {backup}")
    print({t:len(rows) for t,rows in primary.items() if rows})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+", help="Primary database first, optional matching demo copies after it")
    parser.add_argument("--backup-dir", type=Path, default=Path("backups"))
    args = parser.parse_args()
    migrate(args.sources, args.backup_dir)
