from io import BytesIO

import httpx
from openpyxl import load_workbook

from src.backend.api import outreach
from src.backend.api.db import database, initialize


BASE = "/api/outreach"
FAIR = {
    "source": "广交会",
    "edition": "第138届",
    "market": "巴西",
    "title": "=BUYER()",
    "url": "https://example.com/buyers",
    "snippet": "供采对接",
}
REVIEW = {
    "verdict": "已核实",
    "name": "=BUYER()",
    "market": "巴西",
    "kind": "批发进口商",
    "quote": "We source brake linings for trucks.",
    "fit": "A",
    "reason": "原文明确采购商用车衬片",
}


def capture(client, **changes):
    response = client.post(BASE + "/evidence", json={**FAIR, **changes})
    assert response.status_code == 200, response.text
    return response.json()


def test_fair_search_import_retry_and_regrade(client):
    for fair in ("广交会", "上海法兰克福"):
        assert client.post(BASE + "/search", json={"source": fair}).json()["items"]
        assert (
            client.post(
                BASE + "/search", json={"source": fair, "keywords": "no-such-buyer"}
            ).json()["items"]
            == []
        )
        assert (
            client.post(
                BASE + "/search", json={"source": fair, "mode": "live"}
            ).status_code
            == 503
        )

    batch = {
        "source": "广交会",
        "edition": "第138届",
        "csv_text": "企业名称,来源链接,市场\n联营,https://example.com,中国\n另一家公司,javascript:invalid,中国",
    }
    assert client.post(BASE + "/import", json=batch).status_code == 422
    assert client.get(BASE).json()["evidence"] == []
    batch["csv_text"] = batch["csv_text"].replace(
        "javascript:invalid", "https://example.com"
    )
    assert client.post(BASE + "/import", json=batch).json() == {
        "added": 2,
        "duplicates": 0,
    }
    assert client.post(BASE + "/import", json=batch).json() == {
        "added": 0,
        "duplicates": 2,
    }
    other = client.post(BASE + "/import", json={**batch, "edition": "第139届"})
    assert other.json()["added"] == 2
    assert (
        len(
            client.post(
                BASE + "/search",
                json={"source": "广交会", "edition": "139", "keywords": "联营"},
            ).json()["items"]
        )
        == 1
    )

    item = capture(client)
    path = BASE + "/evidence/" + str(item["id"])
    reviewed = client.put(path, json={**REVIEW, "version": item["updated"]}).json()
    assert reviewed["reviewer"] == "林悦"
    assert (
        client.put(path, json={**REVIEW, "version": item["updated"]}).status_code == 409
    )
    buyer_id = reviewed["company_id"]
    with database(True) as db:
        db.execute("UPDATE companies SET procurement='仅转售' WHERE id=%s", (buyer_id,))
    assert capture(client)["fit"] == "A"
    extra = capture(client, edition="第139届")
    client.put(
        BASE + "/evidence/" + str(extra["id"]),
        json={
            **REVIEW,
            "fit": "B",
            "company_id": buyer_id,
            "version": extra["updated"],
        },
    ).raise_for_status()
    client.put(
        path, json={**REVIEW, "verdict": "排除", "version": reviewed["updated"]}
    ).raise_for_status()
    initialize()
    buyers = client.get(BASE).json()["buyers"]
    assert [(b["grade"], b["procurement"]) for b in buyers] == [("B", "仅转售")]


def test_posts_by_permalink_raw_content_and_failure(client, monkeypatch):
    hits = [
        {
            "url": "https://x.com/axle/status/" + i,
            "title": i,
            "description": "Seeking parts",
        }
        for i in ("123", "456")
    ]
    hits.append(
        {"url": "https://x.com/seller", "title": "Profile", "description": "Sell parts"}
    )

    def search(query, *, domains):
        assert query == "brake"
        assert "x.com" in domains and "linkedin.com/posts" in domains
        return hits

    monkeypatch.setattr(outreach.prospects, "public_search", search)
    results = client.post(
        BASE + "/search",
        json={"source": "社媒原帖", "mode": "live", "keywords": "brake"},
    ).json()["items"]
    assert len(results) == 2
    item = client.post(BASE + "/evidence", json=results[0]).json()
    replay = capture(
        client,
        source="社媒原帖",
        title="Updated title",
        url=results[0]["url"] + "?utm_source=x",
    )
    assert replay["id"] == item["id"]
    req = {
        **REVIEW,
        "name": "",
        "market": "",
        "author": "@axle",
        "version": item["updated"],
        "intent": "寻找货源",
    }
    assert (
        client.put(BASE + "/evidence/" + str(item["id"]), json=req).json()["company_id"]
        is None
    )
    assert not client.get("/api/inquiries").json()
    assert (
        client.post(
            BASE + "/assess", json={"text": "We sell brake pads at a good price"}
        ).json()["intent"]
        == "卖方推广"
    )

    def response(*args, **kwargs):
        payload = {
            "posts": [
                {
                    "uri": "at://did:plc:abc/app.bsky.feed.post/abcd",
                    "record": {
                        "text": "Need brake shoes",
                        "createdAt": "2026-11-20T10:00:00Z",
                    },
                    "author": {"handle": "fleet.test"},
                }
            ]
        }
        return httpx.Response(
            200, json=payload, request=httpx.Request("GET", "https://api.bsky.app")
        )

    monkeypatch.setattr(outreach.httpx, "get", response)
    native = client.post(
        BASE + "/search", json={"source": "社媒原帖", "mode": "bluesky"}
    ).json()["items"][0]
    assert native["quote"] == "Need brake shoes" and native["published"] == "2026-11-20"
    assert client.post(BASE + "/evidence", json=native).json()["author"] == "fleet.test"

    def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(outreach.httpx, "get", offline)
    assert (
        client.post(
            BASE + "/search", json={"source": "社媒原帖", "mode": "bluesky"}
        ).status_code
        == 502
    )


