"""Transactional import and atomic export of the two managed Excel sheets."""
import hashlib
import io
import json
import os
import shutil
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from .catalog import BOOK, SHEETS, LEGACY_FIELDS, db, order_specs, photo_path, photo_roots

def digest(data):
    return hashlib.sha256(data).hexdigest()

def normalized(rows):
    specs = order_specs(rows["产品规格"])
    media = sorted(rows["图片索引"], key=lambda row: (row["path"],row["spec_id"] or ""))
    return {"产品规格": specs, "图片索引": media}

def from_db(conn):
    return normalized({name: conn.execute(f"SELECT {', '.join(fields)} FROM {table}").fetchall()
                       for name, (table,fields) in SHEETS.items()})

def data_hash(rows):
    return digest(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode())

def cell_text(value):
    if value is None or value == "":
        return None
    if isinstance(value,(date,datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip() or None

def from_book(wb):
    result, keys = {}, set()
    roots = photo_roots()
    for name, (_,fields) in SHEETS.items():
        sheet = wb[name]
        headers = list(next(sheet.values))
        legacy = name=="产品规格" and headers==list(LEGACY_FIELDS.values())
        if headers != list(fields.values()) and not legacy:
            raise ValueError(f"{name} 表头发生变化，请恢复模板中的列名和顺序")
        records = []
        for i, values in enumerate(sheet.values, 1):
            if i == 1 or not any(v is not None for v in values):
                continue
            row = dict.fromkeys(fields)
            row.update({k:cell_text(v) for k,v in zip(fields, values)})
            if any(v and v.startswith("=") for v in row.values()):
                raise ValueError(f"{name} 第 {i} 行需要填写实际值")
            if name == "产品规格":
                if not row["name"] and not row["code"]:
                    raise ValueError(f"第 {i} 行缺少型号名称或冠英编号")
                key = row["spec_id"] or "SPEC-"+uuid.uuid4().hex
                if key in keys:
                    raise ValueError(f"第 {i} 行的规格唯一键重复：{key}")
                row["spec_id"] = key
                keys.add(key)
                if row["price"]:
                    try:
                        price = Decimal(row["price"])
                        if not price.is_finite() or price < 0:
                            raise InvalidOperation
                    except InvalidOperation:
                        raise ValueError(f"第 {i} 行单价无效") from None
                if row["valid_until"]:
                    date.fromisoformat(row["valid_until"])
            else:
                if row["spec_id"] and row["spec_id"] not in keys:
                    raise ValueError(f"图片第 {i} 行引用了不存在的规格")
                if not row["path"]:
                    raise ValueError(f"图片第 {i} 行缺少路径")
                if photo_path(row["path"], roots) is None:
                    raise ValueError(f"图片第 {i} 行路径无效")
            records.append(row)
        result[name] = records
    if len({(m["path"],m["spec_id"]) for m in result["图片索引"]}) != len(result["图片索引"]):
        raise ValueError("同一规格的图片路径重复")
    return normalized(result)

def save_db(conn, rows):
    conn.execute("DELETE FROM catalog_media")
    conn.execute("DELETE FROM catalog_spec")
    conn.execute("DELETE FROM catalog_product")
    with conn.cursor() as cur:
        codes = {r["code"] for r in rows["产品规格"] if r["code"]}
        cur.executemany("INSERT INTO catalog_product VALUES (%s)", [(code,) for code in codes])
        for sheet, (table,fields) in SHEETS.items():
            cur.executemany(f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})",
                            [[row[k] for k in fields] for row in rows[sheet]])

def gap_rows(specs):
    for spec in specs:
        needs=[]
        if spec["market"]=="待确认":
            needs.append("市场归属")
        if not spec["code"]:
            needs.append("冠英编号")
        if (spec["page_refs"] or "").startswith("cn-") and spec["kind"] in ("盘式","鼓式") and not spec["fit_notes"]:
            needs.append("适配车型")
        if spec["kind"]=="盘式" and not spec["thickness"]:
            needs.append("标称厚度")
        for key,label in (("material","材质"),("sku","可售 SKU"),("price","有效价目")):
            if not spec[key]:
                needs.append(label)
        if needs:
            yield (spec["market"],spec["spec_id"],spec["name"],spec["source"],"、".join(needs))

def write_snapshot(wb, rows, old_hash, destination=None, source=None):
    source=source or BOOK
    for name, (_,fields) in SHEETS.items():
        sheet = wb[name]
        for n,label in enumerate(fields.values(),1):
            sheet.cell(1,n,label)
        if sheet.max_row > 1:
            sheet.delete_rows(2,sheet.max_row-1)
        for row in rows[name]:
            sheet.append([row[k] for k in fields])
        for cells in sheet.iter_rows(min_row=2):
            for cell in cells:
                cell.number_format = "@"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.freeze_panes = "C2" if name == "产品规格" else "B2"
    if "待企业补充" in wb.sheetnames:
        sheet=wb["待企业补充"]
        if sheet.max_row>1:
            sheet.delete_rows(2,sheet.max_row-1)
        for row in gap_rows(rows["产品规格"]):
            sheet.append(row)
        sheet.auto_filter.ref=sheet.dimensions
    with tempfile.NamedTemporaryFile(dir=BOOK.parent, suffix=".sync-tmp.xlsx",delete=False) as temp:
        path = Path(temp.name)
    try:
        wb.save(path)
        updated = digest(path.read_bytes())
        if digest(source.read_bytes()) != old_hash:
            raise ValueError("Excel 在同步期间再次保存，将在下一轮重新读取")
        os.replace(path, destination or source)
        return updated
    finally:
        path.unlink(missing_ok=True)

