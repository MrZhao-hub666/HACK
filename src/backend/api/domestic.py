"""Read MediaCrawler exports as evidence for domestic prospect discovery."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, ValidationError

from .auth import workspace_user
from .db import database, initialize, one, utc
from .intelligence import extract
from .inbox import receive
from .models import Company, Event, Input
from .prospects import save_company

router = APIRouter(prefix="/api/domestic", tags=["国内线索"])
Platform = Literal["dy", "xhs"]
Signal = Literal["求购", "供应推广", "待判断"]
LABELS = {"dy": "抖音", "xhs": "小红书"}
MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 5000
FILES = re.compile(
    r"^(douyin|dy|xhs|xiaohongshu)/json/([\w.-]*(?:contents|comments)[\w.-]*\.json)$",
    re.I,
)
ID = re.compile(r"[a-zA-Z0-9_-]{1,100}")
PRODUCT = re.compile(
    r"刹车片|制动片|制动衬片|摩擦片|刹车蹄|brake\s*(?:pads?|linings?|shoes?)|WVA[\s-]*\d+",
    re.I,
)
WANT = re.compile(
    r"求购|求报价|请报价|要报价|询价|求推荐.{0,6}(?:厂家|供应商)|找.{0,4}(?:供应商|货源)|需(?:要|采购)|想买|多少钱|怎么卖|怎么报|什么价|采购.{0,10}(?:套|片|刹车|制动)|looking for|need to buy|need.{0,10}\d|please quote|request for quot",
    re.I,
)
OFFER = re.compile(
    r"厂家直销|工厂直供|欢迎询价|欢迎采购|我[们家]+.{0,5}(?:供应|生产)|专业生产|现货供应|we (?:supply|sell)|for sale",
    re.I,
)
NEGATIVE = re.compile(
    r"(?:不再|无需|不需要|不想|暂不|不求购|不采购).{0,12}(?:采购|买|刹车片|制动片|报价)|已(?:经)?(?:买到|购得|找到供应商)|停止采购",
    re.I,
)


class Adopt(Input):
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(default="", max_length=80)


class LiveSearch(Input):
    id: UUID
    q: str = Field(min_length=1, max_length=180)
    platform: Platform | None = None


class LiveChannel(Input):
    platform: Platform
    status: Literal["queued", "running", "login", "complete", "failed"]
    count: int | None = None
    error: str | None = None


class LiveJob(Input):
    id: UUID
    q: str
    status: Literal["running", "complete"]
    channels: list[LiveChannel]


def identify_file(path):
    clean = path.replace("\\", "/")
    match = FILES.fullmatch(clean)
    if not match:
        return None
    return ("dy" if match[1].lower() in ("dy", "douyin") else "xhs", clean)


def upstream_request(path, params=None, payload=None):
    root = os.getenv("MEDIACRAWLER_URL", "").strip().rstrip("/")
    if not root:
        raise HTTPException(503, "尚未配置 MediaCrawler WebUI 地址，可先导入 JSON。")
    try:
        with httpx.Client(timeout=12, trust_env=False) as client:
            with client.stream(
                "GET" if payload is None else "POST",
                root + path,
                params=params,
                json=payload,
            ) as res:
                res.raise_for_status()
                data = bytearray()
                for chunk in res.iter_bytes(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise HTTPException(
                            413, "单次读取上限为 4 MiB，请拆分导出文件。"
                        )
        return json.loads(data.decode("utf-8-sig"))
    except httpx.HTTPStatusError as exc:
        if path.startswith("/api/workbench/searches"):
            if exc.response.status_code == 409:
                raise HTTPException(409, "采集任务正在运行或尚未完成，请稍后重试。") from exc
            if exc.response.status_code == 404:
                message = (
                    "MediaCrawler 尚未启用工作台实时采集接口。"
                    if payload is not None
                    else "找不到采集任务，请重新搜索。"
                )
                raise HTTPException(404, message) from exc
        raise HTTPException(
            502, "无法读取 MediaCrawler 数据，请检查地址、服务和 JSON 导出。"
        ) from exc
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, RecursionError) as exc:
        raise HTTPException(
            502, "无法读取 MediaCrawler 数据，请检查地址、服务和 JSON 导出。"
        ) from exc


def read_upstream(endpoint, params=None):
    return upstream_request("/api/data/" + endpoint, params)


def live_job(path, payload=None):
    try:
        return LiveJob.model_validate(upstream_request(path, payload=payload))
    except ValidationError as exc:
        raise HTTPException(502, "MediaCrawler 返回了未知的采集状态。") from exc


def files():
    payload = read_upstream("files", {"file_type": "json"})
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise HTTPException(502, "MediaCrawler 返回了未知的文件清单格式。")
    items = []
    for entry in payload["files"]:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            result = identify_file(entry["path"])
            if result:
                items.append(
                    {
                        "platform": result[0],
                        "path": result[1],
                        "count": entry.get("record_count"),
                    }
                )
    return items


def string(row, key):
    value = row.get(key)
    return str(value).strip() if type(value) in (str, int) else ""


def timestamp(value):
    try:
        num = int(value)
        if num >= 10**12:
            num /= 1000
        if num > 0:
            return utc(datetime.fromtimestamp(num, timezone.utc))
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return ""


def normalize(platform, row):
    if not isinstance(row, dict):
        return None
    parent = string(row, "aweme_id" if platform == "dy" else "note_id")
    if not ID.fullmatch(parent):
        return None
    is_comment = "comment_id" in row
    key = string(row, "comment_id") if is_comment else parent
    if not ID.fullmatch(key):
        return None
    if is_comment:
        body = string(row, "content")
    else:
        body = "\n".join(
            dict.fromkeys(filter(None, (string(row, "title"), string(row, "desc"))))
        )
    if not body or len(body) > 12000:
        return None
    return (
        platform,
        "comment" if is_comment else "post",
        key,
        parent,
        body,
        string(row, "source_keyword")[:180],
        timestamp(row.get("create_time") or row.get("time")),
    )


def validate_rows(rows):
    if not isinstance(rows, list):
        raise HTTPException(422, "需要 MediaCrawler 导出的 JSON 数组。")
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, "单文件支持 5000 条记录，请拆分导出。")


def store_signals(db, platform, rows, demo=False, search_id=None):
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    for item in rows:
        values = normalize(platform, item)
        if values is None:
            stats["skipped"] += 1
            continue
        previous = db.execute(
            """SELECT id,parent_id,body,keyword,published FROM domestic_signals
              WHERE platform=%s AND kind=%s AND external_id=%s AND demo=%s""",
            (*values[:3], int(demo)),
        ).fetchone()
        if previous is None:
            signal_id = db.execute(
                """INSERT INTO domestic_signals(platform,kind,external_id,parent_id,body,keyword,published,demo)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (*values, int(demo)),
            ).fetchone()["id"]
            stats["inserted"] += 1
        else:
            signal_id = previous["id"]
            if tuple(previous[k] for k in ("parent_id", "body", "keyword", "published")) != values[3:]:
                db.execute(
                    """UPDATE domestic_signals SET parent_id=%s,body=%s,keyword=%s,published=%s
                       WHERE id=%s""",
                    (*values[3:], signal_id),
                )
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        if search_id:
            db.execute(
                "INSERT INTO domestic_search_results VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (search_id, signal_id),
            )
    return stats


