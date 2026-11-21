"""Fair discovery and human verification, separate from inbound inquiries."""

import csv
import io
import json
import re
from datetime import date
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field, ValidationError, field_validator

from . import prospects
from .auth import workspace_user
from .db import database, one, utc
from .models import Company, CompanyKind, Input
from .intelligence import enrich, extract
from .outreach_excel import buyer_workbook

router = APIRouter(prefix="/api/outreach", tags=["展会拓客"])
Source = Literal["上海法兰克福", "广交会", "社媒原帖", "企业采购资料"]
SHANGHAI = "https://automechanika-shanghai.hk.messefrankfurt.com/shanghai/zh-cn/planning-preparation/visitors.html"
CANTON = "https://finance.sina.com.cn/jjxw/2025-10-18/doc-infuhrzu6312926.shtml"
CATALOG = [
    (
        "上海法兰克福",
        "2025",
        "LKQ Europe Gmbh",
        "瑞士",
        SHANGHAI,
        "主办方列为 2025 年部分优选买家代表。",
    ),
    (
        "上海法兰克福",
        "2025",
        "Dorman",
        "",
        SHANGHAI,
        "主办方列出企业简称 Dorman，具体参观人及法人待核。",
    ),
    (
        "上海法兰克福",
        "2025",
        "CarParts",
        "美国",
        SHANGHAI,
        "主办方列为 2025 年部分优选买家代表。",
    ),
    (
        "广交会",
        "第138届",
        "Command Auto Parts LTD",
        "巴西",
        CANTON,
        "韶关发布（转载）记载该企业在汽车配件供采对接会上发布需求，具体片型未披露。",
    ),
    (
        "广交会",
        "第138届",
        "KHANN LLC",
        "埃及",
        CANTON,
        "对接会报道点名该买家及所在国。企业法定名称、具体品类和联系方式应另行核对。",
    ),
    (
        "社媒原帖",
        "",
        "Trailer brake shoes",
        "",
        "https://www.thetruckersreport.com/truckingindustryforum/threads/trailer-brake-shoes.1815500/",
        "历史论坛原帖：车主为挂车找制动蹄，企业身份待核。",
    ),
    (
        "企业采购资料",
        "",
        "SAF-HOLLAND",
        "德国",
        "https://safholland.com/int/en/suppliers-emea",
        "供应商准入页列有盘式片及鼓式衬片，另列德国采购部门邮箱。",
    ),
    (
        "企业采购资料",
        "",
        "MTT AUTO PARTS SDN. BHD.",
        "马来西亚",
        "https://www.mttautoparts.com.my/company-profile/",
        "公司官网列出商用车配件进口、批发和制动系统业务，以及企业 WhatsApp、电话和邮箱。",
    ),
]
SCOPES = {
    "上海法兰克福": "Automechanika Shanghai 上海汽配展 买家 buyer",
    "广交会": "广交会 Canton Fair 汽车配件 采购商 buyer",
    "社媒原帖": "(site:facebook.com OR site:linkedin.com/posts OR site:x.com OR site:threads.com OR site:bsky.app OR site:thetruckersreport.com OR site:bigmacktrucks.com)",
    "企业采购资料": "commercial vehicle brakes supplier purchasing procurement",
}


class Search(Input):
    source: Source
    mode: Literal["local", "live", "bluesky"] = "local"
    keywords: str = Field(default="", max_length=150)
    edition: str = Field(default="", max_length=45)
    market: str = Field(default="", max_length=80)


class Signal(Input):
    source: Source
    edition: str = Field(default="", max_length=60)
    title: str = Field(min_length=1, max_length=200)
    market: str = Field(default="", max_length=80)
    url: str = Field(min_length=1, max_length=1400)
    snippet: str = Field(default="", max_length=1800)
    author: str = Field(default="", max_length=160)
    published: date | None = None
    quote: str = Field(default="", max_length=2000)

    @field_validator("url")
    @classmethod
    def check_url(cls, value):
        return prospects.valid_url(value)


