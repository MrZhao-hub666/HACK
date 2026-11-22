import asyncio
import logging
from collections import defaultdict
from typing import Literal
from io import BytesIO
import re
from functools import lru_cache
from hashlib import sha256
from contextlib import asynccontextmanager, suppress
from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

from .catalog import DOCS, FIELDS, db, init_db, order_specs, photo_path, photo_roots
from .match import Turn, extract, match
from .routing import route_inquiry
from .sync import sync
from .foreign import country_candidates, read_tables, sales_fields
from .foreign_sync import synchronize as sync_foreign
from .quotes import Quote, save_quote
from . import domestic

logger = logging.getLogger(__name__)
state = {"sync":"首次同步中"}

def refresh():
    errors = []
    for name, key, synchronize in (
        ("外贸目录", "foreign_revision", sync_foreign),
        ("国内目录", "domestic_revision", domestic.synchronize),
        ("产品知识库", "sync", sync),
    ):
        try:
            state[key] = synchronize()
        except PermissionError:
            errors.append(f"{name}文件已锁定，请关闭 Excel 后等待重试")
        except ValueError as exc:
            errors.append(f"{name}：{str(exc)[:180]}")
        except Exception:
            logger.exception("目录同步失败，目录为 %s", name)
            errors.append(f"{name}同步失败，请查看服务日志")
    if errors:
        state["sync"] = "；".join(errors)

async def watch():
    while True:
        await asyncio.sleep(4)
        await asyncio.to_thread(refresh)

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(refresh)
    task = asyncio.create_task(watch())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

router = APIRouter()

@lru_cache(maxsize=2048)
def photo_digest(path, modified, size):
    return sha256(path.read_bytes()).digest()

PHOTO_VIEW_LABELS = ("实拍三视图 · 正面", "实拍三视图 · 反面", "实拍三视图 · 侧面")

def catalog(prefixes=None,compact=False,marketed_only=False):
    with db() as conn:
        foreign={}
        domestic_parts=defaultdict(list)
        if conn.execute("SELECT current_schema() AS s").fetchone()["s"]=="public":
            foreign={r["legacy_key"]:r for group in read_tables(conn,prefixes).values() for r in group}
            for part in domestic.read_rows(conn,prefixes):
                domestic_parts[part["legacy_key"]].append(part)
        keys = None if prefixes is None else list(foreign.keys() | domestic_parts.keys())
        if marketed_only:
            keys = [row["spec_id"] for row in conn.execute("""
                SELECT spec_id FROM catalog_spec WHERE market IN ('国内','外贸')
                AND (%s::text[] IS NULL OR spec_id=ANY(%s))
            """, (keys, keys))]
        condition = "" if keys is None else " WHERE spec_id=ANY(%s)"
        args = None if keys is None else (keys,)
        columns="spec_id,code,name,series,brand,vehicle,axle,fit_notes,market,kind,source,width,thickness,holes" if compact else "*"
        rows=order_specs(conn.execute(f"SELECT {columns} FROM catalog_spec"+condition,args).fetchall())
        references=conn.execute("SELECT * FROM catalog_reference"+condition+" ORDER BY scheme,number",args).fetchall()
        images=[] if compact else conn.execute("SELECT * FROM catalog_media"+condition+" ORDER BY path",args).fetchall()
        observations=[] if compact else conn.execute("SELECT observation_id,spec_key,page_key FROM catalog_observation"+
            condition.replace("spec_id","spec_key")+" ORDER BY page_key,observation_id",args).fetchall()
    sources={}
    for o in observations:
        page=o["page_key"]
        sources.setdefault(o["spec_key"],[]).append(dict(label=("英文册 " if page.startswith("en") else "中文册 ")+str(int(page[-2:]))+" 页",
            page="/api/page/"+page,crop="/api/observation/"+o["observation_id"]))
    by_spec={}
    for ref in references:
        by_spec.setdefault(ref["spec_id"],[]).append(ref)
    albums, seen = {}, set()
    galleries = defaultdict(lambda: defaultdict(dict))
    roots = photo_roots() if images else ()
    for m in images:
        file = photo_path(m["path"], roots)
        if file is None:
            continue
        stat = file.stat()
        signature = (m["spec_id"], photo_digest(file,stat.st_mtime_ns,stat.st_size))
        if signature in seen:
            continue
        seen.add(signature)
        image = {"label": m["label"], "url": "/api/photo/" + quote(m["path"])}
        if m["label"] in PHOTO_VIEW_LABELS:
            folder = m["path"].rpartition("/")[0]
            galleries[m["spec_id"]][folder][m["label"]] = image
        else:
            albums.setdefault(m["spec_id"], []).append(image)
    result=[]
    for r in rows:
        r["references"]=by_spec.get(r["spec_id"],[])
        r["images"]=albums.get(r["spec_id"],[])
        for gallery in galleries.get(r["spec_id"], {}).values():
            if all(label in gallery for label in PHOTO_VIEW_LABELS):
                r["photo_views"] = [gallery[label] for label in PHOTO_VIEW_LABELS]
                break
        source=r["source"] or ""
        r["sources"]=sources.get(r["spec_id"],[])
        r["evidence"]=r["sources"][0]["page"] if r["sources"] else next(("/api/evidence/"+p for p in ("8","13") if f"PDF {p} /" in source),None)
        if r["spec_id"] in domestic_parts:
            for part in domestic_parts[r["spec_id"]]:
                item={**r,**domestic.sales_fields(part)}
                item["images"]=[dict(label="中文册原图",url="/api/domestic-picture/"+part["part_id"]),*r["images"]]
                item["references"]=[*r["references"],dict(spec_id=part["part_id"],scheme="spec_id",number=part["part_id"],supplier=None)]
                result.append(item)
            continue
        new=foreign.get(r["spec_id"])
        if new:
            r.update(sales_fields(new))
            if new.get("item") and not new.get("code"):
                r["name"]=new["item"]
                r["series"]=new["application"]
            refs=[ref for ref in r["references"] if ref["scheme"]=="supplier_ref"]
            for scheme in ("spec_id","code","wva","bfmc","fmsi","oe_ref","catalog_ref"):
                value=r.get(scheme)
                if not value:
                    continue
                tokens=[value]
                if scheme=="wva" and re.fullmatch(r"[\d\s/；;]+",value):
                    tokens=re.findall(r"\d+",value)
                refs.extend(dict(spec_id=r["spec_id"],scheme=scheme,number=t,supplier=None) for t in tokens)
            r["references"]=refs
        result.append(r)
    return sorted(result,key=lambda r:r.get("pdf_order",10000000))