def ingest(platform, rows, demo=False):
    validate_rows(rows)
    with database(True) as db:
        return store_signals(db, platform, rows, demo)


def sync(path):
    result = identify_file(path)
    if not result:
        raise HTTPException(422, "请选择抖音或小红书的内容、评论 JSON 文件。")
    return ingest(
        result[0],
        read_upstream("files/" + quote(result[1], safe="/"), {"preview": "false"}),
    )


def import_export(platform, document):
    if len(document) > MAX_BYTES:
        raise HTTPException(413, "单个文件不能超过 4 MiB。")
    try:
        rows = json.loads(document.decode("utf-8-sig"))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "文件不是有效的 UTF-8 JSON。") from exc
    return ingest(platform, rows)


def examples():
    if os.getenv("ENABLE_SIMULATOR", "1") != "1":
        raise HTTPException(403, "测试样例入口已关闭。")
    dy = ingest(
        "dy",
        [
            {"aweme_id": "demo1", "desc": "演示维修站分享重卡刹车片的更换记录。"},
            {
                "aweme_id": "demo1",
                "comment_id": "demo2",
                "content": "我们车队需要 80 套，请报价。",
            },
        ],
        True,
    )
    xhs = ingest(
        "xhs",
        [
            {
                "note_id": "demo3",
                "title": "求购 WVA 29087 刹车片",
                "desc": "维修厂想买 40 套。",
            },
            {"note_id": "demo4", "desc": "重卡刹车片厂家直销，欢迎询价。"},
        ],
        True,
    )
    return {key: dy[key] + xhs[key] for key in dy}


