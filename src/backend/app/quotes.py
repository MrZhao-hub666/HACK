"""Create catalogue quote snapshots in the caller's transaction."""
import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import domestic
from .catalog import FIELDS
from .foreign import COUNTRIES, canonical_id, sales_fields


class QuoteLine(BaseModel):
    spec_id: str
    quantity: int = Field(gt=0, le=100000000)
    unit: str = Field(min_length=1, max_length=20)


class Quote(QuoteLine):
    workspace: UUID | None = None
    inquiry_id: int | None = Field(default=None, gt=0)
    request_key: UUID | None = None
    market: Literal["国内", "外贸", "待确认"] | None = None


def save_quote(conn, req: Quote):
    key = canonical_id(req.spec_id)
    workspace = str(req.workspace) if req.workspace else None
    request = dict(
        workspace=workspace, inquiry_id=req.inquiry_id, spec_id=key,
        quantity=req.quantity, unit=req.unit, market=req.market,
    )
    if req.request_key:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (str(req.request_key),),
        )
        saved = conn.execute(
            "SELECT id,snapshot FROM quote_draft WHERE request_key=%s",
            (req.request_key,),
        ).fetchone()
        if saved:
            if saved["snapshot"].get("request") != request:
                raise HTTPException(409, "该请求已用于其他报价，请重新选择")
            return dict(id=saved["id"], **saved["snapshot"])

    snapshot = quote_preview(conn, req)
    if req.inquiry_id:
        snapshot.update(inquiry_id=req.inquiry_id, workspace=workspace)
    if req.request_key:
        snapshot["request"] = request
    ref = conn.execute(
        "INSERT INTO quote_draft(snapshot,request_key) VALUES (%s,%s) RETURNING id",
        (Jsonb(snapshot), req.request_key),
    ).fetchone()
    return dict(id=ref["id"], **snapshot)


def quote_preview(conn, req: Quote):
    key = canonical_id(req.spec_id)
    part = domestic_part = None
    if re.fullmatch(r"DC[GP]\d{4}", key):
        domestic_part = conn.execute(
            "SELECT * FROM domestic_catalog.parts WHERE part_id=%s", (key,)
        ).fetchone()
        if domestic_part:
            key = domestic_part["legacy_key"]
    if re.fullmatch(r"F[EAJCKN][GP]\d{4}", key):
        table = COUNTRIES[key[1]][1]
        part = conn.execute(f"""
            SELECT t.*,s.legacy_key,s.pdf_order FROM foreign_catalog.{table} t
            JOIN foreign_catalog.source s USING(part_id) WHERE part_id=%s
        """, (key,)).fetchone()
        if part:
            key = part["legacy_key"]

    row = conn.execute("SELECT * FROM catalog_spec WHERE spec_id=%s", (key,)).fetchone()
    if not row:
        raise HTTPException(404, "规格不存在")
    if part:
        row.update(sales_fields(part))
    if domestic_part:
        row.update(domestic.sales_fields(domestic_part))
    if req.market and row["market"] != req.market:
        raise HTTPException(409, "目录市场已变动，请重新选择对应规格")

    required = ("sku", "material", "price", "currency", "sale_unit", "price_source", "valid_until")
    missing = [FIELDS[key] for key in required if not row[key]]
    if row["sale_unit"] and req.unit != row["sale_unit"]:
        missing.append("计价单位不一致")
    if row["valid_until"] and date.fromisoformat(row["valid_until"]) < date.today():
        missing.append("价目已过期")
    if row["status"] not in {"目录记录", "企业已核"}:
        missing.append("产品关系待核")
    total = None if missing else str(Decimal(row["price"]) * req.quantity)
    snapshot = dict(
        spec_id=row["spec_id"], code=row["code"], name=row["name"], sku=row["sku"],
        market=row["market"], source_pages=row["page_refs"], size=row["size_raw"],
        material=row["material"], quantity=req.quantity, unit=req.unit,
        unit_price=row["price"], total=total, currency=row["currency"],
        source=row["price_source"], valid_until=row["valid_until"],
        status="待核价" if missing else "报价草稿", missing=missing,
    )
    if domestic_part:
        snapshot["thickness"] = domestic_part["thickness"]
    return snapshot
