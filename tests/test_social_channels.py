import base64
import hashlib
import hmac
import json
import time

import pytest


TEXT = "  请报价 WVA 29289，100 sets  "
SEC = 1_790_000_000
MS = SEC * 1000
KEY = "local-protocol-fixture"
CONFIG = {
    "whatsapp": {
        "WA_APP_SECRET": KEY,
        "WA_VERIFY_TOKEN": "verify",
        "WA_PHONE_NUMBER_IDS": "phone, other",
    },
    "instagram": {
        "IG_APP_SECRET": KEY,
        "IG_VERIFY_TOKEN": "verify",
        "IG_ACCOUNT_IDS": "shop",
    },
    "x": {"X_CLIENT_SECRET": KEY, "X_USER_IDS": "shop"},
    "tiktok": {"TIKTOK_APP_SECRET": KEY, "TIKTOK_BUSINESS_IDS": "shop"},
    "telegram": {"TELEGRAM_WEBHOOK_SECRET": KEY, "TELEGRAM_BOT_ID": "123"},
    "line": {"LINE_CHANNEL_SECRET": KEY, "LINE_BOT_USER_ID": "shop"},
}


def configure(monkeypatch, provider):
    for key, value in CONFIG[provider].items():
        monkeypatch.setenv(key, value)


def deliver(client, provider, payload, *, key=KEY, timestamp=None):
    body = json.dumps(payload, ensure_ascii=False).encode()
    digest = hmac.new(key.encode(), body, hashlib.sha256)
    b64 = base64.b64encode(digest.digest()).decode()
    if provider in {"whatsapp", "instagram"}:
        headers = {"X-Hub-Signature-256": "sha256=" + digest.hexdigest()}
    elif provider == "x":
        headers = {"X-Twitter-Webhooks-Signature-OAuth2": "sha256=" + b64}
    elif provider == "tiktok":
        stamp = str(timestamp if timestamp is not None else int(time.time()))
        sig = hmac.new(
            key.encode(), stamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        headers = {"TikTok-Signature": f"t={stamp},s={sig}"}
    elif provider == "line":
        headers = {"x-line-signature": b64}
    else:
        headers = {"X-Telegram-Bot-Api-Secret-Token": key}
    return client.post("/webhooks/" + provider, content=body, headers=headers)


def wa(account="phone", ident="wamid.1", sender="buyer", at=SEC):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": account},
                            "contacts": [
                                {
                                    "wa_id": sender,
                                    "profile": {"name": "Same display name"},
                                }
                            ],
                            "messages": [
                                {
                                    "id": ident,
                                    "from": sender,
                                    "type": "text",
                                    "text": {"body": TEXT},
                                    "timestamp": str(at),
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def ig():
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "shop",
                "messaging": [
                    {
                        "sender": {"id": "buyer"},
                        "recipient": {"id": "shop"},
                        "timestamp": MS,
                        "message": {"mid": "ig1", "text": TEXT},
                    }
                ],
            }
        ],
    }


def x(event_type, payload):
    return {
        "data": {
            "event_uuid": "delivery-id",
            "event_type": event_type,
            "filter": {"user_id": "shop"},
            "payload": payload,
        }
    }


def dm():
    return x(
        "dm.received",
        {
            "direct_message_events": [
                {
                    "type": "message_create",
                    "id": "dm1",
                    "created_timestamp": str(MS),
                    "message_create": {
                        "sender_id": "buyer",
                        "target": {"recipient_id": "shop"},
                        "message_data": {"text": TEXT},
                    },
                }
            ]
        },
    )


def tt():
    return {
        "client_key": "app",
        "event": "im_receive_msg",
        "user_openid": "shop",
        "create_time": SEC,
        "content": json.dumps(
            {
                "from": "buyer name",
                "from_user": {"id": "buyer", "role": "personal_account"},
                "to_user": {"id": "shop", "role": "business_account"},
                "conversation_id": "conv",
                "message_id": "tt1",
                "timestamp": MS,
                "type": "text",
                "text": {"body": TEXT},
            }
        ),
    }


def tg():
    return {
        "update_id": 99,
        "message": {
            "chat": {"id": 4242, "type": "private"},
            "from": {"id": 4242, "first_name": "buyer", "is_bot": False},
            "message_id": 1,
            "text": TEXT,
            "date": SEC,
        },
    }


def line():
    return {
        "destination": "shop",
        "events": [
            {
                "webhookEventId": "event-1",
                "type": "message",
                "message": {"type": "text", "id": "line1", "text": TEXT},
                "source": {"type": "user", "userId": "buyer"},
                "timestamp": MS,
            }
        ],
    }


@pytest.mark.parametrize(
    "provider,make,channel,thread",
    [
        ("whatsapp", wa, "whatsapp", "buyer"),
        ("instagram", ig, "instagram", "buyer"),
        ("x", dm, "x_dm", "buyer"),
        ("tiktok", tt, "tiktok", "conv"),
        ("telegram", tg, "telegram", "4242"),
        ("line", line, "line", "buyer"),
    ],
)
def test_signed_inbox_roundtrip(client, monkeypatch, provider, make, channel, thread):
    for key in CONFIG[provider]:
        monkeypatch.delenv(key, raising=False)
    payload = make()
    assert deliver(client, provider, payload).status_code == 503
    configure(monkeypatch, provider)
    assert deliver(client, provider, payload, key="wrong").status_code == 403
    assert not client.get("/api/inquiries").json()
    config = client.get("/api/config").json()
    row = next(r for r in config["receivers"] if r["id"] == provider)
    assert row["configured"] and row["sync"] is None and KEY not in str(config)
    for _ in range(2):
        assert deliver(client, provider, payload).json() == {"accepted": 1}
    (inquiry,) = client.get("/api/inquiries").json()
    (msg,) = client.get(f"/api/inquiries/{inquiry['id']}").json()["messages"]
    assert (msg["channel"], msg["body"], msg["thread_key"]) == (channel, TEXT, thread)
    assert msg["features"]["intent"] == "采购询价" and "实时" in msg["origin"]


