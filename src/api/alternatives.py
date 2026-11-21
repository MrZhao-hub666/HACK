"""Evidence-backed buyer recommendations for a manually selected inquiry."""

import json
import re
import unicodedata
from typing import Literal
from html import unescape

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .accounts import team
from .auth import workspace_user
from .db import audit, database, one, utc
from .models import Company, Discovery, Input
from .prospects import (
    MARKETS,
    discover,
    host,
    matching_company,
    market_key,
    public_search,
    samples,
    save_company,
    valid_url,
)

router = APIRouter()
FAMILIES = {
    "车队": "运输车队",
    "维修厂": "商用车维修",
    "维修及配件": "商用车维修",
    "配件门店": "配件经销",
    "贸易商": "配件经销",
}
PUBLIC_SOURCES = [
    (
        "Swift Haulage Berhad",
        "车队",
        "https://swiftlogistics.com.my/container-haulage/",
        "官网列有马来西亚半岛集装箱运输业务及牵引车、挂车车队。",
        "corporate@swiftlogistics.com.my",
    ),
    (
        "Infinity Logistics and Transport Ventures",
        "车队",
        "https://www.infinity.com.my/services/land-transportation-services/",
        "官网列有马来西亚跨境公路运输、自有牵引车与挂车，以及集装箱运输服务。",
        "",
    ),
    (
        "Diamond Technique Sdn. Bhd.",
        "贸易商",
        "https://diamondtechnique.com/about-us/",
        "企业介绍列有在马来西亚批发欧洲重卡配件的业务，供应品类包括制动部件。",
        "",
    ),
    (
        "Wintruck Auto Supply Sdn. Bhd.",
        "配件门店",
        "https://www.wintruckgroup.com/",
        "官网列有莎阿南营业地址、卡车及挂车配件，并提供刹车片和制动衬片产品栏目。",
        "",
    ),
]


class Search(Input):
    source_company_id: int = Field(gt=0)
    mode: Literal["local", "live"] = "local"
    claim: bool = False


class Feedback(Input):
    decision: Literal["adopted", "dismissed"]


class Proof(Input):
    url: str = Field(min_length=1, max_length=1400)
    note: str = Field(min_length=1, max_length=1000)


def public_catalog():
    rows = samples()
    for name, kind, url, evidence, contact in PUBLIC_SOURCES:
        rows.append(
            dict(
                name=name,
                kind=kind,
                country="马来西亚",
                website="/".join(url.split("/")[:3]),
                evidence=evidence,
                evidence_url=url,
                source="已核验样例",
                checked="2026-11-21",
                contact=contact,
                procurement="待核实",
                next_action=(
                    "确认车队自行采购制动件，还是由维保服务商统一供货。"
                    if kind == "车队"
                    else "确认常备制动件品牌、覆盖车型与新增供应商的准入方式。"
                ),
            )
        )
    return rows


def facts(row):
    # Only business-profile fields are retained. Private notes and inquiry messages never enter discovery.
    return {
        k: row.get(k, "")
        for k in (
            "name",
            "country",
            "kind",
            "website",
            "social",
            "contact",
            "procurement",
            "evidence",
            "evidence_url",
            "source",
            "checked",
            "next_action",
        )
    }


def name_key(name):
    normalized = unicodedata.normalize("NFKC", name).casefold()
    normalized = re.sub(r"\b(sdn|bhd|berhad|limited|ltd|inc)\b", "", normalized)
    return "".join(ch for ch in normalized if ch.isalnum())


def keys(profile):
    result = {"name:" + name_key(profile["name"])}
    if profile["website"]:
        result.add("web:" + host(profile["website"]))
    return result


