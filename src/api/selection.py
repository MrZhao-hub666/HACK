"""Connect authenticated sales inquiries to the catalogue service."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.backend.app import main as catalogue
from .db import database
from .inbox import get_inquiry

router = APIRouter()


class Selection(BaseModel):
    customer_words: str = Field(default="", max_length=3000)


class Draft(BaseModel):
    spec_id: str = Field(min_length=1, max_length=180)
    quantity: int = Field(gt=0, le=100000000)
    unit: str = Field(min_length=1, max_length=20)
    request_key: UUID


@router.post("/api/inquiries/{ident}/selection")
def select(ident: int, req: Selection):
    with database() as db:
        get_inquiry(db, ident)
        rows = db.execute("""
            SELECT role, text FROM (
                SELECT 'customer' AS role, body AS text, at, id FROM messages WHERE inquiry_id=%s
                UNION ALL
                SELECT 'sales', detail, at, id FROM history WHERE inquiry_id=%s AND action='登记人工回复'
            ) AS conversation WHERE trim(text)<>'' ORDER BY at DESC, role DESC, id DESC LIMIT 30
        """, (ident, ident)).fetchall()
    turns = [{"role": row["role"], "text": row["text"][i:i+3000]}
             for row in reversed(rows) for i in range(0, len(row["text"]), 3000)]
    if words := req.customer_words.strip():
        turns.append({"role": "customer", "text": words})
    if not any(t["role"] == "customer" for t in turns[-30:]):
        raise HTTPException(422, "请先录入客户原话或补充旧件信息")
    return catalogue.analyze(catalogue.Inquiry(turns=turns[-30:]))


@router.post("/api/inquiries/{ident}/selection/quotes")
def create_quote(ident: int, req: Draft):
    with database(True) as db:
        get_inquiry(db, ident)
        workspace = db.execute("SELECT value FROM cursors WHERE name='selection-workspace'").fetchone()["value"]
        quote = catalogue.save_quote(db, catalogue.Quote(**req.model_dump(), inquiry_id=ident, workspace=workspace))
        db.execute("INSERT INTO inquiry_quotes(inquiry_id,quote_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (ident,quote["id"]))
        return quote


@router.get("/api/inquiries/{ident}/selection/quotes")
def prior_quotes(ident: int):
    with database() as db:
        get_inquiry(db, ident)
        rows = db.execute("""
            WITH RECURSIVE linked(id) AS (
                SELECT %s::integer UNION SELECT i.id FROM inquiries i JOIN linked l ON i.merged_into=l.id
            )
            SELECT q.id,q.snapshot FROM linked JOIN inquiry_quotes k ON k.inquiry_id=linked.id
            JOIN quote_draft q ON q.id=k.quote_id ORDER BY q.id DESC LIMIT 25
        """, (ident,)).fetchall()
    return [dict(id=row["id"], **row["snapshot"]) for row in rows]


@router.get("/api/selection/media/{kind}/{key:path}")
def image(kind: Literal["photo", "page", "observation", "domestic-picture", "evidence"], key: str):
    readers = {"photo": catalogue.photo, "page": catalogue.source_page, "observation": catalogue.source_row,
               "domestic-picture": catalogue.domestic_picture}
    if kind == "evidence":
        if key not in {"8", "13"}:
            raise HTTPException(404)
        return catalogue.evidence(int(key))
    return readers[kind](key)
