"""Recommend prospects from observed purchasing signals and public business evidence."""

import json
import re
import time

from fastapi import HTTPException

from . import domestic, prospects
from .db import database, utc
from .intelligence import extract

MARKET = "马来西亚"
QUERY = (
    "Malaysia commercial vehicle truck brake parts distributor heavy truck brake repair "
    "workshop haulage fleet own workshop"
)
DAY = 24 * 60 * 60
REFRESH_IN_PROGRESS = "推荐正在更新，请稍后查看结果。"
NO_NEW_WEB_CANDIDATES = "本次实时检索没有筛选出符合条件的网页推荐。"
DIRECTIONS = (
    ("主机与车桥配套", r"车桥厂|主机厂|整车厂|整车配套|axle manufacturer|vehicle manufacturer|truck manufacturer"),
    ("经销进口", r"经销商|代理商|进口商|批发商|\b(?:distributors?|importers?|wholesalers?|dealerships?)\b"),
    ("车队自用", r"车队(?!客户)|物流公司|haulage|fleet operator|(?:our|own) fleet|operat(?:e|es|ing) a fleet"),
    ("维修服务", r"维修厂|修理厂|维修店|truck repair|\bworkshops?\b|bengkel"),
)
DIRECTION_PATTERNS = [
    (label, re.compile(pattern, re.I)) for label, pattern in DIRECTIONS
]
COMMERCIAL = re.compile(
    r"商用车|重卡|卡车|货车|牵引车|挂车|客车|车队|commercial vehicles?|"
    r"\b(?:trucks?|trailers?|lorry|lorries|haulage|WVA)\b",
    re.I,
)
PROCUREMENT = re.compile(
    r"求购|请报价|求报价|询价|要报价|招标|采购|找.{0,5}(?:货源|供应商|厂家)|"
    r"备货|拿货|想买|怎么买|looking for|request for quot|please quote|\bRFQ\b",
    re.I,
)
PASSENGER = re.compile(r"乘用车|普通车主|家用车|摩托车|自行车|两轮电动车|motorcycle|bicycle", re.I)
BRAKE = re.compile(
    r"制动系统|刹车系统|刹车维修|\bbrake(?:s| service| repair| system| tests?| components?)\b|\bbrake,",
    re.I,
)


def direction(text):
    matches = (
        (match.start(), label)
        for label, pattern in DIRECTION_PATTERNS
        if (match := pattern.search(text))
    )
    return min(matches, default=(0, ""))[1]


def domestic_candidates(db):
    rows = db.execute(
        domestic.JOINED + """ WHERE s.demo=0 AND s.company_id IS NULL
          AND m.inquiry_id IS NULL ORDER BY s.published DESC, s.id DESC"""
    )
    for row in rows:
        body, parent = row["body"], row["parent_text"]
        context = f"{body} {parent}"
        if (
            not PROCUREMENT.search(body)
            or PASSENGER.search(body)
            or (PASSENGER.search(parent) and not COMMERCIAL.search(body))
            or not COMMERCIAL.search(context)
            or domestic.classify(body, parent) != "求购"
        ):
            continue
        role = direction(body)
        details = extract(body)
        specification = bool(details["quantities"] or details["codes"])
        grade = "A" if role and specification else "B" if role or specification else "C"
        evidence = domestic.describe(row)
        yield {
            "id": f"domestic:{row['id']}",
            "title": domestic.LABELS[row["platform"]] + "采购线索",
            "source": domestic.LABELS[row["platform"]],
            "market": "",
            "direction": role or "待核实",
            "grade": grade,
            "reason": (
                "原文给出了采购意向、业务角色及型号或数量"
                if grade == "A" else "原文有采购意向，后续可核对采购主体和需求"
            ),
            "evidence": body,
            "url": evidence["source_url"],
            "published": row["published"],
        }


def archived_companies(db):
    return db.execute("SELECT name,country,domain FROM companies WHERE saved=1").fetchall()