def test_contacts_drafts_and_excel_share_correct_company(client):
    item = capture(client)
    entity = client.put(
        BASE + "/evidence/" + str(item["id"]),
        json={**REVIEW, "version": item["updated"]},
    ).json()
    cid = entity["company_id"]
    path = f"{BASE}/buyers/{cid}"
    c = {
        "kind": "采购邮箱",
        "holder": "采购团队",
        "value": "buy@example.com",
        "url": "https://example.com/contact",
    }
    for _ in range(2):
        client.post(path + "/contacts", json=c).raise_for_status()
    contacts = client.get(BASE).json()["contacts"]
    assert len(contacts) == 1
    invitation = {
        "event": "Canton Fair",
        "starts": "2027-04-15",
        "ends": "2027-04-19",
        "booth": "Hall 9 A01",
        "contact_id": contacts[0]["id"],
    }
    draft = client.post(path + "/draft", json=invitation).json()
    assert draft["recipient"] == "buy@example.com" and "Hall 9 A01" in draft["body"]
    edit = {
        "version": draft["updated"],
        "subject": "Meeting request",
        "body": "My edited draft",
        "contact_id": contacts[0]["id"],
    }
    client.put(BASE + "/drafts/" + str(draft["id"]), json=edit).raise_for_status()
    assert (
        client.post(path + "/draft", json=invitation).json()["body"]
        == "My edited draft"
    )
    assert (
        client.put(BASE + "/drafts/" + str(draft["id"]), json=edit).status_code == 409
    )
    assert (
        client.post(
            path + "/draft", json={**invitation, "ends": "2020-01-01"}
        ).status_code
        == 422
    )
    other = client.post(
        "/api/companies", json={"name": "Other", "country": "巴西"}
    ).json()
    assert (
        client.post(f"{BASE}/buyers/{other['id']}/draft", json=invitation).status_code
        == 404
    )

    def book(**params):
        response = client.get(BASE + "/export.xlsx", params=params)
        response.raise_for_status()
        return load_workbook(BytesIO(response.content))

    wb = book(grade="A", q="BUYER")
    assert wb.sheetnames == ["买家分级", "核实依据", "采购联系渠道"]
    assert (
        wb.worksheets[0]["B2"].value == "=BUYER()"
        and wb.worksheets[0]["B2"].data_type == "s"
    )
    assert (
        wb.worksheets[1]["K2"].value == REVIEW["quote"]
        and wb.worksheets[2]["D2"].value == c["value"]
    )
    assert all(s.max_row == 1 for s in book(grade="A", q="Other"))
    assert not client.get("/api/inquiries").json()


def test_existing_volume_adds_tables_without_changing_old_company(client):
    old = client.post(
        "/api/companies",
        json={"name": "原有企业", "country": "马来西亚", "procurement": "委托采购"},
    ).json()
    with database(True) as db:
        for table in ("outreach_drafts", "outreach_contacts", "outreach_evidence"):
            db.execute("DROP TABLE " + table)
    initialize()
    initialize()
    result = client.get(BASE).json()
    assert len(result["buyers"]) == 1
    assert result["buyers"][0]["id"] == old["id"] and result["buyers"][0]["grade"] == ""
    assert result["buyers"][0]["procurement"] == "委托采购"
    assert not result["drafts"] and not result["contacts"] and not result["evidence"]


def test_fit_suggestion_keeps_buyers_and_sellers_separate(client):
    text = "We are looking for a supplier of truck brake linings."
    assert client.post(BASE + "/assess", json={"text": text}).json()["fit"] == "A"
    text = "We sell truck brake pads at a great price."
    result = client.post(BASE + "/assess", json={"text": text}).json()
    assert (result["intent"], result["fit"]) == ("卖方推广", "B")
    assert (
        client.post(BASE + "/assess", json={"text": "上海展买家名单"}).json()["fit"]
        == "C"
    )