def sync():
    if not BOOK.is_file():
        return "产品目录待导入"
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(400712)")
        conn.execute("LOCK TABLE catalog_product, catalog_spec, catalog_media IN SHARE ROW EXCLUSIVE MODE")
        state = conn.execute("SELECT * FROM catalog_sync WHERE id=1").fetchone()
        if not state:
            alternate=BOOK.with_name("冠英产品知识库-全目录.xlsx")
            if alternate.is_file() and BOOK.exists():
                initial=load_workbook(BOOK,read_only=True)
                try:
                    legacy=list(next(initial["产品规格"].values))==list(LEGACY_FIELDS.values())
                finally:
                    initial.close()
                if legacy:
                    conn.execute("INSERT INTO catalog_pending_excel VALUES(1,%s,%s) ON CONFLICT DO NOTHING",
                                 (digest(BOOK.read_bytes()),alternate.name))
        pending=conn.execute("SELECT * FROM catalog_pending_excel WHERE id=1").fetchone()
        active=BOOK
        message="已同步"
        if pending:
            alternate=BOOK.parent/pending["snapshot"]
            original_hash=digest(BOOK.read_bytes())
            if original_hash not in {pending["original_hash"],digest(alternate.read_bytes())}:
                raise ValueError("原工作簿在发布后被修改，请核对原表和全目录副本后合并")
            with tempfile.NamedTemporaryFile(dir=BOOK.parent,suffix=".sync-tmp.xlsx",delete=False) as f:
                replacement=Path(f.name)
            try:
                shutil.copyfile(alternate,replacement)
                os.replace(replacement,BOOK)
            except PermissionError:
                active=alternate
                message="全目录副本已同步，原工作簿待关闭"
            finally:
                replacement.unlink(missing_ok=True)
            if active==BOOK:
                conn.execute("DELETE FROM catalog_pending_excel WHERE id=1")
        raw = active.read_bytes()
        file_hash = digest(raw)
        current = from_db(conn)
        db_hash = data_hash(current)
        file_changed = not state or file_hash != state["file_hash"]
        db_changed = bool(state and db_hash != state["data_hash"])
        if not file_changed and not db_changed:
            return message
        wb = load_workbook(io.BytesIO(raw))
        try:
            legacy = list(next(wb["产品规格"].values))==list(LEGACY_FIELDS.values())
            if legacy and file_changed and any(r.get("page_refs") for r in current["产品规格"]):
                raise ValueError("当前数据库已按市场分册，旧模板缺少市场和来源页，不能覆盖现有目录")
            if legacy and state and db_changed:
                old={**current,"产品规格":[{k:r[k] for k in LEGACY_FIELDS} for r in current["产品规格"]]}
                if data_hash(old)==state["data_hash"]:
                    db_changed=False
            if file_changed:
                incoming = from_book(wb)
                # A workbook edit may correct product details, but a catalogued
                # spec keeps the market of its archived source document.
                archived = {r["spec_key"]: r["market"] for r in conn.execute("""
                    SELECT spec_key,min(reading->>'market') AS market
                    FROM catalog_observation GROUP BY spec_key
                    HAVING count(DISTINCT left(page_key,2))=1""")}
                for row in incoming["产品规格"]:
                    expected=archived.get(row["spec_id"])
                    if expected and row["market"]!=expected and not legacy:
                        raise ValueError(f'{row["spec_id"]} 的目录市场应为{expected}，请核对来源册')
                incoming_hash = data_hash(incoming)
                if (db_changed or (not state and current["产品规格"])) and incoming_hash != db_hash:
                    raise ValueError("数据库和 Excel 都有修改。请保留副本并合并差异后重试")
                if incoming_hash != db_hash:
                    save_db(conn,incoming)
                db_hash, current = incoming_hash, incoming
            # Write back only if the physical order or generated keys changed.
            needs_write = legacy or db_changed or any(
                list(wb[name].values)[1:] != [tuple(r[k] for k in fields) for r in current[name]]
                for name, (_,fields) in SHEETS.items())
            if not needs_write and "待企业补充" in wb.sheetnames:
                needs_write=list(wb["待企业补充"].values)[1:]!=list(gap_rows(current["产品规格"]))
            if needs_write:
                file_hash = write_snapshot(wb,current,file_hash,source=active)
            conn.execute("""INSERT INTO catalog_sync VALUES (1,%s,%s) ON CONFLICT (id)
                DO UPDATE SET file_hash=excluded.file_hash,data_hash=excluded.data_hash""",(file_hash,db_hash))
        finally:
            wb.close()
        return message