JOINED = """SELECT s.*, coalesce(p.body,'') AS parent_text,m.inquiry_id FROM domestic_signals s
    LEFT JOIN messages m ON s.demo=0 AND s.kind='comment' AND m.channel=s.platform
       AND m.account='mediacrawler' AND m.event_id=s.external_id
    LEFT JOIN domestic_signals p ON s.kind='comment' AND p.kind='post'
      AND p.platform=s.platform AND p.external_id=s.parent_id AND p.demo=s.demo"""


def classify(body, parent):
    if OFFER.search(body):
        return "供应推广"
    if (
        WANT.search(body)
        and PRODUCT.search(body + " " + parent)
        and not NEGATIVE.search(body)
    ):
        return "求购"
    return "待判断"


def owned(row):
    configured = os.getenv("MEDIACRAWLER_OWN_POSTS", "")
    return (
        not row["demo"]
        and row["kind"] == "comment"
        and (
            row["platform"] + ":" + row["parent_id"]
            in {x.strip() for x in configured.split(",")}
        )
    )


def describe(row):
    body = row["body"]
    signal = classify(body, row["parent_text"])
    features = extract(body)
    url = (
        "https://www.douyin.com/video/"
        if row["platform"] == "dy"
        else "https://www.xiaohongshu.com/explore/"
    ) + row["parent_id"]
    return {
        **dict(row),
        "signal": signal,
        "source_url": "" if row["demo"] else url,
        "codes": features["codes"],
        "quantities": features["quantities"],
        "owned": owned(row),
    }


LIVE_PATH = "/api/workbench/searches"


@router.post("/searches", status_code=202)
def start_live(req: LiveSearch):
    return live_job(LIVE_PATH, req.model_dump(mode="json"))


@router.get("/searches/{ident}")
def get_live(ident: UUID):
    return live_job(f"{LIVE_PATH}/{ident}")


@router.post("/searches/{ident}/import")
def import_live(ident: UUID):
    key = str(ident)
    with database() as db:
        existing = db.execute(
            "SELECT record_count FROM domestic_search_imports WHERE id=%s", (key,)
        ).fetchone()
        if existing:
            return {"count": existing["record_count"]}
    job = get_live(ident)
    if job.status != "complete":
        raise HTTPException(409, "采集尚未结束。")
    batches = {}
    for channel in job.channels:
        if channel.status == "complete":
            rows = upstream_request(f"{LIVE_PATH}/{ident}/records/{channel.platform}")
            validate_rows(rows)
            batches[channel.platform] = rows
    if not batches:
        raise HTTPException(502, "所有平台采集均失败。")

    with database(True) as db:
        inserted = db.execute(
            "INSERT INTO domestic_search_imports VALUES (%s,0) ON CONFLICT DO NOTHING", (key,)
        ).rowcount
        if inserted:
            for platform, rows in batches.items():
                store_signals(db, platform, rows, search_id=key)
            db.execute(
                """UPDATE domestic_search_imports SET record_count=(
                     SELECT count(*) FROM domestic_search_results WHERE search_id=%s
                   ) WHERE id=%s""",
                (key, key),
            )
        return {"count": db.execute(
            "SELECT record_count FROM domestic_search_imports WHERE id=%s", (key,)
        ).fetchone()["record_count"]}