def live_profile(row, source):
    text = unescape(
        re.sub("<[^>]+>", " ", row["name"] + " " + row["evidence"])
    ).casefold()
    market = market_key(source["country"])
    places = [market] + [cn for cn, en in MARKETS.items() if en.casefold() == market]
    if len(source["country"]) > 2:
        places.append(source["country"].casefold())
    if market == "malaysia":
        places += [
            "马来西亚",
            "selangor",
            "kuala lumpur",
            "port klang",
            "johor",
            "penang",
            "malaysian",
        ]
    if not any(place in text for place in places) or not re.search(
        r"truck|fleet|haulage|prime mover|commercial vehicle|lorry|重卡|商用车|车队",
        text,
    ):
        return None
    if re.search(r"\b(top \d+|jobs|vacancies|directory of)\b", row["name"], re.I):
        return None
    kind = row["kind"]
    if kind == "待识别":
        if re.search(
            r"distribut|wholesal|parts supplier|trade in|spare parts shop|批发|经销",
            text,
        ):
            kind = "贸易商"
        elif re.search(r"haulage|prime movers|车队", text):
            kind = "车队"
    return {
        **row,
        "country": source["country"],
        "kind": kind,
        "evidence": unescape(re.sub("<[^>]+>", "", row["evidence"])),
    }


def shortlist(db, source, pool):
    remembered = {}
    for record in db.execute(
        "SELECT * FROM alternative_buyers WHERE source_company_id=?", (source["id"],)
    ):
        prior = dict(record)
        for alias in keys(json.loads(prior["profile"])) | {prior["identity"]}:
            remembered[alias] = prior
    source_keys = keys(source)
    source_host = host(source["website"])
    ranked = []
    for raw in pool:
        profile = facts(raw)
        if (
            not name_key(profile["name"])
            or not profile["evidence"].strip()
            or not profile["evidence_url"]
        ):
            continue
        try:
            valid_url(profile["evidence_url"])
            valid_url(profile["website"])
        except HTTPException:
            continue
        if (
            market_key(profile["country"]) != market_key(source["country"])
            or FAMILIES.get(profile["kind"]) != FAMILIES[source["kind"]]
        ):
            continue
        if not re.search(
            r"fleet|truck|brak(e|ing)|haulage|prime mover|lorry|commercial vehicle|车队|重卡|卡车|牵引车|商用车|制动|刹车|挂车",
            profile["evidence"],
            re.I,
        ):
            continue
        if source["evidence_url"] and source["evidence_url"].rstrip("/") == profile[
            "evidence_url"
        ].rstrip("/"):
            continue
        aliases = keys(profile)
        evidence_host = host(profile["evidence_url"])
        if aliases & source_keys or (
            source_host
            and (
                evidence_host == source_host
                or evidence_host.endswith("." + source_host)
            )
        ):
            continue
        existing = matching_company(db, profile)
        if existing and existing["id"] == source["id"]:
            continue
        key = (
            ("web:" + host(profile["website"]))
            if profile["website"]
            else "name:" + name_key(profile["name"])
        )
        # Live result titles may include a page heading. An exact previously verified
        # official page can recover the same identity without treating directory domains as companies.
        official = remembered.get("web:" + evidence_host)
        if official and not profile["website"]:
            previous = json.loads(official["profile"])
            if previous["evidence_url"] == profile["evidence_url"] or name_key(
                previous["name"]
            ) in name_key(profile["name"]):
                key = official["identity"]
                profile.update(name=previous["name"], website=previous["website"])
                aliases |= keys(profile)
        prior = remembered.get(key) or remembered.get(
            "name:" + name_key(profile["name"])
        )
        if prior:
            key = prior["identity"]
            if prior["decision"] == "dismissed":
                continue
        direct = bool(prior and prior["proof_url"])
        # Prefer documented relationships, then unworked peers and an exact business-type match.
        rank = (
            not direct,
            bool(prior and prior["decision"] == "adopted"),
            bool(existing),
            (existing["procurement"] if existing else profile["procurement"])
            != "可直接采购",
            profile["kind"] != source["kind"],
            profile["source"] == "实时网页搜索",
            profile["name"].casefold(),
        )
        ranked.append((rank, key, profile, aliases))
    chosen, used = [], set()
    for _, key, profile, aliases in sorted(ranked, key=lambda entry: entry[0]):
        if key in used or aliases & used:
            continue
        used.update({key, *aliases})
        chosen.append((key, profile))
        if len(chosen) == 3:
            break
    return chosen


