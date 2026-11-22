"""Column order is shared by PostgreSQL, the API and the editable workbook."""
import re
from pathlib import Path

from .storage import db

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
PACK = ROOT / "鼓式刹车片照片等8个文件"
CATALOG_PHOTOS = DOCS / "materials/photos"
BOOK = DOCS / "冠英产品知识库.xlsx"
FIELDS = {
    "code": "冠英编号", "series": "系列", "name": "型号名称", "spec_id": "规格唯一键",
    "kind": "产品类型", "wva": "WVA", "bfmc": "BFMC", "fmsi": "FMSI",
    "brand": "车辆品牌", "vehicle": "车型", "axle": "车桥", "position": "位置",
    "outer_arc": "外弧 A", "inner_arc": "内弧 B", "width": "宽度 C", "thickness": "标称厚度 D",
    "holes": "孔数", "rivet": "铆钉规格", "supplier_ref": "供应商及料号",
    "status": "资料状态", "source": "资料出处", "material": "材质", "sku": "可售 SKU",
    "sale_unit": "计价单位", "price": "单价", "currency": "币种",
    "price_source": "价目依据", "valid_until": "价格有效至",
}
LEGACY_FIELDS = FIELDS.copy()
EXTRA_FIELDS = {
    "market":"目录市场", "section":"原册分区", "size_raw":"原册尺寸", "fit_notes":"适配车型原文",
    "arc_value":"弧形图示原值", "taper":"Taper 原值", "oe_ref":"OEM / OE 参考号",
    "catalog_ref":"Item / 原册料号", "reference_raw":"参考栏原文", "kit_ref":"修理包号",
    "lining_ref":"配套衬片号", "page_refs":"来源页索引", "comparison":"双册对照",
}
FIELDS.update(EXTRA_FIELDS)
MEDIA = {"spec_id": "关联规格键", "path": "资料包相对路径", "label": "图片说明"}
SHEETS = {"产品规格": ("catalog_spec", FIELDS), "图片索引": ("catalog_media", MEDIA)}

def photo_roots():
    return tuple(directory.resolve() for directory in (PACK, CATALOG_PHOTOS) if directory.is_dir())

def photo_path(relative_path, roots=None):
    relative = Path(relative_path)
    if relative.anchor or ".." in relative.parts or relative.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        return None
    for root in photo_roots() if roots is None else roots:
        candidate = root / relative
        if candidate.is_file():
            file = candidate.resolve()
            if file.is_relative_to(root):
                return file
    return None

def natural(value):
    return [int(x) if i % 2 else x.casefold() for i, x in enumerate(re.split(r"(\d+)", value or ""))]

def order_specs(rows):
    return sorted(rows, key=lambda r: (not bool(r.get("series")), natural(r.get("series")),
                  not bool(r.get("code")), natural(r.get("code") or r.get("name")),
                  natural(r.get("thickness")), natural(r["spec_id"])))

def init_db():
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(400710)")
        columns = ", ".join(f"{k} text" for k in FIELDS if k not in {"spec_id","code"})
        conn.execute("CREATE TABLE IF NOT EXISTS catalog_product (code text PRIMARY KEY)")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS catalog_spec (
            spec_id text PRIMARY KEY, code text REFERENCES catalog_product(code), {columns})""")
        for col in EXTRA_FIELDS:
            conn.execute(f"ALTER TABLE catalog_spec ADD COLUMN IF NOT EXISTS {col} text")
        conn.execute("""CREATE TABLE IF NOT EXISTS catalog_page (
            page_key text PRIMARY KEY, pdf_name text NOT NULL, pdf_page int NOT NULL,
            pdf_sha256 text NOT NULL, purpose text NOT NULL, ocr jsonb NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS catalog_observation (
            observation_id text PRIMARY KEY, page_key text NOT NULL REFERENCES catalog_page,
            spec_key text NOT NULL, bbox int[] NOT NULL, reading jsonb NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS catalog_observation_spec ON catalog_observation(spec_key)")
        conn.execute("""CREATE TABLE IF NOT EXISTS catalog_media (
            spec_id text REFERENCES catalog_spec(spec_id), path text NOT NULL, label text)""")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS catalog_media_attachment
            ON catalog_media(path,spec_id) NULLS NOT DISTINCT""")
        conn.execute("ALTER TABLE catalog_media DROP CONSTRAINT IF EXISTS catalog_media_pkey")
        conn.execute("""CREATE OR REPLACE VIEW catalog_reference AS
            SELECT s.spec_id, r.scheme,
              CASE WHEN r.scheme='supplier_ref' AND strpos(token,'|')>0
                   THEN trim(split_part(token,'|',1)) END AS supplier,
              CASE WHEN r.scheme='supplier_ref' AND strpos(token,'|')>0
                   THEN trim(substr(token,strpos(token,'|')+1)) ELSE trim(token) END AS number
            FROM catalog_spec s CROSS JOIN LATERAL (VALUES
              ('code',s.code),('wva',s.wva),('bfmc',s.bfmc),('fmsi',s.fmsi),
              ('supplier_ref',s.supplier_ref),('oe_ref',s.oe_ref),('catalog_ref',s.catalog_ref)) AS r(scheme,raw)
            CROSS JOIN LATERAL regexp_split_to_table(r.raw, E'[;；\\n]+') AS token
            WHERE trim(token)<>''""")
        conn.execute("CREATE INDEX IF NOT EXISTS catalog_spec_code ON catalog_spec(code)")
        conn.execute("""CREATE TABLE IF NOT EXISTS catalog_sync (
            id int PRIMARY KEY CHECK(id=1), file_hash text, data_hash text)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS catalog_pending_excel (
            id int PRIMARY KEY CHECK(id=1), original_hash text NOT NULL, snapshot text NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS quote_draft (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, created_at timestamptz DEFAULT now(),
            snapshot jsonb NOT NULL)""")
        conn.execute("ALTER TABLE quote_draft ADD COLUMN IF NOT EXISTS request_key uuid")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS quote_draft_request_key ON quote_draft(request_key)")
        from .archive import MANIFEST, restore
        restore(conn)
        if conn.execute("SELECT current_schema() AS s").fetchone()["s"]=="public":
            from .domestic import install as install_domestic
            install_domestic(conn)
            from .foreign import COUNTRIES, install, migrate_country_ids
            if not conn.execute("SELECT to_regclass('foreign_catalog.source') AS t").fetchone()["t"]:
                install(conn)
            else:
                conn.execute("SELECT pg_advisory_xact_lock(400713)")
                migrate_country_ids(conn)
                if MANIFEST.is_file() and not conn.execute("SELECT 1 FROM foreign_catalog.source LIMIT 1").fetchone():
                    install(conn)
                for _,table,_ in COUNTRIES.values():
                    conn.execute(f"ALTER TABLE foreign_catalog.{table} DROP COLUMN IF EXISTS inner_diameter")

