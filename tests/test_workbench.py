import base64
import hashlib
import hmac
import json
import os
import struct
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from src.api.main import app
from src.api import channels, prospects


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DEMO_DATA", "0")
    monkeypatch.setenv("ENABLE_SIMULATOR", "1")
    for key in ("BRAVE_API_KEY", "LLM_API_KEY", "AUTO_ASSIGN"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as c:
        yield c


def event(c, event_id="e1", **kw):
    data = {
        "event_id": event_id,
        "channel": "messenger",
        "sender": "Buyer",
        "thread_key": "thread",
        "body": "Can you quote 100 sets of WVA 29289 for our workshop?",
        **kw,
    }
    return c.post("/api/demo/inquiries", json=data)


def test_discovery_and_company(client):
    rows = client.post(
        "/api/discovery/search", json={"market": "MY", "kind": "维修厂"}
    ).json()["items"]
    assert len(rows) == 2
    c = client.post("/api/companies", json=rows[0]).json()
    assert c["procurement"] == "待核实"
    assert client.post("/api/companies", json=rows[0]).json()["id"] == c["id"]
    data = {k: v for k, v in rows[0].items() if k not in ("source", "checked")}
    data["procurement"] = "可直接采购"
    assert client.put(f"/api/companies/{c['id']}", json=data).json()["reviewed"] == 1
    assert (
        client.post(
            "/api/companies", json={**data, "website": "javascript:alert(1)"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/discovery/search", json={"market": "巴西", "mode": "live"}
        ).status_code
        == 503
    )
    assert (
        client.post("/api/discovery/search", json={"market": "巴西"}).json()["items"]
        == []
    )


def test_live_provider(client, monkeypatch):
    import httpx

    monkeypatch.setenv("BRAVE_API_KEY", "dummy")
    calls = []

    def get(url, **kw):
        calls.append(kw["params"]["q"])
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://example.org/services",
                            "title": "Fleet Co",
                            "description": "Our fleet has its own workshop",
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(prospects.httpx, "get", get)
    out = client.post(
        "/api/discovery/search", json={"market": "巴西", "kind": "车队", "mode": "live"}
    ).json()
    assert "Brazil" in calls[0] and out["items"][0]["source"] == "实时网页搜索"


def test_idempotency_and_handoff(client):
    ids = list(ThreadPoolExecutor(5).map(lambda _: event(client).json(), range(10)))
    assert sum(not r["duplicate"] for r in ids) == 1
    ident = ids[0]["inquiry_id"]
    base = f"/api/inquiries/{ident}"
    row = client.get(base).json()
    assert row["messages"][0]["features"]["quantities"] == ["100 sets"]
    assert row["messages"][0]["features"]["codes"] == ["WVA 29289"]
    assert (
        client.patch(
            base, json={"owner": "林悦", "next_action": "核对装套单位"}
        ).json()["owner"]
        == "林悦"
    )
    assert (
        client.post(base + "/notes", json={"text": "等待技术回复"}).status_code == 200
    )
    assert (
        client.post(
            base + "/reply", json={"text": "已在平台核对数量", "actor": "林悦"}
        ).json()["unanswered"]
        is False
    )
    event(
        client,
        "later",
        body="And can you quote 20 pieces?",
        occurred_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
    )
    latest = client.get(base).json()
    assert (
        latest["unanswered"]
        and len(latest["messages"]) == 2
        and latest["state"] == "跟进中"
    )
    event(client, "older", body="Thank you", occurred_at="2025-01-01T00:00:00Z")
    assert client.get(base).json()["intent"] == "采购询价"


def test_cross_channel_merge(client):
    first = event(client).json()["inquiry_id"]
    second = event(client, channel="wechat_kf").json()["inquiry_id"]
    assert first != second
    url = f"/api/inquiries/{second}/merge"
    assert client.post(url, json={"target_id": second}).status_code == 422
    assert len(client.post(url, json={"target_id": first}).json()["messages"]) == 2
    assert len(client.get("/api/inquiries").json()) == 1
    assert event(client, "e2", channel="wechat_kf").json()["inquiry_id"] == first
    assert event(client, channel="wechat_kf").json() == {
        "duplicate": True,
        "inquiry_id": first,
    }


def test_validation_assignment_and_restart(client, monkeypatch):
    assert event(client, body="").status_code == 422
    assert event(client, occurred_at="2026-01-01T12:00:00").status_code == 422
    monkeypatch.setenv("AUTO_ASSIGN", "1")
    a = event(client).json()["inquiry_id"]
    b = event(client, "e2", thread_key="new").json()["inquiry_id"]
    assert (
        client.get(f"/api/inquiries/{a}").json()["owner"]
        != client.get(f"/api/inquiries/{b}").json()["owner"]
    )
    monkeypatch.setenv("ENABLE_SIMULATOR", "0")
    assert event(client).status_code == 403
    with TestClient(app) as another:
        assert len(another.get("/api/inquiries").json()) == 2


def test_meta_signature_and_replay(client, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setenv("META_PAGE_ID", "pg")
    monkeypatch.setenv("META_VERIFY_TOKEN", "verify")
    assert (
        client.get(
            "/webhooks/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify",
                "hub.challenge": "abc",
            },
        ).text
        == "abc"
    )
    data = {
        "entry": [
            {
                "id": "pg",
                "messaging": [
                    {
                        "sender": {"id": "buyer"},
                        "message": {"mid": "mid", "text": "price?"},
                        "timestamp": 1780000000000,
                    }
                ],
            }
        ]
    }
    body = json.dumps(data).encode()
    assert client.post("/webhooks/meta", content=body).status_code == 403
    headers = {
        "X-Hub-Signature-256": "sha256="
        + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    }
    for _ in range(2):
        assert (
            client.post("/webhooks/meta", content=body, headers=headers).status_code
            == 200
        )
    rows = client.get("/api/inquiries").json()
    assert (
        len(rows) == 1
        and rows[0]["origin"] == "Meta 实时"
        and rows[0]["message_count"] == 1
    )


def test_wechat_verified_callback(client, monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("WX_AES_KEY", base64.b64encode(key).decode().rstrip("="))
    for var, val in {
        "WX_TOKEN": "token",
        "WX_CORP_ID": "corp",
        "WX_KF_SECRET": "secret",
    }.items():
        monkeypatch.setenv(var, val)

    def encrypted(s):
        plain = b"0" * 16 + struct.pack(">I", len(s)) + s + b"corp"
        pad = 32 - len(plain) % 32
        encrypt = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
        cipher = base64.b64encode(
            encrypt.update(plain + bytes([pad]) * pad) + encrypt.finalize()
        ).decode()
        sig = hashlib.sha1(
            "".join(sorted(["token", "1", "nonce", cipher])).encode()
        ).hexdigest()
        return cipher, dict(timestamp="1", nonce="nonce", msg_signature=sig)

    cipher, q = encrypted(b"hello")
    assert (
        client.get("/webhooks/wechat", params={**q, "echostr": cipher}).text == "hello"
    )
    calls = []

    def remote(method, url, **kw):
        if url.endswith("gettoken"):
            return {"access_token": "demo"}
        calls.append(kw["json"]["cursor"])
        return {
            "next_cursor": "next",
            "msg_list": [
                {
                    "origin": 3,
                    "msgid": "abc",
                    "msgtype": "text",
                    "external_userid": "customer",
                    "send_time": 1780000000,
                    "text": {"content": "想询价 50 套"},
                }
            ],
        }

    monkeypatch.setattr(channels, "remote_json", remote)
    plain = b"<xml><Event>kf_msg_or_event</Event><OpenKfId>kf1</OpenKfId><Token>t</Token></xml>"
    cipher, q = encrypted(plain)
    for _ in range(2):
        assert (
            client.post(
                "/webhooks/wechat",
                params=q,
                content=f"<xml><Encrypt>{cipher}</Encrypt></xml>",
            ).text
            == "success"
        )
    assert calls == ["", "next"]
    assert client.get("/api/inquiries").json()[0]["message_count"] == 1


def test_reply_race_and_merged_unanswered(client):
    ident = event(client).json()["inquiry_id"]
    base = f"/api/inquiries/{ident}"
    seen = client.get(base).json()["messages"][0]["id"]
    event(client, "second", body="What about delivery?")
    assert (
        client.post(
            base + "/reply", json={"text": "已回复", "through_message_id": seen}
        ).status_code
        == 409
    )
    other = event(client, "other", channel="wechat_kf").json()["inquiry_id"]
    client.post(base + "/reply", json={"text": "已回复当前询盘"})
    merged = client.post(
        f"/api/inquiries/{other}/merge", json={"target_id": ident}
    ).json()
    assert merged["unanswered"] and merged["state"] == "跟进中"
    assert sum(not m["answered"] for m in merged["messages"]) == 1


def test_preserve_unhandled_night_message_after_morning_followup(client, monkeypatch):
    from datetime import timedelta, timezone

    now = datetime.now(timezone(timedelta(hours=8)))
    start = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    event(client, occurred_at=(start + timedelta(hours=3)).isoformat())
    event(client, "day-message", occurred_at=(start + timedelta(hours=13)).isoformat())
    rows = client.get("/api/inquiries").json()
    assert rows[0]["night_unanswered"] == 1
    client.post("/api/inquiries/%s/reply" % rows[0]["id"], json={"text": "已确认"})
    assert client.get("/api/inquiries").json()[0]["night_unanswered"] == 0
