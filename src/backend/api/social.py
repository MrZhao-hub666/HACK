"""Map authenticated provider payloads to inbox events using platform identifiers."""

import json
from datetime import datetime, timezone
from typing import Annotated

from pydantic import StringConstraints

from .models import Event


class IncomingMessage(Event):
    # Keep provider text verbatim, including long posts and customer part numbers.
    body: Annotated[str, StringConstraints(strip_whitespace=False)] = ""


def at_epoch(value, divisor=1):
    return datetime.fromtimestamp(int(value) / divisor, tz=timezone.utc)


def whatsapp(payload, accounts):
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload["entry"]:
        for change in entry["changes"]:
            if change["field"] != "messages":
                continue
            value = change["value"]
            account = value["metadata"]["phone_number_id"]
            if account not in accounts or value["messaging_product"] != "whatsapp":
                continue
            names = {
                ident: contact.get("profile", {}).get("name")
                for contact in value.get("contacts", [])
                for ident in (contact.get("wa_id"), contact.get("user_id"))
                if ident
            }
            for msg in value.get("messages", []):
                kind = msg["type"]
                if kind in {"system", "reaction"}:
                    continue
                sender = msg.get("from_user_id") or msg["from"]
                part = msg.get(kind) or {}
                body = ""
                if kind == "text":
                    body = part["body"]
                elif kind in {"image", "document", "video"}:
                    body = part.get("caption", "")
                elif kind == "button":
                    body = part["text"]
                elif kind == "interactive":
                    body = part.get(part["type"], {}).get("title", "")
                yield IncomingMessage(
                    channel="whatsapp",
                    account=account,
                    event_id=msg["id"],
                    thread_key=sender,
                    sender=names.get(sender) or sender,
                    body=body,
                    attachment="" if kind == "text" else kind,
                    occurred_at=at_epoch(msg["timestamp"]),
                )


def instagram(payload, accounts):
    if payload.get("object") != "instagram":
        return
    for entry in payload["entry"]:
        account = entry["id"]
        if account not in accounts:
            continue
        for item in entry.get("messaging", []):
            msg = item.get("message")
            if (
                not msg
                or not msg.get("mid")
                or msg.get("is_echo")
                or msg.get("is_self")
                or msg.get("is_deleted")
            ):
                continue
            sender = item["sender"]["id"]
            if sender == account or item["recipient"]["id"] != account:
                continue
            attachment = "、".join(a["type"] for a in msg.get("attachments", []))
            yield IncomingMessage(
                channel="instagram",
                account=account,
                event_id=msg["mid"],
                thread_key=sender,
                sender=sender,
                body=msg.get("text", ""),
                attachment=attachment
                or ("" if msg.get("text") else "请在 Instagram 查看原消息"),
                occurred_at=at_epoch(item["timestamp"], 1000),
            )


def x_activity(payload, accounts):
    data = payload["data"]
    account = data["filter"].get("user_id")
    if account not in accounts:
        return
    kind = data["event_type"]
    content = data["payload"]
    if kind == "dm.received":
        for item in content["direct_message_events"]:
            if item["type"] != "message_create":
                continue
            msg = item["message_create"]
            sender = msg["sender_id"]
            if sender == account or msg["target"]["recipient_id"] != account:
                continue
            fields = msg["message_data"]
            name = content.get("users", {}).get(sender, {}).get("data", {}).get("name")
            yield IncomingMessage(
                channel="x_dm",
                account=account,
                event_id=item["id"],
                sender=name or sender,
                thread_key=sender,
                body=fields.get("text", ""),
                attachment=fields.get("attachment", {}).get("type", ""),
                occurred_at=at_epoch(item["created_timestamp"], 1000),
            )
    elif kind == "chat.received" and content["sender_id"] != account:
        yield IncomingMessage(
            channel="x_dm",
            account=account,
            event_id=content["id"],
            sender=content["sender_id"],
            thread_key="chat:" + content["conversation_id"],
            attachment="X 加密聊天来信，请在 X 查看原文",
            occurred_at=at_epoch(content["created_at_msec"], 1000),
        )
    elif kind in {"post.mention.create", "post.reply.create"}:
        sender = content["author_id"]
        if sender == account:
            return
        yield IncomingMessage(
            channel="x_post",
            account=account,
            event_id=content["id"],
            sender=sender,
            thread_key=f"{content['conversation_id']}:{sender}",
            body=content.get("note_tweet", {}).get("text") or content["text"],
            occurred_at=datetime.fromisoformat(content["created_at"]),
        )


def tiktok(payload, accounts):
    if (
        payload.get("event") != "im_receive_msg"
        or payload["user_openid"] not in accounts
    ):
        return
    account = payload["user_openid"]
    msg = json.loads(payload["content"])
    if msg["to_user"]["id"] != account or msg["from_user"]["id"] == account:
        return
    kind = msg["type"]
    if kind == "reaction":
        return
    yield IncomingMessage(
        channel="tiktok",
        account=account,
        event_id=msg["message_id"],
        thread_key=msg["conversation_id"],
        sender=msg.get("from") or msg["from_user"]["id"],
        body=msg["text"]["body"] if kind == "text" else "",
        attachment="" if kind == "text" else kind,
        occurred_at=at_epoch(msg["timestamp"], 1000),
    )


def telegram(payload, account):
    msg = payload.get("message")
    if not msg or msg["chat"]["type"] != "private" or msg["from"]["is_bot"]:
        return
    chat_id = str(msg["chat"]["id"])
    types = (
        "photo",
        "document",
        "video",
        "voice",
        "audio",
        "sticker",
        "animation",
        "video_note",
        "location",
        "venue",
        "contact",
        "poll",
        "dice",
        "paid_media",
    )
    kind = next((k for k in types if k in msg), "")
    body = msg.get("text") or msg.get("caption", "")
    if not kind and not body:
        return
    author = msg["from"]
    yield IncomingMessage(
        channel="telegram",
        account=account,
        event_id=f"{chat_id}:{msg['message_id']}",
        thread_key=chat_id,
        sender=author.get("username") or author.get("first_name") or chat_id,
        body=body,
        attachment=kind,
        occurred_at=at_epoch(msg["date"]),
    )


def line(payload, account):
    if payload["destination"] != account:
        return
    for item in payload["events"]:
        if item["type"] != "message" or item["source"]["type"] != "user":
            continue
        sender = item["source"].get("userId")
        msg = item["message"]
        # A user ID may be withheld. Keep each such message on its own ticket.
        yield IncomingMessage(
            channel="line",
            account=account,
            event_id=msg["id"],
            thread_key=sender or ("message:" + msg["id"]),
            sender=sender or "LINE 用户",
            body=msg.get("text", ""),
            attachment="" if msg["type"] == "text" else msg["type"],
            occurred_at=at_epoch(item["timestamp"], 1000),
        )