JOIN = """FROM alternative_slots s JOIN alternative_batches b ON s.inquiry_id=b.inquiry_id
    JOIN inquiries i ON i.id=b.inquiry_id AND i.company_id=b.source_company_id AND i.merged_into IS NULL
    JOIN companies c ON c.id=b.source_company_id
    JOIN alternative_buyers r ON r.id=s.candidate_id AND r.source_company_id=c.id"""
SELECT = (
    """SELECT r.*, i.id AS inquiry_id,i.owner,c.name AS source_name,c.evidence_url AS source_url,c.kind AS source_kind,
    c.country AS market,b.generated_at,s.position """
    + JOIN
)


def card(db, row):
    profile = json.loads(row["profile"])
    saved = (
        db.execute(
            "SELECT * FROM companies WHERE id=?", (row["company_id"],)
        ).fetchone()
        if row["company_id"]
        else None
    )
    if not saved:
        saved = matching_company(db, profile)
    owners = []
    if saved:
        owners = [
            r[0]
            for r in db.execute(
                """SELECT DISTINCT owner FROM inquiries WHERE company_id=?
            AND owner<>'' AND state<>'已结束' AND merged_into IS NULL ORDER BY owner""",
                (saved["id"],),
            )
        ]
        if saved["owner"] and saved["owner"] not in owners:
            owners.insert(0, saved["owner"])
        profile["procurement"] = saved["procurement"]
        profile["contact"] = saved["contact"] or profile["contact"]
    proof = None
    if row["proof_url"]:
        proof = dict(
            url=row["proof_url"],
            note=row["proof_note"],
            actor=row["proof_actor"],
            at=row["proof_at"],
        )
    return dict(
        id=row["id"],
        inquiry_id=row["inquiry_id"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        owner=row["owner"],
        profile=profile,
        decision=row["decision"],
        proof=proof,
        reason=f"目标市场为{row['market']}；原企业与候选企业均经营{FAMILIES.get(row['source_kind'], row['source_kind'])}相关业务。",
        archive_id=saved["id"] if saved else None,
        archive_owners=owners,
    )


def batch(db, ident):
    header = db.execute(
        """SELECT b.* FROM alternative_batches b JOIN inquiries i ON i.id=b.inquiry_id
        WHERE b.inquiry_id=? AND b.source_company_id=i.company_id AND i.merged_into IS NULL""",
        (ident,),
    ).fetchone()
    if not header:
        return None
    rows = db.execute(
        SELECT + " WHERE i.id=? AND r.decision<>'dismissed' ORDER BY s.position",
        (ident,),
    )
    return {**dict(header), "items": [card(db, r) for r in rows]}


def context(db, ident, req):
    inquiry = one(
        db,
        "SELECT company_id,owner FROM inquiries WHERE id=? AND merged_into IS NULL",
        (ident,),
    )
    if inquiry["company_id"] != req.source_company_id:
        raise HTTPException(409, "请先关联企业，或刷新已变更的询盘")
    if not inquiry["owner"] and not req.claim:
        raise HTTPException(409, "请先分派负责人或选择认领并查找")
    if inquiry["owner"] and inquiry["owner"] not in team(db):
        raise HTTPException(409, "请先将询盘分派给启用的团队成员")
    source = one(db, "SELECT * FROM companies WHERE id=?", (req.source_company_id,))
    if (
        market_key(source["country"]) in {"", "全部", "all", "待核实"}
        or source["kind"] not in FAMILIES
    ):
        raise HTTPException(422, "请在客户档案补全目标市场和买家业务类型")
    prior = db.execute(
        "SELECT generated_at FROM alternative_batches WHERE inquiry_id=?", (ident,)
    ).fetchone()
    snapshot = (
        inquiry["owner"],
        source["name"],
        source["country"],
        source["kind"],
        source["website"],
        prior[0] if prior else "",
    )
    return source, inquiry["owner"], snapshot


@router.post("/api/inquiries/{ident}/alternatives")
def generate(ident: int, req: Search, user=Depends(workspace_user)):
    with database() as db:
        source, owner, snapshot = context(db, ident, req)
    if req.mode == "live":
        # Explicit public market + coarse business type only; no customer identity or free-form inquiry keywords.
        market = market_key(source["country"])
        public_market = next(
            (en for en in MARKETS.values() if en.casefold() == market), "international"
        )
        found = discover(
            Discovery(market=public_market, kind=source["kind"], mode="live")
        )
        query = found["query"]
        pool = [p for raw in found["items"] if (p := live_profile(raw, source))]
    else:
        query = source["country"] + " · " + FAMILIES[source["kind"]]
        pool = public_catalog()
    with database(True) as db:
        if context(db, ident, req)[2] != snapshot:
            raise HTTPException(409, "询盘、企业或推荐批次已变更，请刷新后重试")
        if req.mode == "local":
            pool += [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM companies WHERE saved=1 AND evidence_url<>'' AND checked<>''"
                )
            ]
        selected = shortlist(db, source, pool)
        if not owner:
            owner = user["display_name"]
            db.execute("UPDATE inquiries SET owner=? WHERE id=?", (owner, ident))
            audit(db, ident, owner, "分配负责人", owner)
        db.execute("DELETE FROM alternative_batches WHERE inquiry_id=?", (ident,))
        db.execute(
            "INSERT INTO alternative_batches VALUES(?,?,?,?,?)",
            (ident, source["id"], utc(), req.mode, query),
        )
        for position, (key, profile) in enumerate(selected, 1):
            rid = db.execute(
                """INSERT INTO alternative_buyers(source_company_id,identity,profile) VALUES(?,?,?)
                ON CONFLICT(source_company_id,identity) DO UPDATE SET profile=excluded.profile RETURNING id""",
                (source["id"], key, json.dumps(profile, ensure_ascii=False)),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO alternative_slots VALUES(?,?,?)", (ident, position, rid)
            )
        audit(
            db,
            ident,
            user["display_name"],
            "查找替代买家",
            f"{query} · {len(selected)} 家 · 负责人 {owner}",
        )
        return batch(db, ident)