def normalized_url(url):
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.casefold().startswith("utm_")
        and k.casefold() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            parts.fragment,
        )
    )


def identity(item):
    key = [item.source, normalized_url(item.url)]
    if item.source != "社媒原帖":
        key.extend([item.edition.casefold(), item.title.casefold()])
    return json.dumps(key, ensure_ascii=False)


def is_social_post(url):
    parts = urlsplit(url)
    domain = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    patterns = {
        "facebook.com": r"/(?:[^/]+/)?(?:posts|videos|reel)/|/groups/[^/]+/(?:posts|permalink)/|^/(?:permalink|story)\.php$",
        "linkedin.com": r"^/(?:posts/|feed/update/)",
        "x.com": r"/status/\d+",
        "twitter.com": r"/status/\d+",
        "threads.net": r"/post/[^/]+",
        "threads.com": r"/post/[^/]+",
        "bsky.app": r"/profile/[^/]+/post/[^/]+",
        "thetruckersreport.com": r"/threads/[^/]+",
        "bigmacktrucks.com": r"/topic/[^/]+",
    }
    return domain in patterns and re.search(patterns[domain], parts.path) is not None


def record(db, item):
    if item.source in ("广交会", "上海法兰克福") and not item.edition:
        raise HTTPException(422, "登记展会线索时请填写已核对的届次")
    key = identity(item)
    db.execute(
        """INSERT INTO outreach_evidence
        (identity,source,edition,title,market,url,snippet,author,published,quote,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(identity) DO NOTHING""",
        (
            key,
            item.source,
            item.edition,
            item.title,
            item.market,
            item.url,
            item.snippet,
            item.author,
            str(item.published or ""),
            item.quote,
            utc(),
        ),
    )
    return one(db, "SELECT * FROM outreach_evidence WHERE identity=?", (key,))


@router.post("/search")
def search(req: Search):
    if req.mode == "bluesky":
        if req.source != "社媒原帖":
            raise HTTPException(422, "Bluesky 仅适用于社媒原帖")
        query = " ".join(
            x for x in [req.keywords or "truck brake lining", req.market] if x
        )
        items = bluesky_posts(query)
    elif req.mode == "live":
        product = req.keywords or (
            "truck brake lining supplier wanted"
            if req.source == "社媒原帖"
            else "commercial vehicle parts"
        )
        query = " ".join(
            x for x in [SCOPES[req.source], req.edition, req.market, product] if x
        )
        items = [
            Signal(
                source=req.source,
                title=h["title"] or h["url"][:200],
                url=h["url"],
                snippet=h["description"],
                edition=req.edition,
                market=req.market,
            )
            for h in prospects.public_search(query)
            if req.source != "社媒原帖" or is_social_post(h["url"])
        ]
    else:
        query = " ".join(
            x for x in [req.source, req.edition, req.market, req.keywords] if x
        )
        items = [
            Signal(source=s, edition=e, title=t, market=m, url=u, snippet=n)
            for s, e, t, m, u, n in CATALOG
            if s == req.source
        ]
        with database() as db:
            for row in db.execute(
                """SELECT source,edition,title,market,url,snippet FROM outreach_evidence
                                     WHERE source=? ORDER BY id DESC""",
                (req.source,),
            ):
                items.append(Signal(**dict(row)))
        items = [
            i
            for i in items
            if req.edition.casefold() in i.edition.casefold()
            and req.market.casefold() in i.market.casefold()
            and all(
                word.casefold()
                in " ".join([i.title, i.market, i.edition, i.snippet]).casefold()
                for word in req.keywords.split()
            )
        ]
    return {
        "query": query,
        "mode": req.mode,
        "items": list({identity(i): i for i in items}.values()),
    }


