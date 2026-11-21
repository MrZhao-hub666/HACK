"""Connect authenticated sales inquiries to the catalogue service."""
import os
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

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


def catalogue(method, path, payload=None):
    url = os.getenv("SELECTOR_URL", "http://127.0.0.1:8000").rstrip("/") + path
    try:
        with httpx.Client(timeout=httpx.Timeout(45, connect=4), trust_env=False) as client:
            response = client.request(method, url, json=payload)
    except httpx.RequestError:
        raise HTTPException(503, "选型服务暂不可用，请检查目录后端后重试") from None
    if response.status_code in (404, 409, 422):
        try:
            message = response.json().get("detail")
        except (ValueError, AttributeError):
            message = None
        raise HTTPException(response.status_code, message if isinstance(message, str) else "请核对目录参数")
    if not response.is_success:
        raise HTTPException(502, "产品目录服务处理失败，请稍后重试")
    return response


@router.post("/api/inquiries/{ident}/selection")
def select(ident: int, req: Selection):
    with database() as db:
        get_inquiry(db, ident)
        rows = db.execute("""
            SELECT role, text FROM (
                SELECT 'customer' AS role, body AS text, at, id FROM messages WHERE inquiry_id=?
                UNION ALL
                SELECT 'sales', detail, at, id FROM history WHERE inquiry_id=? AND action='登记人工回复'
            ) WHERE trim(text)<>'' ORDER BY at DESC, role DESC, id DESC LIMIT 30
        """, (ident, ident)).fetchall()
    turns = [{"role": row["role"], "text": row["text"][i:i+3000]}
             for row in reversed(rows) for i in range(0, len(row["text"]), 3000)]
    if words := req.customer_words.strip():
        turns.append({"role": "customer", "text": words})
    if not any(t["role"] == "customer" for t in turns[-30:]):
        raise HTTPException(422, "请先录入客户原话或补充旧件信息")
    return catalogue("POST", "/api/match", {"turns": turns[-30:], "use_model": False}).json()


@router.post("/api/inquiries/{ident}/selection/quotes")
def create_quote(ident: int, req: Draft):
    with database() as db:
        get_inquiry(db, ident)
        workspace = db.execute("SELECT value FROM cursors WHERE name='selection-workspace'").fetchone()[0]
    return catalogue("POST", "/api/quotes", {**req.model_dump(mode="json"), "inquiry_id": ident, "workspace": workspace}).json()


@router.get("/api/inquiries/{ident}/selection/quotes")
def prior_quotes(ident: int):
    with database() as db:
        get_inquiry(db, ident)
        workspace = db.execute("SELECT value FROM cursors WHERE name='selection-workspace'").fetchone()[0]
        merged = db.execute("""
            WITH RECURSIVE linked(id) AS (
                SELECT ? UNION SELECT i.id FROM inquiries i JOIN linked l ON i.merged_into=l.id
            ) SELECT id FROM linked
        """, (ident,)).fetchall()
    return catalogue("POST", "/api/quote-drafts/search", {"workspace": workspace, "inquiries": [r[0] for r in merged]}).json()


@router.get("/api/selection/media/{kind}/{key:path}")
def image(kind: Literal["photo", "page", "observation", "domestic-picture", "evidence"], key: str):
    if not key or any(p in ("", ".", "..") for p in key.split("/")) or "\\" in key:
        raise HTTPException(404, "图片不存在")
    response = catalogue("GET", f"/api/{kind}/{quote(key, safe='/')}")
    mime = response.headers.get("content-type", "").split(";")[0]
    if mime not in {"image/png", "image/jpeg"}:
        raise HTTPException(502, "目录图片格式异常")
    return Response(response.content, media_type=mime)
