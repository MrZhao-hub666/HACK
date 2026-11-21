import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from typing import Literal

from .accounts import team
from .auth import browser_write, router as auth_router, workspace_user
from .channels import router
from .db import audit, database, initialize, one, utc
from .inbox import detail, edit, get_inquiry, merge, receive
from .intelligence import INTENTS
from .models import Company, Discovery, Event, InquiryEdit, Merge, Note, Reply
from .prospects import discover, host, save_company, valid_url
from .seed import seed


@asynccontextmanager
async def lifespan(app):
    initialize()
    seed()
    yield


app = FastAPI(title="冠英 · 海外销售工作台", version="1.0.0", lifespan=lifespan)
app.include_router(router)
app.include_router(auth_router)
business = APIRouter(dependencies=[Depends(workspace_user), Depends(browser_write)])


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/auth/"):
        return JSONResponse({"detail": "请核对账号格式和密码长度"}, status_code=422)
    return await request_validation_exception_handler(request, exc)


@app.get("/api/health")
def health():
    with database() as db:
        db.execute("SELECT 1 FROM inquiries LIMIT 1").fetchone()
    return {"status": "ok"}


@business.get("/api/config")
def config():
    with database() as db:
        sales = team(db)
        sync = {
            r["provider"]: dict(r) for r in db.execute("SELECT * FROM channel_sync")
        }
    return {
        "team": sales,
        "intents": INTENTS,
        "live_search": bool(os.getenv("BRAVE_API_KEY")),
        "receivers": [
            {
                "id": k,
                "name": name,
                "configured": all(os.getenv(x) for x in keys),
                "sync": sync.get(k),
            }
            for k, name, keys in [
                (
                    "meta",
                    "Facebook / Messenger",
                    ["META_APP_SECRET", "META_PAGE_ID", "META_VERIFY_TOKEN"],
                ),
                (
                    "wechat",
                    "微信客服",
                    ["WX_AES_KEY", "WX_TOKEN", "WX_CORP_ID", "WX_KF_SECRET"],
                ),
            ]
        ],
        "llm": bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL")),
        "demo": os.getenv("ENABLE_SIMULATOR", "1") == "1",
    }


@business.post("/api/discovery/search")
def discovery(req: Discovery):
    return discover(req)


class NewCompany(Company):
    source: Literal["销售录入", "已核验样例", "实时网页搜索"] = "销售录入"
    checked: str = Field(default="", max_length=32)


@business.get("/api/companies")
def companies():
    with database() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT * FROM companies WHERE saved=1 ORDER BY id DESC"
            )
        ]


@business.post("/api/companies")
def adopt(req: NewCompany):
    with database(True) as db:
        return save_company(
            db, req.model_dump(exclude={"source", "checked"}), req.source, req.checked
        )


@business.put("/api/companies/{ident}")
def company_edit(ident: int, req: Company):
    data = req.model_dump()
    for key in ("website", "social", "evidence_url"):
        valid_url(data[key])
    data["domain"] = host(data["website"])
    with database(True) as db:
        one(db, "SELECT id FROM companies WHERE id=?", (ident,))
        try:
            db.execute(
                "UPDATE companies SET reviewed=1,"
                + ",".join(f"{k}=?" for k in data)
                + " WHERE id=?",
                [*data.values(), ident],
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "该官网已关联其他买家") from exc
        return one(db, "SELECT * FROM companies WHERE id=?", (ident,))


@business.post("/api/demo/inquiries")
def simulate(event: Event, user=Depends(workspace_user)):
    if os.getenv("ENABLE_SIMULATOR", "1") != "1":
        raise HTTPException(403, "模拟入口已关闭")
    return receive(
        event.model_copy(update={"account": "demo:" + event.account}),
        "模拟渠道",
        actor=user["display_name"],
    )


@business.post("/api/inquiries/manual")
def manual(event: Event, user=Depends(workspace_user)):
    return receive(
        event.model_copy(update={"account": "manual:" + event.account}),
        "销售补录",
        actor=user["display_name"],
    )


@business.get("/api/inquiries")
def inquiries():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone(timedelta(hours=8)))
    start = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    with database() as db:
        return [
            dict(r)
            for r in db.execute(
                """
        SELECT i.*, c.name AS company,
          EXISTS(SELECT 1 FROM messages u WHERE u.inquiry_id=i.id AND u.answered=0) AS unanswered,
          EXISTS(SELECT 1 FROM messages n WHERE n.inquiry_id=i.id AND n.at>=? AND n.at<?
                 AND n.answered=0) AS night_unanswered,
          (SELECT group_concat(DISTINCT ch.channel) FROM messages ch WHERE ch.inquiry_id=i.id) AS all_channels,
          m.channel,m.body AS preview,m.origin,m.features,
          (SELECT count(*) FROM messages WHERE inquiry_id=i.id) AS message_count
        FROM inquiries i LEFT JOIN companies c ON c.id=i.company_id
        JOIN messages m ON m.id=(SELECT id FROM messages WHERE inquiry_id=i.id ORDER BY at DESC,id DESC LIMIT 1)
        WHERE merged_into IS NULL ORDER BY i.last_in DESC,i.id DESC""",
                (utc(start), utc(start + timedelta(hours=12))),
            )
        ]


@business.get("/api/inquiries/{ident}")
def inquiry(ident: int):
    with database() as db:
        return detail(db, ident)


@business.patch("/api/inquiries/{ident}")
def update(ident: int, req: InquiryEdit, user=Depends(workspace_user)):
    with database(True) as db:
        return edit(db, ident, req, user["display_name"])


@business.post("/api/inquiries/{ident}/notes")
def note(ident: int, req: Note, user=Depends(workspace_user)):
    with database(True) as db:
        get_inquiry(db, ident)
        audit(db, ident, user["display_name"], "跟进备注", req.text)
        return detail(db, ident)


@business.post("/api/inquiries/{ident}/reply")
def reply(ident: int, req: Reply, user=Depends(workspace_user)):
    with database(True) as db:
        item = get_inquiry(db, ident)
        latest = db.execute(
            "SELECT max(id) FROM messages WHERE inquiry_id=?", (ident,)
        ).fetchone()[0]
        if req.through_message_id is not None and latest != req.through_message_id:
            raise HTTPException(409, "有新来信，请核对最新消息后再登记回复")
        db.execute("UPDATE messages SET answered=1 WHERE inquiry_id=?", (ident,))
        db.execute(
            "UPDATE inquiries SET replied=?,owner=?,state='等客户补充' WHERE id=?",
            (utc(), item["owner"] or user["display_name"], ident),
        )
        audit(db, ident, user["display_name"], "登记人工回复", req.text)
        return detail(db, ident)


@business.post("/api/inquiries/{ident}/merge")
def link(ident: int, req: Merge, user=Depends(workspace_user)):
    with database(True) as db:
        return merge(db, ident, req.target_id, user["display_name"])


app.include_router(business)

web = Path(__file__).resolve().parent.parent / "web" / "dist"
if web.is_dir():
    app.mount("/", StaticFiles(directory=web, html=True), name="workbench")