def bluesky_posts(query):
    try:
        result = httpx.get(
            "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
            params={"q": query, "limit": 25, "sort": "latest"},
            timeout=10,
        )
        result.raise_for_status()
        posts = result.json()["posts"]
        if not isinstance(posts, list):
            raise ValueError
        items = []
        for post in posts:
            match = re.fullmatch(
                r"at://(did:[A-Za-z0-9:%._-]+)/app\.bsky\.feed\.post/([A-Za-z0-9._~-]+)",
                post["uri"],
            )
            if not match:
                continue
            author = post["author"]["handle"]
            body = post["record"]["text"]
            items.append(
                Signal(
                    source="社媒原帖",
                    title=(author + " · " + body)[:200],
                    url=f"https://bsky.app/profile/{match[1]}/post/{match[2]}",
                    snippet=body[:1800],
                    quote=body[:2000],
                    author=author,
                    published=date.fromisoformat(post["record"]["createdAt"][:10]),
                )
            )
        return items
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(502, "Bluesky 原帖检索服务不可用，请稍后重试") from exc


@router.post("/evidence")
def capture(req: Signal):
    with database(True) as db:
        return record(db, req)


class FairImport(Input):
    source: Literal["上海法兰克福", "广交会"]
    edition: str = Field(min_length=1, max_length=60)
    csv_text: str = Field(min_length=1, max_length=400000)


@router.post("/import")
def import_fair(req: FairImport):
    parsed = csv.DictReader(io.StringIO(req.csv_text.lstrip("\ufeff")), strict=True)
    try:
        if not {"企业名称", "来源链接"}.issubset(parsed.fieldnames or []):
            raise HTTPException(422, "CSV 需要企业名称、来源链接两列")
        items = []
        for row in parsed:
            if len(items) >= 500 or None in row:
                raise HTTPException(422, f"第 {parsed.line_num} 行超出行数或列数限制")
            items.append(
                Signal(
                    source=req.source,
                    edition=req.edition,
                    title=row["企业名称"],
                    url=row["来源链接"],
                    market=row.get("市场") or "",
                    snippet=row.get("来源说明") or "",
                )
            )
    except (ValidationError, csv.Error) as exc:
        raise HTTPException(422, f"第 {parsed.line_num} 行格式或字段有误") from exc
    if not items:
        raise HTTPException(422, "CSV 没有数据行")
    with database(True) as db:
        before = db.total_changes
        for item in items:
            record(db, item)
        added = db.total_changes - before
    return {"added": added, "duplicates": len(items) - added}


class Review(Input):
    version: str
    verdict: Literal["已核实", "排除", "待核实"]
    company_id: int | None = Field(default=None, gt=0)
    name: str = Field(default="", max_length=200)
    market: str = Field(default="", max_length=80)
    kind: CompanyKind = "待识别"
    author: str = Field(default="", max_length=160)
    published: date | None = None
    quote: str = Field(default="", max_length=2000)
    intent: Literal[
        "待判断",
        "企业参会",
        "采购询价",
        "寻找货源",
        "供应商准入",
        "安装咨询",
        "卖方推广",
        "其他",
    ] = "待判断"
    fit: Literal["A", "B", "C"] = "C"
    reason: str = Field(min_length=1, max_length=600)


class Excerpt(Input):
    text: str = Field(min_length=1, max_length=2000)


def suggest_intent(text):
    for intent, pattern in [
        ("待判断", r"don.t need (?:a )?quote|no quote|无需报价|不采购"),
        (
            "供应商准入",
            r"purchasing portfolio|become (?:a|our) supplier|供应商准入|采购品类",
        ),
        (
            "卖方推广",
            r"we (?:sell|supply|manufacture)|our catalog|we offer|本厂供应|厂家直销",
        ),
        (
            "安装咨询",
            r"already have (?:the |my )?(?:pads|parts)|自备.{0,5}(?:配件|刹车片).{0,8}安装",
        ),
        (
            "寻找货源",
            r"looking for (?:a |an )?(?:supplier|source)|where (?:can|do) (?:I|you) buy|求购|寻找供应商",
        ),
    ]:
        if re.search(pattern, text, re.I):
            return intent, "本地规则"
    features = enrich(text, extract(text))
    intent = "采购询价" if features["intent"] == "采购询价" else "待判断"
    return intent, features["engine"]


