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
from src.api.accounts import create_account, encode_password
from src.api.db import database
from src.api import channels, prospects


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DEMO_DATA", "0")
    monkeypatch.setenv("ENABLE_SIMULATOR", "1")
    for key in ("BRAVE_API_KEY", "LLM_API_KEY", "AUTO_ASSIGN"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as c:
        password = "Workbench-fixture-123"
        encoded = encode_password(password)
        with database(True) as db:
            create_account(db, "lin.yue", "林悦", "admin", encoded, False)
            create_account(db, "chen.zhou", "陈舟", "sales", encoded, False)
        c.headers["X-Workspace-Request"] = "1"
        assert c.post(
            "/api/auth/login", json={"username": "lin.yue", "password": password}
        ).is_success
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
        another.cookies.update(client.cookies)
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


def test_alternatives_claim_feedback_and_evidence(client):
    src = client.post(
        "/api/companies",
        json={"name": "Test Haulage", "kind": "车队", "country": "马来西亚"},
    ).json()
    ident = event(client).json()["inquiry_id"]
    path = f"/api/inquiries/{ident}"
    search = path + "/alternatives"
    criteria = {"source_company_id": src["id"]}
    assert client.post(search, json=criteria).status_code == 409
    client.patch(path, json={"company_id": src["id"]})
    assert client.post(search, json=criteria).status_code == 409
    result = client.post(search, json={**criteria, "claim": True}).json()
    cards = result["items"]
    assert len(cards) == 3 and all(
        not c["proof"] and c["profile"]["procurement"] == "待核实" for c in cards
    )
    assert client.get(path).json()["owner"] == "林悦"
    assert len(client.get("/api/alternatives/mine").json()) == 3
    card = next(c for c in cards if "Swift" in c["profile"]["name"])
    endpoint = search + "/" + str(card["id"])
    assert (
        client.post(
            endpoint + "/proof",
            json={"url": "invalid", "note": "双方参加同一次公开物流项目投标"},
        ).status_code
        == 422
    )
    proof = {
        "url": "https://tender.example/lot-4",
        "note": "测试资料：双方参加同一物流项目投标",
    }
    confirmed = client.post(endpoint + "/proof", json=proof).json()["items"]
    assert (
        next(c for c in confirmed if c["id"] == card["id"])["proof"]["actor"] == "林悦"
    )
    client.delete(endpoint + "/proof")
    assert all(
        c["proof"] is None for c in client.get(path).json()["alternatives"]["items"]
    )
    for _ in range(2):
        assert client.post(
            endpoint + "/feedback", json={"decision": "adopted"}
        ).is_success
    saved = [
        c
        for c in client.get("/api/companies").json()
        if c["name"] == card["profile"]["name"]
    ]
    assert (
        len(saved) == 1
        and saved[0]["owner"] == "林悦"
        and saved[0]["evidence_url"] == card["profile"]["evidence_url"]
    )
    other = next(c for c in cards if c["id"] != card["id"])
    for _ in range(2):
        assert client.post(
            search + f"/{other['id']}/feedback", json={"decision": "dismissed"}
        ).is_success
    fresh = client.post(search, json=criteria).json()["items"]
    assert other["id"] not in [c["id"] for c in fresh]
    assert (
        next(c for c in fresh if c["id"] == card["id"])["archive_id"] == saved[0]["id"]
    )
    assert len(client.get("/api/alternatives/mine").json()) == 1
    assert client.get(path).json()["state"] == "待处理"


def test_alternative_owner_and_merge(client):
    with TestClient(app, headers={"X-Workspace-Request": "1"}) as other:
        assert other.post(
            "/api/auth/login",
            json={"username": "chen.zhou", "password": "Workbench-fixture-123"},
        ).is_success
        swift = other.post(
            "/api/companies",
            json={
                "name": "Swift Haulage Berhad",
                "country": "MY",
                "kind": "车队",
                "procurement": "委托采购",
                "website": "https://swiftlogistics.com.my",
                "notes": "原销售记录",
            },
        ).json()
        src = client.post(
            "/api/companies",
            json={
                "name": "L&R Haulage",
                "country": "MY",
                "kind": "车队",
                "website": "https://lrh.com.my",
            },
        ).json()
        a = event(client).json()["inquiry_id"]
        b = event(client, "evt2", thread_key="second").json()["inquiry_id"]
        root = f"/api/inquiries/{a}"
        client.patch(root, json={"company_id": src["id"], "owner": "陈舟"})
        result = client.post(
            root + "/alternatives", json={"source_company_id": src["id"]}
        ).json()
        assert all(c["profile"]["name"] != "L&R Haulage" for c in result["items"])
        card = next(c for c in result["items"] if c["archive_id"] == swift["id"])
        assert (
            card["archive_owners"] == ["陈舟"]
            and card["profile"]["procurement"] == "委托采购"
        )
        assert not client.get("/api/alternatives/mine").json()
        assert len(other.get("/api/alternatives/mine").json()) == 2
        fb = root + f"/alternatives/{card['id']}/feedback"
        assert client.post(fb, json={"decision": "adopted"}).status_code == 403
        client.patch(root, json={"owner": "林悦"})
        assert not other.get("/api/alternatives/mine").json()
        assert len(client.get("/api/alternatives/mine").json()) == 2
        assert client.post(fb, json={"decision": "adopted"}).is_success
        assert (
            next(
                c for c in client.get("/api/companies").json() if c["id"] == swift["id"]
            )["notes"]
            == "原销售记录"
        )
        merged = client.post(root + "/merge", json={"target_id": b}).json()
        assert merged["alternatives"]["inquiry_id"] == b
        assert client.get("/api/alternatives/mine").json()[0]["inquiry_id"] == b
        client.patch(f"/api/inquiries/{b}", json={"company_id": None})
        assert not client.get("/api/alternatives/mine").json()
        assert (
            client.post(
                f"/api/inquiries/{b}/alternatives/{card['id']}/feedback",
                json={"decision": "adopted"},
            ).status_code
            == 409
        )


def test_alternative_live_privacy_quality_and_failure(client, monkeypatch):
    import httpx

    src = client.post(
        "/api/companies",
        json={
            "name": "Original Fleet",
            "country": "马来西亚",
            "kind": "车队",
            "website": "https://original.example",
            "notes": "PRIVATE-NOTES",
            "contact": "PRIVATE-CONTACT",
        },
    ).json()
    ident = event(client, body="PRIVATE-QUOTE").json()["inquiry_id"]
    root = f"/api/inquiries/{ident}"
    criteria = {"source_company_id": src["id"], "mode": "live"}
    client.patch(root, json={"company_id": src["id"], "owner": "林悦"})
    assert client.post(root + "/alternatives", json=criteria).status_code == 503
    monkeypatch.setenv("BRAVE_API_KEY", "dummy")

    def hit(name, domain, body):
        return dict(title=name, url="https://" + domain, description=body)

    good = "Our haulage fleet operates in Malaysia."
    hits = [
        hit("Other Fleet", "other.example", good),
        hit("Original Fleet Sdn Bhd", "news.example", good),
        hit("Own workshop", "original.example/self", good),
        hit("Unrelated", "othermarket.example", "Own fleet operates in Europe."),
        hit("Fleet directory", "empty.example", ""),
    ]
    queries = []

    def search(url, **kwargs):
        queries.append(kwargs["params"]["q"])
        return httpx.Response(
            200, request=httpx.Request("GET", url), json={"web": {"results": hits}}
        )

    monkeypatch.setattr(prospects.httpx, "get", search)
    response = client.post(root + "/alternatives", json=criteria)
    assert response.is_success, response.text
    cards = response.json()["items"]
    assert (
        len(cards) == 1
        and cards[0]["profile"]["name"] == "Other Fleet"
        and not cards[0]["proof"]
    )
    assert queries == ["Malaysia haulage fleet own workshop"]
    hits[:] = [
        hit(
            "Public tender",
            "public.example",
            "Original Fleet and Other Fleet were both listed as bidders.",
        ),
        hit("Something else", "other.example", "One bidder only."),
    ]
    evidence = client.post(root + f"/alternatives/{cards[0]['id']}/sources").json()
    assert (
        len(evidence["items"]) == 1
        and "Original Fleet" in queries[-1]
        and "Other Fleet" in queries[-1]
    )
    assert all("PRIVATE" not in q for q in queries)
    assert not client.get(root).json()["alternatives"]["items"][0]["proof"]
    monkeypatch.delenv("BRAVE_API_KEY")
    assert client.post(root + "/alternatives", json=criteria).status_code == 503
    assert (
        client.get(root).json()["alternatives"]["generated_at"]
        == response.json()["generated_at"]
    )


def test_alternative_context_change_during_search(client, monkeypatch):
    from src.api import alternatives

    src = client.post(
        "/api/companies", json={"name": "A", "country": "巴西", "kind": "车队"}
    ).json()
    ident = event(client).json()["inquiry_id"]
    root = f"/api/inquiries/{ident}"
    client.patch(root, json={"company_id": src["id"], "owner": "林悦"})
    empty = client.post(
        root + "/alternatives", json={"source_company_id": src["id"]}
    ).json()
    assert empty["items"] == []

    def late(_):
        client.patch(root, json={"owner": "陈舟"})
        return {"query": "Brazil", "items": []}

    monkeypatch.setattr(alternatives, "discover", late)
    assert (
        client.post(
            root + "/alternatives",
            json={"source_company_id": src["id"], "mode": "live"},
        ).status_code
        == 409
    )
    assert (
        client.get(root).json()["alternatives"]["generated_at"] == empty["generated_at"]
    )


def test_alternative_company_edits_and_market_aliases(client):
    source = {
        "name": "Source Parts",
        "kind": "配件门店",
        "country": "MY",
        "evidence": "销售重卡制动配件",
        "evidence_url": "https://source.example/about",
    }
    company = client.post("/api/companies", json=source).json()
    assert (
        client.post("/api/companies", json={**source, "country": "马来西亚"}).json()[
            "id"
        ]
        == company["id"]
    )
    ident = event(client).json()["inquiry_id"]
    root = f"/api/inquiries/{ident}"
    client.patch(root, json={"company_id": company["id"], "owner": "林悦"})
    criteria = {"source_company_id": company["id"]}
    result = client.post(root + "/alternatives", json=criteria).json()
    assert len(result["items"]) == 2
    assert all(c["source_url"] == source["evidence_url"] for c in result["items"])
    path = f"/api/companies/{company['id']}"
    assert client.put(path, json={**source, "owner": "unknown"}).status_code == 422
    assert client.put(path, json={**source, "owner": "陈舟"}).json()["owner"] == "陈舟"
    assert (
        client.get(root).json()["alternatives"]["generated_at"]
        == result["generated_at"]
    )
    client.put(path, json={**source, "country": "巴西"})
    assert client.get(root).json()["alternatives"] is None
    assert not client.get("/api/alternatives/mine").json()
    assert client.post(root + "/alternatives", json=criteria).json()["items"] == []
