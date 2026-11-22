"""Optional production receivers. Providers retry failed batches; event IDs make replay safe."""

import base64
import hashlib
import hmac
import json
import os
import re
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
from . import social
from .inbox import receive
from .models import Event

router = APIRouter(prefix="/webhooks")
wx_lock = Lock()

# Each parser receives its configured destination ID(s) after authentication.
SOCIAL_RECEIVERS = {
    "whatsapp": (
        "WhatsApp 商业号码",
        "WA_PHONE_NUMBER_IDS",
        "WA_APP_SECRET",
        social.whatsapp,
    ),
    "instagram": (
        "Instagram 私信",
        "IG_ACCOUNT_IDS",
        "IG_APP_SECRET",
        social.instagram,
    ),
    "x": ("X 私信、提及与回复", "X_USER_IDS", "X_CLIENT_SECRET", social.x_activity),
    "tiktok": (
        "TikTok 企业私信",
        "TIKTOK_BUSINESS_IDS",
        "TIKTOK_APP_SECRET",
        social.tiktok,
    ),
    "telegram": (
        "Telegram 机器人",
        "TELEGRAM_BOT_ID",
        "TELEGRAM_WEBHOOK_SECRET",
        social.telegram,
    ),
    "line": ("LINE 官方账号", "LINE_BOT_USER_ID", "LINE_CHANNEL_SECRET", social.line),
}
VERIFY_TOKENS = {"whatsapp": "WA_VERIFY_TOKEN", "instagram": "IG_VERIFY_TOKEN"}


def receiver_settings():
    yield (
        "meta",
        "Facebook / Messenger",
        ("META_APP_SECRET", "META_PAGE_ID", "META_VERIFY_TOKEN"),
    )
    yield "wechat", "微信客服", ("WX_AES_KEY", "WX_TOKEN", "WX_CORP_ID", "WX_KF_SECRET")
    for provider, (name, account_key, secret_key, _) in SOCIAL_RECEIVERS.items():
        keys = [account_key, secret_key]
        if provider in VERIFY_TOKENS:
            keys.append(VERIFY_TOKENS[provider])
        yield provider, name, keys


def tracked(provider, operation, *args):
    try:
        result = operation(*args)
    except Exception:
        with database(True) as db:
            db.execute(
                "INSERT INTO channel_sync(provider,last_attempt,error) VALUES(%s,%s,%s) "
                "ON CONFLICT(provider) DO UPDATE SET last_attempt=excluded.last_attempt,error=excluded.error",
                (provider, utc(), "接收失败，请检查授权与渠道重试记录"),
            )
        raise
    if result == 0:
        return result
    at = utc()
    with database(True) as db:
        db.execute(
            "INSERT INTO channel_sync VALUES(%s,%s,%s,'') ON CONFLICT(provider) DO UPDATE SET "
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
    return meta_challenge(request, "META_VERIFY_TOKEN")


def meta_challenge(request, verify_key):
    q = request.query_params
    if q.get("hub.mode") != "subscribe" or not hmac.compare_digest(
        q.get("hub.verify_token", "").encode(), setting(verify_key).encode()
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
                "SELECT value FROM cursors WHERE name=%s", ("wx:" + kfid,)
            ).fetchone()
        cursor = row["value"] if row else ""
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
                        "INSERT INTO cursors VALUES (%s,%s) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
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


@router.get("/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(request: Request):
    return meta_challenge(request, VERIFY_TOKENS["whatsapp"])


@router.get("/instagram", response_class=PlainTextResponse)
def instagram_verify(request: Request):
    return meta_challenge(request, VERIFY_TOKENS["instagram"])


def base64_hmac(secret, body):
    return base64.b64encode(hmac.digest(secret, body, "sha256")).decode("ascii")


@router.get("/x")
def x_verify(crc_token: str):
    # CRC challenges are opaque tokens; only sign a token, never an event body.
    if not re.fullmatch(r"[A-Za-z0-9_+=/.-]{1,512}", crc_token):
        raise HTTPException(400, "回调验证参数无效")
    return {
        "response_token": "sha256="
        + base64_hmac(setting("X_CLIENT_SECRET").encode(), crc_token.encode())
    }


def verify_social(provider, secret, headers, body):
    if provider in VERIFY_TOKENS:
        expected = "sha256=" + hmac.digest(secret, body, "sha256").hex()
        supplied = headers.get("X-Hub-Signature-256", "")
    elif provider == "x":
        expected = "sha256=" + base64_hmac(secret, body)
        supplied = headers.get("X-Twitter-Webhooks-Signature-OAuth2", "")
    elif provider == "line":
        expected = base64_hmac(secret, body)
        supplied = headers.get("x-line-signature", "")
    elif provider == "telegram":
        expected = secret.decode()
        supplied = headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    else:  # TikTok for Business signs timestamp + "." + raw JSON.
        parts = {}
        for item in headers.get("TikTok-Signature", "").split(","):
            key, _, value = item.strip().partition("=")
            parts[key] = value
        stamp = parts.get("t", "")
        if (
            not re.fullmatch(r"[0-9]{1,12}", stamp)
            or abs(time.time() - int(stamp)) > 300
        ):
            raise HTTPException(403, "签名时间无效")
        expected = hmac.digest(secret, stamp.encode() + b"." + body, "sha256").hex()
        supplied = parts.get("s", "")
    if not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(403, "签名无效")


def process_social(provider, body, account_config):
    name, account_key, _, parse = SOCIAL_RECEIVERS[provider]
    accounts = account_config.strip()
    if account_key.endswith("_IDS"):
        accounts = {item.strip() for item in account_config.split(",") if item.strip()}
    try:
        # Validate the whole delivery before writing its first message.
        events = list(parse(json.loads(body), accounts))
    except (ValueError, KeyError, AttributeError, TypeError, OverflowError, OSError):
        raise HTTPException(400, "渠道事件格式无效") from None
    for event in events:
        receive(event, name + "实时", allow_model=bool(event.body))
    return len(events)


@router.post("/{provider}")
async def social_callback(provider: str, request: Request):
    if provider not in SOCIAL_RECEIVERS:
        raise HTTPException(404, "未知渠道")
    _, account_key, secret_key, _ = SOCIAL_RECEIVERS[provider]
    accounts = setting(account_key)
    secret = setting(secret_key).encode()
    body = await request.body()
    verify_social(provider, secret, request.headers, body)
    accepted = await run_in_threadpool(
        tracked, provider, process_social, provider, body, accounts
    )
    return {"accepted": accepted}