@router.post("/assess")
def assess(req: Excerpt):
    text = req.text
    intent, engine = suggest_intent(text)
    commercial = re.search(
        r"商用车|重卡|车桥|挂车|客车|trucks?|trailers?|buses|commercial vehicle|WVA[ -]*\d+",
        text,
        re.I,
    )
    product = re.search(
        r"制动片|刹车片|制动衬片|摩擦片|brake (?:pads?|linings?)|friction materials?|WVA[ -]*\d+",
        text,
        re.I,
    )
    if commercial and product and intent in ("寻找货源", "采购询价", "供应商准入"):
        fit, reason = "A", "摘录同时含商用车场景、目标品类和采购方向。"
    elif commercial and (
        product or re.search(r"brak|axle|spare parts|制动|配件|车桥", text, re.I)
    ):
        fit, reason = "B", "摘录涉及商用车相关业务，目标品类采购方式仍需核实。"
    else:
        fit, reason = "C", "这段摘录不足以确认商用车制动片采购。"
    return {"intent": intent, "engine": engine, "fit": fit, "reason": reason}


@router.put("/evidence/{ident}")
def review(ident: int, req: Review, user=Depends(workspace_user)):
    with database(True) as db:
        item = one(db, "SELECT * FROM outreach_evidence WHERE id=?", (ident,))
        if req.version != item["updated"]:
            raise HTTPException(409, "记录已更新，请重新打开核实记录")
        company_id = req.company_id
        if req.verdict == "已核实":
            if not req.quote or (item["source"] == "社媒原帖" and not req.author):
                raise HTTPException(422, "请摘录原文；社媒原帖还需填写发布方")
            if company_id:
                one(
                    db, "SELECT id FROM companies WHERE id=? AND saved=1", (company_id,)
                )
            elif req.name or item["source"] != "社媒原帖":
                if not req.name or not req.market:
                    raise HTTPException(
                        422, "请选择已有档案，或填写已核实的企业名和市场"
                    )
                data = Company(
                    name=req.name,
                    country=req.market,
                    kind=req.kind,
                ).model_dump()
                company_id = prospects.save_company(
                    db, data, item["source"], owner=user["display_name"]
                )["id"]
        else:
            company_id = None
        db.execute(
            """UPDATE outreach_evidence SET company_id=?,verdict=?,author=?,published=?,quote=?,
                      intent=?,fit=?,reason=?,reviewer=?,updated=? WHERE id=?""",
            (
                company_id,
                req.verdict,
                req.author,
                str(req.published or ""),
                req.quote,
                req.intent,
                req.fit if company_id else "C",
                req.reason,
                user["display_name"],
                utc(),
                ident,
            ),
        )
        return one(db, "SELECT * FROM outreach_evidence WHERE id=?", (ident,))


class Contact(Input):
    kind: Literal[
        "采购邮箱",
        "企业邮箱",
        "电话",
        "WhatsApp",
        "Facebook",
        "微信",
        "地址",
        "供应商入口",
    ]
    holder: str = Field(min_length=1, max_length=180)
    value: str = Field(min_length=1, max_length=700)
    url: str = Field(min_length=1, max_length=1400)


PUBLIC_CONTACTS = {
    "lkq europe gmbh": [
        (
            "采购邮箱",
            "直接采购部门",
            "lkqe-direct-purchasing@lkqeurope.com",
            "https://lkqeurope.com/company/locations-contacts",
        ),
        (
            "电话",
            "公司总机",
            "+41 41 884 84 84",
            "https://lkqeurope.com/company/locations-contacts",
        ),
    ],
    "saf-holland": [
        (
            "采购邮箱",
            "德国采购部",
            "Purchasing-DE@safholland.de",
            "https://safholland.com/int/en/suppliers-emea",
        ),
    ],
    "mtt auto parts sdn. bhd.": [
        (
            "企业邮箱",
            "公司咨询台",
            "inquirymtt@yahoo.com",
            "https://www.mttautoparts.com.my/company-profile/",
        ),
        (
            "WhatsApp",
            "官网业务入口",
            "+60 19-310 6682",
            "https://www.mttautoparts.com.my/company-profile/",
        ),
    ],
}


