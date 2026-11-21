"""Optional production receivers. Providers retry failed batches; event IDs make replay safe."""

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from datetime import datetime, timezone
from threading import Lock
from xml.etree import ElementTree as ET

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from .db import database, utc
from .inbox import receive
from .models import Event

router = APIRouter(prefix="/webhooks")
wx_lock = Lock()


def tracked(provider, operation, *args):
    try:
        result = operation(*args)
    except Exception:
        with database(True) as db:
            db.execute(
                "INSERT INTO channel_sync(provider,last_attempt,error) VALUES(?,?,?) "
                "ON CONFLICT(provider) DO UPDATE SET last_attempt=excluded.last_attempt,error=excluded.error",
                (provider, utc(), "接收失败，请检查授权与渠道重试记录"),
            )
        raise
    at = utc()
    with database(True) as db:
        db.execute(
            "INSERT INTO channel_sync VALUES(?,?,?,'') ON CONFLICT(provider) DO UPDATE SET "
            "last_attempt=excluded.last_attempt,last_success=excluded.last_success,error=''",
            (provider, at, at),
        )
    return result


def setting(name):
    value = os.getenv(name)
    if not value:
        raise HTTPException(503, "渠道尚未配置")
    return value


def remote_json(method, url, **kwargs):
    try:
        r = httpx.request(method, url, timeout=8, **kwargs)
        r.raise_for_status()
        obj = r.json()
        if obj.get("errcode", 0):
            raise ValueError("provider error")
        return obj
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(502, "渠道数据读取失败，等待重试") from exc


@router.get("/meta", response_class=PlainTextResponse)
def meta_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") != "subscribe" or not hmac.compare_digest(
        q.get("hub.verify_token", ""), setting("META_VERIFY_TOKEN")
    ):
        raise HTTPException(403, "验证失败")
    return q.get("hub.challenge", "")


def unix_at(n):
    return datetime.fromtimestamp(float(n or time.time()), tz=timezone.utc)


def process_meta(payload):
    page = setting("META_PAGE_ID")
    count = 0
    for entry in payload.get("entry", []):
        if str(entry.get("id")) != page:
            continue
        for m in entry.get("messaging", []):
            msg = m.get("message", {})
            if not msg.get("mid") or msg.get("is_echo"):
                continue
            sender = str(m["sender"]["id"])
            receive(
                Event(
                    channel="messenger",
                    account=page,
                    event_id=msg["mid"],
                    thread_key=sender,
                    sender=sender,
                    body=msg.get("text", ""),
                    attachment="、".join(
                        x.get("type", "附件") for x in msg.get("attachments", [])
                    ),
                    occurred_at=unix_at(m["timestamp"] / 1000),
                ),
                "Meta 实时",
            )
            count += 1
        for change in entry.get("changes", []):
            v = change.get("value", {})
            if (
                change.get("field") == "feed"
                and v.get("item") == "comment"
                and v.get("verb") == "add"
            ):
                author = v.get("from") or {}
                if str(author.get("id", "")) == page:
                    continue
                cid = str(v["comment_id"])
                sender = str(author.get("id") or cid)
                receive(
                    Event(
                        channel="facebook_comment",
                        account=page,
                        event_id=cid,
                        thread_key=f"{v.get('post_id', cid)}:{sender}",
                        sender=author.get("name") or sender,
                        body=v.get("message", ""),
                        attachment="" if v.get("message") else "评论附件／未提供文字",
                        occurred_at=unix_at(v.get("created_time") or entry.get("time")),
                    ),
                    "Meta 实时",
                )
                count += 1
            if change.get("field") == "leadgen":
                lead_id = str(v["leadgen_id"])
                if not lead_id.isdigit():
                    raise HTTPException(400, "无效线索编号")
                graph = setting("META_GRAPH_VERSION")
                lead = remote_json(
                    "GET",
                    f"https://graph.facebook.com/{graph}/{lead_id}",
                    params={"fields": "field_data,created_time"},
                    headers={"Authorization": "Bearer " + setting("META_PAGE_TOKEN")},
                )
                fields = {
                    row["name"]: ", ".join(map(str, row["values"]))
                    for row in lead.get("field_data", [])
                }
                receive(
                    Event(
                        channel="facebook_form",
                        account=page,
                        event_id=lead_id,
                        thread_key=lead_id,
                        sender=fields.get("company_name")
                        or fields.get("full_name")
                        or "表单买家",
                        body="\n".join(f"{k}: {val}" for k, val in fields.items())
                        or "提交了表单",
                        occurred_at=unix_at(v.get("created_time")),
                    ),
                    "Meta 实时",
                )
                count += 1
    return count


