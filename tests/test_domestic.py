import json

import pytest
from fastapi import HTTPException

from src.api import domestic


def upload(platform, rows):
    return domestic.import_export(platform, json.dumps(rows).encode("utf8"))


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
    assert upload("dy", [comment])["inserted"] == 1
    assert rows(client, signal="求购")["total"] == 0
    post = {
        "aweme_id": str(parent),
        "desc": "重卡刹车片维修记录",
        "source_keyword": "卡车维保",
    }
    assert upload("dy", [post, comment])["unchanged"] == 1
    edited = {**comment, "content": "我们车队需要 100 套，请报价。"}
    assert upload("dy", [edited, {}]) == {
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
    upload("xhs", input_rows)
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
    assert domestic.examples()["inserted"] == 4
    assert domestic.examples()["unchanged"] == 4
    sample = next(r for r in rows(client, signal="求购")["items"] if r["demo"])
    assert sample["source_url"] == ""
    assert (
        client.post(
            f"/api/domestic/signals/{sample['id']}/adopt", json={"name": "测试"}
        ).status_code
        == 422
    )
    monkeypatch.setenv("ENABLE_SIMULATOR", "0")
    with pytest.raises(HTTPException) as denied:
        domestic.examples()
    assert denied.value.status_code == 403


def test_webui_contract_and_errors(client, monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("MEDIACRAWLER_URL", raising=False)
    assert rows(client)["index_state"] == "unconfigured"
    with monkeypatch.context() as configured:
        configured.setenv("MEDIACRAWLER_URL", "http://127.0.0.1:8091")
        assert rows(client)["index_state"] == "awaiting_sync"
    with pytest.raises(SystemExit) as unavailable:
        domestic.main(["list"])
    assert unavailable.value.code == 1
    assert "尚未配置 MediaCrawler" in capsys.readouterr().err
    with pytest.raises(HTTPException) as invalid_path:
        domestic.sync("../../secrets.json")
    assert invalid_path.value.status_code == 422
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
    domestic.main(["list"])
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 2
    domestic.main(["sync", listed[0]["path"]])
    assert json.loads(capsys.readouterr().out)["inserted"] == 1
    domestic.main(["sync", listed[0]["path"]])
    assert json.loads(capsys.readouterr().out)["unchanged"] == 1

    export = tmp_path / "export.json"
    export.write_bytes(b"bad")
    with pytest.raises(SystemExit) as invalid_export:
        domestic.main(["import", "dy", str(export)])
    assert invalid_export.value.code == 1
    assert "UTF-8 JSON" in capsys.readouterr().err
    export.write_text(
        json.dumps([{"note_id": "n1", "title": "求购刹车片"}]), encoding="utf-8-sig"
    )
    domestic.main(["import", "xhs", str(export)])
    assert json.loads(capsys.readouterr().out)["inserted"] == 1
    assert rows(client, platform="xhs", signal="求购")["total"] == 1
    no_match = rows(client, q="ZZZ-无匹配-987654")
    assert no_match["total"] == 0 and no_match["index_state"] == "indexed"

    with pytest.raises(HTTPException) as invalid_rows:
        upload("xhs", {})
    assert invalid_rows.value.status_code == 422
    for endpoint in ("files", "sync", "import", "examples"):
        assert f"/api/domestic/{endpoint}" not in client.get("/openapi.json").json()["paths"]
    client.cookies.clear()
    assert client.get("/api/domestic/signals").status_code == 401
