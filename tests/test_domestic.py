import json

from src.api import domestic


def upload(client, platform, rows):
    return client.post(
        "/api/domestic/import",
        json={"platform": platform, "document": json.dumps(rows)},
    )


def rows(client, **params):
    response = client.get("/api/domestic/signals", params=params)
    assert response.status_code == 200
    return response.json()


def test_comments_before_post_and_idempotence(client, monkeypatch):
    parent = 7189000000000000123
    comment = {
        "aweme_id": parent,
        "comment_id": "c1",
        "content": "我们车队需要 80 套，请报价。",
        "create_time": 1795136400,
        "nickname": "不保存昵称",
    }
    assert upload(client, "dy", [comment]).json()["inserted"] == 1
    assert rows(client, signal="求购")["total"] == 0
    post = {
        "aweme_id": str(parent),
        "desc": "重卡刹车片维修记录",
        "source_keyword": "卡车维保",
    }
    assert upload(client, "dy", [post, comment]).json()["unchanged"] == 1
    edited = {**comment, "content": "我们车队需要 100 套，请报价。"}
    assert upload(client, "dy", [edited, {}]).json() == {
        "inserted": 0,
        "updated": 1,
        "unchanged": 0,
        "skipped": 1,
    }
    found = rows(client, signal="求购", platform="dy", q="刹车片")
    hit = found["items"][0]
    assert found["total"] == 1 and hit["quantities"] == ["100 套"]
    assert str(parent) in hit["source_url"] and "不保存昵称" not in str(hit)
    endpoint = f"/api/domestic/signals/{hit['id']}/inquiry"
    assert client.post(endpoint).status_code == 422
    assert client.get("/api/inquiries").json() == []
    monkeypatch.setenv("MEDIACRAWLER_OWN_POSTS", f"dy:{parent}")
    promoted = client.post(endpoint).json()
    assert promoted["duplicate"] is False
    assert client.post(endpoint).json() == {**promoted, "duplicate": True}
    assert (
        rows(client, signal="求购")["items"][0]["inquiry_id"] == promoted["inquiry_id"]
    )
    message = client.get(f"/api/inquiries/{promoted['inquiry_id']}").json()["messages"][
        0
    ]
    assert message["body"] == edited["content"] and message["channel"] == "dy"
    assert message["at"].startswith("2026-") and str(parent) in message["attachment"]


def test_search_adopt_and_sample_isolation(client, monkeypatch):
    input_rows = [
        {
            "note_id": "item",
            "title": "求购重卡制动片",
            "desc": "请报价 120 套",
            "time": 1795136400000,
        },
        {"note_id": "seller", "desc": "刹车片厂家直销，欢迎询价"},
        {"note_id": "other", "desc": "需要 5 套床单，请报价"},
    ]
    upload(client, "xhs", input_rows)
    hit = rows(client, platform="xhs", signal="求购")["items"][0]
    assert hit["kind"] == "post" and hit["published"].startswith("2026-")
    assert hit["source_url"] == "https://www.xiaohongshu.com/explore/item"
    assert rows(client, platform="dy")["items"] == []
    assert rows(client, signal="供应推广")["total"] == 1
    assert (
        rows(client, offset=1, limit=1)["items"][0]["id"]
        != rows(client, limit=1)["items"][0]["id"]
    )
    endpoint = f"/api/domestic/signals/{hit['id']}/adopt"
    first = client.post(
        endpoint, json={"name": "已核实企业", "country": "马来西亚"}
    ).json()
    assert client.post(endpoint, json={"name": "已核实企业"}).json() == first
    company = client.get("/api/companies").json()[0]
    assert company["procurement"] == "待核实" and company["country"] == "马来西亚"
    assert (
        company["evidence_url"] == hit["source_url"] and "小红书" in company["source"]
    )
    assert client.post("/api/domestic/examples").json()["inserted"] == 4
    assert client.post("/api/domestic/examples").json()["unchanged"] == 4
    sample = next(r for r in rows(client, signal="求购")["items"] if r["demo"])
    assert sample["source_url"] == ""
    assert (
        client.post(
            f"/api/domestic/signals/{sample['id']}/adopt", json={"name": "测试"}
        ).status_code
        == 422
    )
    monkeypatch.setenv("ENABLE_SIMULATOR", "0")
    assert client.post("/api/domestic/examples").status_code == 403


def test_webui_contract_and_errors(client, monkeypatch):
    monkeypatch.delenv("MEDIACRAWLER_URL", raising=False)
    assert client.get("/api/domestic/files").status_code == 503
    assert (
        client.post(
            "/api/domestic/sync", json={"path": "../../secrets.json"}
        ).status_code
        == 422
    )
    exports = [{"aweme_id": "123", "title": "需采购卡车刹车片"}]
    files = [
        {"path": r"douyin\json\search_contents_a.json", "record_count": 1},
        {"path": "xhs/json/search_comments_a.json", "record_count": 8},
        {"path": "xhs/json/creators.json"},
        {"path": "ks/json/search_contents_a.json"},
    ]

    def upstream(endpoint, params=None):
        if endpoint == "files":
            assert params == {"file_type": "json"}
            return {"files": files}
        assert endpoint == "files/douyin/json/search_contents_a.json" and params == {
            "preview": "false"
        }
        return exports

    monkeypatch.setattr(domestic, "read_upstream", upstream)
    listed = client.get("/api/domestic/files").json()
    assert len(listed) == 2
    assert (
        client.post("/api/domestic/sync", json={"path": listed[0]["path"]}).json()[
            "inserted"
        ]
        == 1
    )
    assert (
        client.post("/api/domestic/sync", json={"path": listed[0]["path"]}).json()[
            "unchanged"
        ]
        == 1
    )
    assert (
        client.post(
            "/api/domestic/import", json={"platform": "dy", "document": "bad"}
        ).status_code
        == 422
    )
    assert upload(client, "xhs", {}).status_code == 422
    client.cookies.clear()
    assert client.get("/api/domestic/signals").status_code == 401