@router.post("/meta")
async def meta_events(request: Request):
    secret = setting("META_APP_SECRET")
    body = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(
        expected, request.headers.get("X-Hub-Signature-256", "")
    ):
        raise HTTPException(403, "签名无效")
    return {
        "accepted": await run_in_threadpool(
            tracked, "meta", process_meta, json.loads(body)
        )
    }


def decode_wechat(q, ciphertext):
    token, corp, key64 = (
        setting("WX_TOKEN"),
        setting("WX_CORP_ID"),
        setting("WX_AES_KEY"),
    )
    data = "".join(
        sorted([token, q.get("timestamp", ""), q.get("nonce", ""), ciphertext])
    )
    expected = hashlib.sha1(data.encode()).hexdigest()
    if not hmac.compare_digest(expected, q.get("msg_signature", "")):
        raise HTTPException(403, "微信签名无效")
    try:
        key = base64.b64decode(key64 + "=")
        decrypt = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
        plain = decrypt.update(base64.b64decode(ciphertext)) + decrypt.finalize()
        pad = plain[-1]
        if not 1 <= pad <= 32 or plain[-pad:] != bytes([pad]) * pad:
            raise ValueError()
        plain = plain[:-pad]
        size = struct.unpack(">I", plain[16:20])[0]
        if plain[20 + size :] != corp.encode():
            raise ValueError()
        return plain[20 : 20 + size].decode()
    except (ValueError, IndexError, struct.error) as exc:
        raise HTTPException(400, "回调密文无效") from exc


@router.get("/wechat", response_class=PlainTextResponse)
def wx_verify(request: Request):
    return decode_wechat(request.query_params, request.query_params.get("echostr", ""))


def sync_wechat(kfid, token):
    with wx_lock:
        auth = remote_json(
            "GET",
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={
                "corpid": setting("WX_CORP_ID"),
                "corpsecret": setting("WX_KF_SECRET"),
            },
        )
        with database() as db:
            row = db.execute(
                "SELECT value FROM cursors WHERE name=?", ("wx:" + kfid,)
            ).fetchone()
        cursor = row[0] if row else ""
        while True:
            result = remote_json(
                "POST",
                "https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg",
                params={"access_token": auth["access_token"]},
                json={
                    "cursor": cursor,
                    "token": token,
                    "open_kfid": kfid,
                    "limit": 100,
                },
            )
            for msg in result.get("msg_list", []):
                if msg.get("origin") != 3 or msg.get("msgtype") == "event":
                    continue
                sender = msg["external_userid"]
                kind = msg["msgtype"]
                text = msg.get("text", {}).get("content", "")
                receive(
                    Event(
                        channel="wechat_kf",
                        account=kfid,
                        event_id=msg["msgid"],
                        thread_key=sender,
                        sender=sender,
                        body=text,
                        attachment="" if kind == "text" else kind,
                        occurred_at=unix_at(msg["send_time"]),
                    ),
                    "微信客服实时",
                )
            nxt = result.get("next_cursor", "")
            if result.get("has_more") and (not nxt or nxt == cursor):
                raise HTTPException(502, "微信游标未前进")
            if nxt:
                with database(True) as db:
                    db.execute(
                        "INSERT INTO cursors VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                        ("wx:" + kfid, nxt),
                    )
                cursor = nxt
            if not result.get("has_more"):
                return


@router.post("/wechat", response_class=PlainTextResponse)
async def wx_callback(request: Request):
    raw = ET.fromstring(await request.body())
    event = ET.fromstring(
        decode_wechat(request.query_params, raw.findtext("Encrypt", ""))
    )
    if event.findtext("Event") == "kf_msg_or_event":
        await run_in_threadpool(
            tracked,
            "wechat",
            sync_wechat,
            event.findtext("OpenKfId", ""),
            event.findtext("Token", ""),
        )
    return "success"