@router.get("/buyers/{ident}/contact-sources")
def contact_sources(ident: int, live: bool = False):
    with database() as db:
        buyer = one(
            db,
            "SELECT name,website,country FROM companies WHERE id=? AND saved=1",
            (ident,),
        )
    if live:
        domain = prospects.host(buyer["website"])
        scope = f"site:{domain}" if domain else buyer["country"]
        query = f'{scope} "{buyer["name"]}" procurement purchasing contact'
        return {"items": [], "pages": prospects.public_search(query)}
    name = buyer["name"].casefold()
    if name == "saf-holland gmbh":
        name = "saf-holland"
    rows = PUBLIC_CONTACTS.get(name, [])
    return {
        "pages": [],
        "items": [Contact(kind=k, holder=h, value=v, url=u) for k, h, v, u in rows],
    }


@router.delete("/buyers/{ident}/contacts/{contact_id}")
def remove_contact(ident: int, contact_id: int):
    with database(True) as db:
        db.execute(
            "DELETE FROM outreach_contacts WHERE id=? AND company_id=?",
            (contact_id, ident),
        )
    return {"ok": True}


@router.post("/buyers/{ident}/contacts")
def save_contact(ident: int, req: Contact, user=Depends(workspace_user)):
    prospects.valid_url(req.url)
    value = req.value
    if req.kind in ("采购邮箱", "企业邮箱"):
        if not re.fullmatch(r"[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+", value):
            raise HTTPException(422, "请填写一个完整的业务邮箱")
        value = value.lower()
    if req.kind in ("Facebook", "供应商入口"):
        prospects.valid_url(value)
    with database(True) as db:
        one(db, "SELECT id FROM companies WHERE id=? AND saved=1", (ident,))
        db.execute(
            """INSERT INTO outreach_contacts(company_id,kind,value,holder,url,reviewer,updated)
                      VALUES (?,?,?,?,?,?,?) ON CONFLICT(company_id,kind,value) DO UPDATE SET
                      holder=excluded.holder,url=excluded.url,reviewer=excluded.reviewer,updated=excluded.updated""",
            (ident, req.kind, value, req.holder, req.url, user["display_name"], utc()),
        )
    return {"ok": True}


def snapshot(db):
    buyers = [
        dict(r)
        for r in db.execute("""SELECT c.id,c.name,c.country,c.kind,c.procurement,c.contact,
        c.website,c.social,c.owner,coalesce(min(e.fit),'') AS grade FROM companies c
        LEFT JOIN outreach_evidence e ON e.company_id=c.id AND e.verdict='已核实'
        WHERE c.saved=1 GROUP BY c.id ORDER BY coalesce(min(e.fit),'Z'),c.name,c.id""")
    ]
    return {
        "buyers": buyers,
        "evidence": [
            dict(r)
            for r in db.execute(
                "SELECT * FROM outreach_evidence ORDER BY updated DESC,id DESC"
            )
        ],
        "contacts": [
            dict(r) for r in db.execute("SELECT * FROM outreach_contacts ORDER BY id")
        ],
        "drafts": [
            dict(r)
            for r in db.execute(
                "SELECT * FROM outreach_drafts ORDER BY updated DESC,id DESC"
            )
        ],
    }


@router.get("")
def dashboard():
    with database() as db:
        return snapshot(db)


@router.get("/summary")
def outreach_summary():
    with database() as db:
        return one(db, """SELECT
            count(CASE WHEN source IN ('上海法兰克福','广交会') THEN 1 END) AS fair_records,
            count(CASE WHEN verdict='待核实' THEN 1 END) AS pending,
            count(DISTINCT CASE WHEN verdict='已核实' THEN company_id END) AS linked_buyers,
            (SELECT count(*) FROM outreach_drafts) AS drafts
            FROM outreach_evidence""")