def test_non_buyer_and_unrelated_events(client, monkeypatch):
    receipt = wa()
    value = receipt["entry"][0]["changes"][0]["value"]
    del value["messages"]
    value["statuses"] = [{"id": "wamid.1", "status": "read"}]
    echo = ig()
    echo["entry"][0]["messaging"][0]["message"]["is_echo"] = True
    handoff = ig()
    handoff["entry"][0]["messaging"][0]["message"] = {"admin_text": "handoff"}
    group = tg()
    group["message"]["chat"]["type"] = "group"
    for provider, payload in [
        ("whatsapp", wa("foreign")),
        ("whatsapp", receipt),
        ("instagram", echo),
        ("instagram", handoff),
        ("x", x("chat.sent", {})),
        ("tiktok", {**tt(), "event": "im_mark_read_msg"}),
        ("tiktok", {**tt(), "event": "im_receive_msg_eu"}),
        ("telegram", group),
        ("line", {**line(), "destination": "foreign"}),
        ("line", {"destination": "shop", "events": []}),
    ]:
        configure(monkeypatch, provider)
        assert deliver(client, provider, payload).json() == {"accepted": 0}
    assert not client.get("/api/inquiries").json()
    assert all(
        row["sync"] is None for row in client.get("/api/config").json()["receivers"]
    )
    assert (
        deliver(client, "tiktok", tt(), timestamp=int(time.time()) - 3600).status_code
        == 403
    )


def test_whatsapp_account_thread_and_lifecycle(client, monkeypatch):
    configure(monkeypatch, "whatsapp")
    for payload in [wa(), wa("other"), wa(ident="wamid.2", sender="buyer2")]:
        assert deliver(client, "whatsapp", payload).is_success
    rows = client.get("/api/inquiries").json()
    assert len(rows) == 3
    first, other, _ = sorted(r["id"] for r in rows)
    assert client.post(
        f"/api/inquiries/{other}/merge", json={"target_id": first}
    ).is_success
    assert deliver(client, "whatsapp", wa("other")).is_success
    assert client.post(
        f"/api/inquiries/{first}/reply", json={"text": "已回复"}
    ).is_success
    assert deliver(client, "whatsapp", wa("other", "follow-up", at=SEC + 20)).is_success
    assert deliver(client, "whatsapp", wa("phone", "late", at=SEC - 90)).is_success
    detail = client.get(f"/api/inquiries/{first}").json()
    assert len(detail["messages"]) == 4
    assert [m["event_id"] for m in detail["messages"]][::3] == ["late", "follow-up"]
    assert detail["messages"][-1]["answered"] == 0 and detail["state"] == "跟进中"


def test_xchat_and_public_reply(client, monkeypatch):
    configure(monkeypatch, "x")
    chat = x(
        "chat.received",
        {
            "id": "encrypted",
            "sender_id": "buyer",
            "conversation_id": "1:2",
            "created_at_msec": str(MS),
            "encoded_event": "opaque-sample",
        },
    )
    assert deliver(client, "x", chat).is_success
    post = {
        "id": "post",
        "author_id": "author",
        "conversation_id": "public-thread",
        "created_at": "2026-06-01T00:00:00Z",
        "text": TEXT,
    }
    for kind in ("post.mention.create", "post.reply.create"):
        assert deliver(client, "x", x(kind, post)).is_success
    dm_row, public = sorted(
        client.get("/api/inquiries").json(), key=lambda r: r["channel"]
    )
    (msg,) = client.get(f"/api/inquiries/{dm_row['id']}").json()["messages"]
    assert (
        not msg["body"]
        and "加密聊天" in msg["attachment"]
        and "opaque-sample" not in str(msg)
    )
    assert public["message_count"] == 1 and public["preview"] == TEXT


def test_subscription_challenges(client, monkeypatch):
    for provider in ("whatsapp", "instagram"):
        configure(monkeypatch, provider)
        q = {
            "hub.mode": "subscribe",
            "hub.challenge": "123",
            "hub.verify_token": "invalid",
        }
        assert client.get("/webhooks/" + provider, params=q).status_code == 403
        q["hub.verify_token"] = "verify"
        assert client.get("/webhooks/" + provider, params=q).text == "123"
    configure(monkeypatch, "x")
    expected = hmac.new(KEY.encode(), b"crc_test", hashlib.sha256).digest()
    assert client.get("/webhooks/x?crc_token=crc_test").json() == {
        "response_token": "sha256=" + base64.b64encode(expected).decode()
    }


def test_authenticated_invalid_batch_is_retryable(client, monkeypatch):
    configure(monkeypatch, "whatsapp")
    payload = wa()
    value = payload["entry"][0]["changes"][0]["value"]
    value["messages"].append({"id": "incomplete"})
    assert deliver(client, "whatsapp", payload).status_code == 400
    assert not client.get("/api/inquiries").json()
    row = next(
        r
        for r in client.get("/api/config").json()["receivers"]
        if r["id"] == "whatsapp"
    )
    assert row["sync"]["error"] and row["sync"]["last_success"] is None
    value["messages"].pop()
    assert deliver(client, "whatsapp", payload).is_success
    row = next(
        r
        for r in client.get("/api/config").json()["receivers"]
        if r["id"] == "whatsapp"
    )
    assert not row["sync"]["error"] and row["sync"]["last_success"]