@router.get("/api/alternatives/mine")
def mine(user=Depends(workspace_user)):
    with database() as db:
        rows = db.execute(
            SELECT
            + " WHERE i.owner=? AND r.decision='pending' ORDER BY b.generated_at DESC,s.position",
            (user["display_name"],),
        )
        seen = set()
        cards = []
        for row in rows:
            if row["id"] not in seen:
                cards.append(card(db, row))
                seen.add(row["id"])
        return cards


def actionable(db, ident, rid, actor):
    row = db.execute(SELECT + " WHERE i.id=? AND r.id=?", (ident, rid)).fetchone()
    if not row:
        raise HTTPException(409, "该推荐已更新，请刷新后再操作")
    if row["owner"] != actor:
        raise HTTPException(403, "仅当前询盘负责人可以处理推荐")
    return row


@router.post("/api/inquiries/{ident}/alternatives/{rid}/feedback")
def feedback(ident: int, rid: int, req: Feedback, user=Depends(workspace_user)):
    actor = user["display_name"]
    with database(True) as db:
        row = actionable(db, ident, rid, actor)
        if row["decision"] == req.decision:
            return batch(db, ident)
        if row["decision"] != "pending":
            raise HTTPException(409, "这条推荐已经处理")
        profile = json.loads(row["profile"])
        archive = None
        if req.decision == "adopted":
            data = Company(
                **{k: v for k, v in profile.items() if k in Company.model_fields}
            ).model_dump()
            archive = save_company(
                db, data, profile["source"], profile["checked"], owner=actor
            )["id"]
        if archive == row["source_company_id"]:
            raise HTTPException(409, "候选现已关联原企业，请重新查找")
        db.execute(
            "UPDATE alternative_buyers SET decision=?,company_id=? WHERE id=?",
            (req.decision, archive, rid),
        )
        audit(
            db,
            ident,
            actor,
            "采纳替代买家" if archive else "标记推荐不相关",
            profile["name"],
        )
        return batch(db, ident)