@lru_cache(maxsize=1)
def routing_index(revision):
    return catalog(compact=True)

@router.get("/api/catalog")
def products(country:str|None=None, marketed_only:bool=False):
    return dict(items=country_candidates(catalog(marketed_only=marketed_only),country),fields=FIELDS,**status())

@router.get("/api/status")
def status():
    with db() as conn:
        row = conn.execute("SELECT data_hash FROM catalog_sync WHERE id=1").fetchone()
    return dict(**state,revision=(row["data_hash"] if row else "")+state.get("foreign_revision","")+state.get("domestic_revision",""))

@router.get("/api/domestic-picture/{key}")
def domestic_picture(key:str):
    with db() as c:
        part=c.execute("SELECT page_key,picture_box FROM domestic_catalog.parts WHERE part_id=%s",(key,)).fetchone()
    if not part:raise HTTPException(404,"国内规格不存在")
    with Image.open(DOCS/"materials/pages"/(part["page_key"]+".jpg")) as im:
        buf=BytesIO()
        im.crop(part["picture_box"]).save(buf,"PNG")
        return Response(buf.getvalue(),media_type="image/png")

@router.get("/api/photo/{path:path}")
def photo(path:str):
    target = photo_path(path)
    if target is None:
        raise HTTPException(404)
    return FileResponse(target)

@router.get("/api/evidence/{page}")
def evidence(page:int):
    if page not in (8,13):
        raise HTTPException(404)
    return FileResponse(DOCS/"materials"/f"catalog-{page:02}.jpg")

@router.get("/api/page/{page}")
def source_page(page:str):
    if not re.fullmatch(r"(en|cn)-\d{2}",page):raise HTTPException(404)
    image=DOCS/"materials/pages"/(page+".jpg")
    if not image.is_file():raise HTTPException(404)
    return FileResponse(image)

@router.get("/api/observation/{key}")
def source_row(key:str):
    with db() as c:
        row=c.execute("SELECT page_key,bbox,reading->'card_box' AS card FROM catalog_observation WHERE observation_id=%s",(key,)).fetchone()
    if not row:raise HTTPException(404)
    with Image.open(DOCS/"materials/pages"/(row["page_key"]+".jpg")) as im:
        box=row["card"] or row["bbox"]
        crop=im.crop((max(0,box[0]-3),max(0,box[1]-3),min(im.width,box[2]+3),min(im.height,box[3]+3)))
        buf=BytesIO();crop.save(buf,"PNG")
    return Response(buf.getvalue(),media_type="image/png")

class Inquiry(BaseModel):
    turns:list[Turn]=Field(min_length=1,max_length=30)
    use_model:bool=False
    market:Literal["国内","外贸"]|None=None
    country:str|None=None

@router.post("/api/match")
def analyze(req:Inquiry):
    index=routing_index(status()["revision"])
    clues,mode=extract(req.turns,index,req.use_model)
    route=route_inquiry(req.turns,index,clues,req.market,req.country)
    clues.market={"F":"外贸","D":"国内"}.get(route["slots"]["market"]["value"],"")
    clues.kind={"P":"盘式","G":"鼓式"}.get(route["slots"]["kind"]["value"],"")
    rows=catalog(route["search_prefixes"]) if route["status"]=="resolved" else []
    result=match(req.turns,rows,False,extracted=(clues,mode))
    result["routing"]=route
    if route["question"]:
        result["question"]=route["question"]
    return result

class DraftSearch(BaseModel):
    workspace: UUID
    inquiries: list[int] = Field(min_length=1)

@router.post("/api/quote-drafts/search")
def inquiry_drafts(req: DraftSearch):
    with db() as conn:
        rows = conn.execute("""
            SELECT id, snapshot FROM quote_draft WHERE snapshot->>'workspace'=%s
            AND snapshot->>'inquiry_id'=ANY(%s)
            ORDER BY id DESC LIMIT 25
        """, (str(req.workspace), [str(i) for i in req.inquiries])).fetchall()
    return [dict(id=row["id"], **row["snapshot"]) for row in rows]

@router.post("/api/quotes")
def standalone_quote(req: Quote):
    if req.inquiry_id is not None or req.workspace is not None:
        raise HTTPException(422, "关联询盘的报价请从询盘详情创建")
    with db() as conn:
        return save_quote(conn, req)