@router.get("/signals")
def search(
    q: str = Query("", max_length=180),
    platform: Platform | None = None,
    signal: Signal | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    search_id: Annotated[UUID | None, Query()] = None,
    real_only: bool = False,
):
    sql = (
        JOINED
        + """ WHERE (%(platform)s::text IS NULL OR s.platform=%(platform)s)
        AND (NOT %(real_only)s OR s.demo=0)
        AND (%(search_id)s::text IS NULL OR EXISTS (
            SELECT 1 FROM domestic_search_results r
            WHERE r.search_id=%(search_id)s AND r.signal_id=s.id
        )) AND
        (strpos(lower(s.body),lower(%(q)s)) > 0 OR strpos(lower(s.keyword),lower(%(q)s)) > 0
         OR strpos(lower(coalesce(p.body,'')),lower(%(q)s)) > 0 OR strpos(lower(coalesce(p.keyword,'')),lower(%(q)s)) > 0)
        ORDER BY s.published DESC,s.id DESC"""
    )
    items = []
    total = 0
    with database() as db:
        for row in db.execute(
            sql,
            {
                "platform": platform, "q": "" if search_id else q.strip(),
                "search_id": str(search_id) if search_id else None,
                "real_only": real_only,
            },
        ):
            if signal and classify(row["body"], row["parent_text"]) != signal:
                continue
            if offset <= total < offset + limit:
                items.append(describe(row))
            total += 1
        indexed = total > 0 or db.execute(
            "SELECT 1 FROM domestic_signals WHERE (NOT %s OR demo=0) LIMIT 1",
            (real_only,),
        ).fetchone() is not None
    index_state = "indexed"
    if not indexed:
        index_state = (
            "awaiting_sync" if os.getenv("MEDIACRAWLER_URL", "").strip() else "unconfigured"
        )
    return {"items": items, "total": total, "index_state": index_state}


@router.post("/signals/{ident}/adopt")
def adopt(ident: int, req: Adopt, user=Depends(workspace_user)):
    with database(True) as db:
        signal = describe(one(db, JOINED + " WHERE s.id=%s", (ident,)))
        if signal["company_id"]:
            return {"company_id": signal["company_id"]}
        if signal["demo"]:
            raise HTTPException(422, "演示样例不写入正式客户档案。")
        company = Company(
            name=req.name,
            country=req.country,
            evidence=signal["body"][:2000],
            evidence_url=signal["source_url"],
            next_action="联系企业核实采购权限与需求有效期",
        )
        saved = save_company(
            db,
            company.model_dump(),
            "MediaCrawler · " + LABELS[signal["platform"]],
            owner=user["display_name"],
        )
        db.execute(
            "UPDATE domestic_signals SET company_id=%s WHERE id=%s", (saved["id"], ident)
        )
        return {"company_id": saved["id"]}


@router.post("/signals/{ident}/inquiry")
def as_inquiry(ident: int, user=Depends(workspace_user)):
    with database() as db:
        row = describe(one(db, JOINED + " WHERE s.id=%s", (ident,)))
    if not owned(row):
        raise HTTPException(422, "只有已配置为企业自有作品的评论可转入收件箱。")
    if not row["published"] or len(row["body"]) > 8000:
        raise HTTPException(422, "请核实原评论的发布时间及长度后在消息补录页登记。")
    source = LABELS[row["platform"]] + "评论"
    event = Event(
        channel=row["platform"],
        account="mediacrawler",
        event_id=row["external_id"],
        thread_key=row["parent_id"] + ":" + row["external_id"],
        sender=source + " · " + row["external_id"],
        body=row["body"],
        attachment=row["source_url"],
        occurred_at=row["published"],
    )
    return receive(
        event, source + " · MediaCrawler（销售核实）", actor=user["display_name"]
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="维护抖音和小红书线索数据")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="列出 MediaCrawler WebUI 的可同步导出")
    sync_file = commands.add_parser("sync", help="同步一份 WebUI 导出")
    sync_file.add_argument("path")
    import_file = commands.add_parser("import", help="从文件或标准输入导入 JSON")
    import_file.add_argument("platform", choices=LABELS)
    import_file.add_argument("filename", help="使用 - 从标准输入读取")
    commands.add_parser("examples", help="载入带标记的演示线索")
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            result = files()
        else:
            initialize()
            if args.command == "sync":
                result = sync(args.path)
            elif args.command == "import":
                try:
                    if args.filename == "-":
                        document = sys.stdin.buffer.read(MAX_BYTES + 1)
                    else:
                        with open(args.filename, "rb") as source:
                            document = source.read(MAX_BYTES + 1)
                except OSError:
                    parser.exit(1, "无法读取导出文件。\n")
                result = import_export(args.platform, document)
            else:
                result = examples()
    except HTTPException as exc:
        parser.exit(1, f"{exc.detail}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