@router.post("/api/inquiries/{ident}/alternatives/{rid}/sources")
def relationship_sources(ident: int, rid: int, user=Depends(workspace_user)):
    with database() as db:
        row = actionable(db, ident, rid, user["display_name"])
        candidate = json.loads(row["profile"])["name"]
        source = row["source_name"]
    query = f'"{source}" "{candidate}" (tender OR bidder OR competitor OR 竞标 OR 竞争)'
    items = []
    seen = set()
    for hit in public_search(query):
        text = unescape(re.sub("<[^>]+>", "", hit["title"] + " " + hit["description"]))
        clean = name_key(text)
        if hit["url"] in seen or not all(
            name_key(n) and name_key(n) in clean for n in (source, candidate)
        ):
            continue
        if not re.search(
            r"tender|bidd(?:er|ing)|competit|竞标|竞标人|投标|竞争", text, re.I
        ):
            continue
        seen.add(hit["url"])
        items.append(hit)
        if len(items) == 3:
            break
    return {"items": items}


@router.post("/api/inquiries/{ident}/alternatives/{rid}/proof")
def record_proof(ident: int, rid: int, req: Proof, user=Depends(workspace_user)):
    valid_url(req.url)
    with database(True) as db:
        row = actionable(db, ident, rid, user["display_name"])
        if row["decision"] == "dismissed":
            raise HTTPException(409, "该推荐已标记不相关")
        if (
            row["proof_url"] == req.url
            and row["proof_note"] == req.note
            and row["proof_actor"] == user["display_name"]
        ):
            return batch(db, ident)
        db.execute(
            "UPDATE alternative_buyers SET proof_url=?,proof_note=?,proof_actor=?,proof_at=? WHERE id=?",
            (req.url, req.note, user["display_name"], utc(), rid),
        )
        audit(
            db,
            ident,
            user["display_name"],
            "核实竞争依据",
            json.loads(row["profile"])["name"] + " · " + req.url,
        )
        return batch(db, ident)


@router.delete("/api/inquiries/{ident}/alternatives/{rid}/proof")
def withdraw_proof(ident: int, rid: int, user=Depends(workspace_user)):
    with database(True) as db:
        row = actionable(db, ident, rid, user["display_name"])
        if row["proof_url"]:
            db.execute(
                "UPDATE alternative_buyers SET proof_url='',proof_note='',proof_actor='',proof_at='' WHERE id=?",
                (rid,),
            )
            audit(
                db,
                ident,
                user["display_name"],
                "撤回竞争判断",
                json.loads(row["profile"])["name"],
            )
        return batch(db, ident)


def merge_batches(db, source, target):
    # Both inquiries now represent one matter. Keep the newest matching search and all company-pair feedback.
    company = db.execute(
        "SELECT company_id FROM inquiries WHERE id=?", (target,)
    ).fetchone()[0]
    rows = db.execute(
        "SELECT * FROM alternative_batches WHERE inquiry_id IN (?,?) ORDER BY generated_at DESC",
        (source, target),
    ).fetchall()
    keep = next(
        (r["inquiry_id"] for r in rows if r["source_company_id"] == company), None
    )
    for row in rows:
        if row["inquiry_id"] != keep:
            db.execute(
                "DELETE FROM alternative_batches WHERE inquiry_id=?",
                (row["inquiry_id"],),
            )
    if keep == source:
        db.execute(
            "UPDATE alternative_batches SET inquiry_id=? WHERE inquiry_id=?",
            (target, source),
        )