@router.get("/export.xlsx")
def export(
    grade: Literal["A", "B", "C", "全部", "待评级"] = Query("全部"),
    q: str = Query("", max_length=150),
):
    with database() as db:
        data = snapshot(db)
    data["buyers"] = [
        b
        for b in data["buyers"]
        if q.strip().casefold() in (b["name"] + b["country"] + b["kind"]).casefold()
    ]
    content = buyer_workbook(data, grade)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="buyer-profiles.xlsx"'},
    )


class Invitation(Input):
    event: str = Field(min_length=1, max_length=150)
    booth: str = Field(min_length=1, max_length=80)
    starts: date
    ends: date
    contact_id: int | None = Field(default=None, gt=0)


@router.post("/buyers/{ident}/draft")
def draft(ident: int, req: Invitation, user=Depends(workspace_user)):
    if req.ends < req.starts:
        raise HTTPException(422, "结束日期必须在开始日期当天或之后")
    with database(True) as db:
        buyer = one(db, "SELECT name FROM companies WHERE id=? AND saved=1", (ident,))
        recipient = ""
        if req.contact_id:
            recipient = one(
                db,
                """SELECT value FROM outreach_contacts WHERE id=? AND company_id=?
                                 AND kind IN ('采购邮箱','企业邮箱')""",
                (req.contact_id, ident),
            )["value"]
        subject = f"Commercial vehicle brake parts at {req.event} | Booth {req.booth}"
        body = (
            f"Dear {buyer['name']} purchasing team,\n\n"
            f"I’m {user['display_name']} from Kooying. We manufacture disc brake pads and drum brake "
            f"linings for commercial vehicles. We will be exhibiting at {req.event} "
            f"from {req.starts} to {req.ends}, booth {req.booth}.\n\n"
            "Would you have 15 minutes to meet? If you share the axle series or friction material "
            "references you source, we can prepare relevant samples for your visit.\n\n"
            f"Best regards,\n{user['display_name']}\nKooying\n\n"
            "If you prefer not to receive further exhibition invitations, please let us know by reply."
        )
        key = (ident, req.event, str(req.starts), str(req.ends), req.booth)
        db.execute(
            """INSERT INTO outreach_drafts(company_id,event,starts,ends,booth,recipient,subject,body,actor,updated)
                     VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id,event,starts,ends,booth) DO NOTHING""",
            (*key, recipient, subject, body, user["display_name"], utc()),
        )
        return one(
            db,
            "SELECT * FROM outreach_drafts WHERE company_id=? AND event=? AND starts=? AND ends=? AND booth=?",
            key,
        )


class DraftEdit(Input):
    version: str
    subject: str = Field(min_length=1, max_length=350)
    body: str = Field(min_length=1, max_length=8000)
    contact_id: int | None = Field(default=None, gt=0)


@router.put("/drafts/{ident}")
def edit_draft(ident: int, req: DraftEdit, user=Depends(workspace_user)):
    with database(True) as db:
        old = one(db, "SELECT * FROM outreach_drafts WHERE id=?", (ident,))
        if req.version != old["updated"]:
            raise HTTPException(409, "草稿已被更新，请重新读取后编辑")
        recipient = ""
        if req.contact_id:
            recipient = one(
                db,
                """SELECT value FROM outreach_contacts WHERE id=? AND company_id=?
                                 AND kind IN ('采购邮箱','企业邮箱')""",
                (req.contact_id, old["company_id"]),
            )["value"]
        db.execute(
            "UPDATE outreach_drafts SET recipient=?,subject=?,body=?,actor=?,updated=? WHERE id=?",
            (recipient, req.subject, req.body, user["display_name"], utc(), ident),
        )
        return one(db, "SELECT * FROM outreach_drafts WHERE id=?", (ident,))
