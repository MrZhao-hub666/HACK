import json
import os

from fastapi import HTTPException

from .accounts import team
from .alternatives import batch as alternative_batch, merge_batches
from .db import audit, database, one, utc
from .intelligence import INTENTS, enrich, extract

ACTIONS = {
    "采购询价": "核对采购身份、数量与计价单位",
    "询型匹配": "索取车桥信息或旧片编码",
    "索取目录": "确认产品方向并提供目录",
    "售后咨询": "核对订单信息并转交负责人",
    "一般互动": "核实是否有业务需求",
    "待判断": "阅读原文，确认需求",
}


def get_inquiry(db, ident):
    return one(
        db, "SELECT * FROM inquiries WHERE id=%s AND merged_into IS NULL", (ident,)
    )


def receive(event, origin, allow_model=True, actor="系统"):
    if not event.body and not event.attachment:
        raise HTTPException(422, "请输入消息或附件说明")
    key = (event.channel, event.account, event.event_id)
    lookup = (
        "SELECT inquiry_id FROM messages WHERE channel=%s AND account=%s AND event_id=%s"
    )
    with database() as db:
        prior = db.execute(lookup, key).fetchone()
        if prior:
            return {"inquiry_id": prior["inquiry_id"], "duplicate": True}
    feats = extract(event.body)
    if allow_model:
        feats = enrich(event.body, feats)
    at = utc(event.occurred_at)
    thread_key = (event.channel, event.account, event.thread_key)
    with database(True) as db:
        prior = db.execute(lookup, key).fetchone()
        if prior:
            return {"inquiry_id": prior["inquiry_id"], "duplicate": True}
        thread = db.execute(
            "SELECT inquiry_id FROM threads WHERE channel=%s AND account=%s AND thread_key=%s",
            thread_key,
        ).fetchone()
        if thread:
            ident = thread["inquiry_id"]
            current = get_inquiry(db, ident)
            if actor != "系统":
                audit(db, ident, actor, "追加来信", origin)
            if current["state"] in ("已结束", "等客户补充"):
                db.execute(
                    "UPDATE inquiries SET state=%s WHERE id=%s",
                    ("跟进中" if current["owner"] else "待处理", ident),
                )
            if at >= current["last_in"]:
                intent = (
                    feats["intent"]
                    if feats["intent"] not in {"一般互动", "待判断"}
                    else current["intent"]
                )
                db.execute(
                    "UPDATE inquiries SET last_in=%s,intent=%s WHERE id=%s",
                    (at, intent, ident),
                )
            db.execute(
                "UPDATE inquiries SET created=least(created, %s) WHERE id=%s", (at, ident)
            )
        else:
            owner = ""
            if os.getenv("AUTO_ASSIGN", "0") == "1":
                workload = {
                    r["owner"]: r["count"]
                    for r in db.execute(
                        "SELECT owner,count(*) FROM inquiries WHERE state<>'已结束' AND merged_into IS NULL GROUP BY owner"
                    )
                }
                owner = min(team(db), key=lambda x: workload.get(x, 0), default="")
            ident = db.execute(
                "INSERT INTO inquiries(buyer,owner,intent,next_action,created,last_in,state) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (
                    event.sender,
                    owner,
                    feats["intent"],
                    ACTIONS[feats["intent"]],
                    at,
                    at,
                    "待处理",
                ),
            ).fetchone()["id"]
            db.execute("INSERT INTO threads VALUES(%s,%s,%s,%s)", (*thread_key, ident))
            audit(db, ident, actor, "收到询盘", origin)
        db.execute(
            "INSERT INTO messages(inquiry_id,channel,account,event_id,thread_key,sender,body,at,origin,"
            "features,attachment) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                ident,
                *key,
                event.thread_key,
                event.sender,
                event.body,
                at,
                origin,
                json.dumps(feats, ensure_ascii=False),
                event.attachment,
            ),
        )
    return {"inquiry_id": ident, "duplicate": False}


def detail(db, ident):
    item = get_inquiry(db, ident)
    messages = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM messages WHERE inquiry_id=%s ORDER BY at,id", (ident,)
        )
    ]
    for m in messages:
        m["features"] = json.loads(m["features"])
    item["alternatives"] = alternative_batch(db, ident)
    item["messages"] = messages
    item["history"] = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM history WHERE inquiry_id=%s ORDER BY at DESC,id DESC",
            (ident,),
        )
    ]
    item["unanswered"] = any(not m["answered"] for m in messages)
    return item


def edit(db, ident, patch, actor):
    current = get_inquiry(db, ident)
    data = patch.model_dump(exclude_unset=True, exclude={"actor"})
    if (
        data.get("owner")
        and data["owner"] != current["owner"]
        and data["owner"] not in team(db)
    ):
        raise HTTPException(422, "请选择启用的团队成员")
    if "intent" in data and data["intent"] not in INTENTS:
        raise HTTPException(422, "无效意图")
    if data.get("company_id") is not None:
        one(db, "SELECT id FROM companies WHERE id=%s", (data["company_id"],))
    for k, v in data.items():
        if v is None and k != "company_id":
            raise HTTPException(422, "字段不能为空")
        if v != current[k]:
            if k == "company_id":
                db.execute(
                    "DELETE FROM alternative_batches WHERE inquiry_id=%s", (ident,)
                )
            db.execute(f"UPDATE inquiries SET {k}=%s WHERE id=%s", (v, ident))
            labels = {
                "owner": "分配负责人",
                "state": "变更状态",
                "company_id": "关联企业",
                "intent": "纠正意图",
                "next_action": "更新下一步",
            }
            audit(db, ident, actor, labels[k], str(v or "已清除"))
    return detail(db, ident)


def merge(db, source, target, actor):
    if source == target:
        raise HTTPException(422, "不能关联同一条询盘")
    a, b = get_inquiry(db, source), get_inquiry(db, target)
    if a["company_id"] and b["company_id"] and a["company_id"] != b["company_id"]:
        raise HTTPException(409, "两条询盘关联不同企业，请先核实")
    for table in ("messages", "threads", "history"):
        db.execute(
            f"UPDATE {table} SET inquiry_id=%s WHERE inquiry_id=%s", (target, source)
        )
    last_in = max(a["last_in"], b["last_in"])
    replied = max(filter(None, (a["replied"], b["replied"])), default=None)
    state = b["state"]
    pending = db.execute(
        "SELECT 1 FROM messages WHERE inquiry_id=%s AND answered=0 LIMIT 1", (target,)
    ).fetchone()
    if state in ("已结束", "等客户补充") and pending:
        state = "跟进中"
    db.execute(
        "UPDATE inquiries SET last_in=%s,created=%s,replied=%s,company_id=%s,owner=%s,state=%s WHERE id=%s",
        (
            last_in,
            min(a["created"], b["created"]),
            replied,
            b["company_id"] or a["company_id"],
            b["owner"] or a["owner"],
            state,
            target,
        ),
    )
    merge_batches(db, source, target)
    db.execute("UPDATE inquiries SET merged_into=%s WHERE id=%s", (target, source))
    audit(db, target, actor, "关联会话", f"并入询盘 #{source}，保留各渠道原文")
    return detail(db, target)