def web_candidates(hits, archived):
    names = {(row["name"].casefold(), prospects.market_key(row["country"])) for row in archived}
    domains = {row["domain"] for row in archived if row["domain"]}
    market = prospects.market_key(MARKET)
    for row in hits:
        title = row["title"].strip()
        if prospects.host(row["url"]) in domains or (title.casefold(), market) in names:
            continue
        evidence = (row.get("description") or row.get("evidence") or "").strip()
        context = f"{title} {evidence}"
        role = direction(title) or direction(evidence)
        if role in {"", "维修服务"} and prospects.inferred_buyer_kind(title, evidence) == "贸易商":
            role = "经销进口"
        if not title or not evidence or not role or not COMMERCIAL.search(evidence):
            continue
        if PASSENGER.search(context) and not COMMERCIAL.search(title):
            continue
        product = bool(domestic.PRODUCT.search(evidence) or BRAKE.search(evidence))
        yield {
            "id": "web:" + row["url"],
            "title": title,
            "source": "实时网页搜索",
            "market": MARKET,
            "direction": role,
            "grade": "B" if product else "C",
            "reason": (
                "来源有商用车和制动相关业务，采购能力待核实"
                if product else "来源有商用车相关业务，具体品类及采购能力待核实"
            ),
            "evidence": evidence,
            "url": row["url"],
            "published": "",
        }


def recommendations():
    now = int(time.time())
    configured = prospects.search_credentials() is not None
    with database() as db:
        cache = db.execute("SELECT * FROM discovery_recommendations WHERE id=1").fetchone()
        archived = archived_companies(db)
        items = list(domestic_candidates(db))
    if cache:
        items.extend(web_candidates(json.loads(cache["items"]), archived))
    ordered = sorted(items, key=lambda item: item["published"], reverse=True)
    ordered.sort(key=lambda item: item["grade"])
    unique = {}
    for item in ordered:
        key = prospects.host(item["url"]) if item["market"] else item["url"]
        unique.setdefault(key, item)
    refresh_message = cache["error"] if cache else ""
    no_new_candidates = refresh_message == NO_NEW_WEB_CANDIDATES
    return {
        "items": list(unique.values()),
        "configured": configured,
        "auto_due": configured and (not cache or cache["attempted"] <= now - DAY),
        "updated": cache["updated"] if cache else "",
        "error": "" if no_new_candidates else refresh_message,
        "notice": refresh_message if no_new_candidates else "",
        "market": MARKET,
        "directions": [label for label, _ in DIRECTIONS] + ["待核实"],
    }


def refresh(automatic):
    if not prospects.search_credentials():
        raise HTTPException(503, "请先配置实时网页搜索。")
    now = int(time.time())
    with database(True) as db:
        cache = db.execute("SELECT attempted,expires,items FROM discovery_recommendations WHERE id=1").fetchone()
        if cache and cache["expires"] > now and not automatic:
            raise HTTPException(409, REFRESH_IN_PROGRESS)
        started = not cache or (
            cache["expires"] <= now and (not automatic or cache["attempted"] <= now - DAY)
        )
        if started:
            db.execute(
                """INSERT INTO discovery_recommendations(id,attempted,expires) VALUES(1,?,?)
                   ON CONFLICT(id) DO UPDATE SET attempted=excluded.attempted,expires=excluded.expires""",
                (now, now + 60),
            )
    if started:
        notice = ""
        try:
            items = prospects.public_search(QUERY)
        except HTTPException as exc:
            notice = exc.detail
        with database(True) as db:
            if not notice and cache:
                archived = archived_companies(db)
                if not any(web_candidates(items, archived)) and any(
                    web_candidates(json.loads(cache["items"]), archived)
                ):
                    notice = NO_NEW_WEB_CANDIDATES
            if notice:
                written = db.execute(
                    """UPDATE discovery_recommendations SET error=?,expires=0
                       WHERE id=1 AND attempted=? AND expires>0""",
                    (notice, now),
                ).rowcount
            else:
                written = db.execute(
                    """UPDATE discovery_recommendations SET items=?,updated=?,error='',expires=0
                       WHERE id=1 AND attempted=? AND expires>0""",
                    (json.dumps(items, ensure_ascii=False), utc(), now),
                ).rowcount
        if not written and not automatic:
            raise HTTPException(409, REFRESH_IN_PROGRESS)
    return recommendations()
