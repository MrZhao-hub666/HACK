"""Synchronize printed rows while keeping their illustrated PDF order stable."""
import io
import re
from openpyxl import load_workbook

from .catalog import db
from .foreign import BOOK, COUNTRIES, LABEL, canonical_id, fields, install, migrate_country_ids, read_tables
from .sync import cell_text, data_hash, digest

SINGLE_THICKNESS = re.compile(r"[0-9]+(?:\.[0-9]+)?")

def editable_rows(tables):
    return {area:[{k:r[k] for k in fields(area) if k!="picture"} for r in rows]
            for area,rows in tables.items()}

def sheet_values(raw, tables):
    book=load_workbook(io.BytesIO(raw),read_only=True)
    try:
        sheet_names=["无国别" if n=="国别未标" else n for n in book.sheetnames]
        if sheet_names!=[v[0] for v in COUNTRIES.values()]:
            raise ValueError("国别工作表名称或顺序已变动")
        result={}
        legacy="国别未标" in book.sheetnames
        for area,records in tables.items():
            name=COUNTRIES[area][0]
            keys=fields(area)
            sheet=book["国别未标"] if area=="N" and "国别未标" in book.sheetnames else book[name]
            rows=iter(sheet.values)
            labels=list(next(rows,()))
            old_column=labels.index("内径") if "内径" in labels else None
            if old_column is not None:
                labels.pop(old_column)
                legacy=True
            if labels!=[LABEL[k] for k in keys]:
                raise ValueError(f"{name}表头与 PDF 模板不一致")
            values=[]
            for raw_row in rows:
                if not any(v is not None for v in raw_row):
                    continue
                if old_column is not None:
                    raw_row=raw_row[:old_column]+raw_row[old_column+1:]
                row={k:cell_text(v) for k,v in zip(keys,raw_row) if k!="picture"}
                if sheet.title=="国别未标" and row["part_id"]:
                    row["part_id"]=canonical_id(row["part_id"])
                if any(v and v.startswith("=") for v in row.values()):
                    raise ValueError(f"{name}表需要填写实际值")
                values.append(row)
            if [r["part_id"] for r in values]!=[r["part_id"] for r in records]:
                raise ValueError(f"{name}表的唯一标识符或目录行序有变动，请核对原册")
            result[area]=values
        return result,legacy
    finally:
        book.close()

def synchronize():
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(400713)")
        if not conn.execute("SELECT to_regclass('foreign_catalog.source') AS t").fetchone()["t"]:
            install(conn)
        migrate_country_ids(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS foreign_catalog.sync_state (
            id integer PRIMARY KEY CHECK(id=1), file_hash text NOT NULL, data_hash text NOT NULL)""")
        state=conn.execute("SELECT * FROM foreign_catalog.sync_state WHERE id=1").fetchone()
        tables_list=", ".join("foreign_catalog."+v[1] for v in COUNTRIES.values())
        conn.execute(f"LOCK TABLE {tables_list} IN SHARE ROW EXCLUSIVE MODE")
        tables=read_tables(conn)
        if not any(tables.values()):
            return ""
        current=editable_rows(tables)
        db_hash=data_hash(current)
        raw=BOOK.read_bytes() if BOOK.exists() else None
        file_hash=digest(raw) if raw is not None else None
        if (state and state["file_hash"]==file_hash and state["data_hash"]==db_hash
                and not any(SINGLE_THICKNESS.fullmatch(r["d"] or "") for rows in tables.values() for r in rows)):
            return db_hash
        rebuild=True
        if raw is not None and (not state or file_hash!=state["file_hash"]):
            incoming,rebuild=sheet_values(raw,tables)
            new_hash=data_hash(incoming)
            hashes={db_hash}
            if rebuild and state and db_hash!=state["data_hash"]:
                old_country={**current,"U":[dict(r,part_id="FU"+r["part_id"][2:]) for r in current["N"]]}
                del old_country["N"]
                hashes.add(data_hash(old_country))
                for version in (old_country,current):
                    hashes.add(data_hash({a:[dict(r,inner_diameter=None) for r in group] for a,group in version.items()}))
            if new_hash!=db_hash and (not state or state["data_hash"] not in hashes):
                raise ValueError("外贸国别 Excel 与数据库均有变动，请核对后合并")
            with conn.cursor() as cur:
                for area,rows in incoming.items():
                    keys=[k for k in fields(area) if k not in ("part_id","picture")]
                    changes=[tuple(new[k] for k in keys)+(new["part_id"],) for old,new in zip(current[area],rows) if old!=new]
                    if changes:
                        table=COUNTRIES[area][1]
                        cur.executemany(f"UPDATE foreign_catalog.{table} SET "+
                                        ", ".join(k+"=%s" for k in keys)+" WHERE part_id=%s",changes)
            db_hash=new_hash
            if digest(BOOK.read_bytes())!=file_hash:
                raise ValueError("国别工作簿在读取时又被保存，请重试")
            tables=read_tables(conn)
        # Reconcile pending edits first, then publish the same representation on both sides.
        normalized=False
        with conn.cursor() as cur:
            for area,rows in tables.items():
                updates=[]
                for row in rows:
                    value=row["d"] or ""
                    if SINGLE_THICKNESS.fullmatch(value):
                        row["d"]=value+"/"+value
                        updates.append((row["d"],row["part_id"]))
                if updates:
                    cur.executemany(f"UPDATE foreign_catalog.{COUNTRIES[area][1]} SET d=%s WHERE part_id=%s",updates)
                    normalized=True
        if normalized:
            rebuild=True
            db_hash=data_hash(editable_rows(tables))
        if rebuild:
            from .foreign_excel import render
            render(tables,file_hash)
            file_hash=digest(BOOK.read_bytes())
        conn.execute("""INSERT INTO foreign_catalog.sync_state VALUES (1,%s,%s) ON CONFLICT (id)
            DO UPDATE SET file_hash=excluded.file_hash,data_hash=excluded.data_hash""",(file_hash,db_hash))
        return db_hash
