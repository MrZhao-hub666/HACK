from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi import HTTPException

from src.backend.api import prospects
from src.backend.api.db import database, initialize


def test_archive_time_and_explicit_deal_confirmation(client):
    profile = {"name": "New fleet", "country": "马来西亚"}
    buyer = client.post(
        "/api/companies", json={**profile, "checked": "2020-01-20"}
    ).json()
    assert buyer["archived_at"] and not buyer["archived_at"].startswith("2020-01-20")
    ident = buyer["id"]
    path = f"/api/companies/{ident}"
    marked = client.put(path, json={**profile, "confirmed_deal": True}).json()
    assert marked["won_at"] and marked["won_by"] == "林悦"
    assert (
        client.post("/api/companies", json=profile).json()["archived_at"]
        == buyer["archived_at"]
    )
    for values in (profile, {**profile, "confirmed_deal": True}):
        assert client.put(path, json=values).json()["won_at"] == marked["won_at"]
    cleared = client.put(path, json={**profile, "confirmed_deal": False}).json()
    assert cleared["won_at"] is None and cleared["won_by"] is None


def test_old_archive_stays_undated_on_upgrade_and_replay(client):
    profile = {"name": "Old fleet", "country": "泰国"}
    buyer = client.post("/api/companies", json=profile).json()
    with database(True) as db:
        for column in ("archived_at", "won_at", "won_by"):
            db.execute(f"ALTER TABLE companies DROP COLUMN {column}")
    initialize()
    initialize()
    old = client.post("/api/companies", json=profile).json()
    assert (
        old["id"] == buyer["id"]
        and old["archived_at"] is None
        and old["won_at"] is None
    )
    with database(True) as db:
        db.execute("UPDATE companies SET saved=0 WHERE id=%s", (old["id"],))
    assert client.post("/api/companies", json=profile).json()["archived_at"]


def test_outreach_summary_counts_records_companies_and_drafts_separately(client):
    summary = "/api/outreach/summary"
    assert client.get(summary).json() == {
        "fair_records": 0,
        "pending": 0,
        "linked_buyers": 0,
        "drafts": 0,
    }
    for i, source in enumerate(("广交会", "上海法兰克福", "社媒原帖")):
        evidence = client.post(
            "/api/outreach/evidence",
            json={
                "source": source,
                "edition": "2025",
                "title": "Buyer",
                "url": f"https://example.com/p/{i}",
            },
        ).json()
        if i < 2:
            result = client.put(
                f"/api/outreach/evidence/{evidence['id']}",
                json={
                    "version": evidence["updated"],
                    "name": "Buyer",
                    "market": "瑞士",
                    "verdict": "已核实",
                    "quote": "Buyer",
                    "fit": "C",
                    "reason": "买家代表",
                },
            ).json()
            company_id = result["company_id"]
    for _ in range(2):
        client.post(
            f"/api/outreach/buyers/{company_id}/draft",
            json={
                "event": "Fair",
                "starts": "2026-11-21",
                "ends": "2026-11-22",
                "booth": "B12",
            },
        ).raise_for_status()
    assert client.get(summary).json() == {
        "fair_records": 2,
        "pending": 1,
        "linked_buyers": 1,
        "drafts": 1,
    }


def test_contact_profile_defaults_and_survives_older_client_updates(client):
    company = {"name": "Profile fleet", "country": "泰国"}
    buyer = client.post("/api/companies", json=company).json()
    with database(True) as db:
        for column in ("contact_gender", "contact_age_band"):
            db.execute(f"ALTER TABLE companies DROP COLUMN {column}")
    initialize()
    initialize()

    path = f"/api/companies/{buyer['id']}"
    record = client.put(path, json=company).json()
    assert record["contact_gender"] == record["contact_age_band"] == ""
    profile = {"contact_gender": "女", "contact_age_band": "35-44"}
    client.put(path, json={**company, **profile}).raise_for_status()
    client.post("/api/companies", json=company).raise_for_status()
    record = client.put(path, json={**company, "notes": "历史客户端"}).json()
    assert {key: record[key] for key in profile} == profile
    assert client.put(path, json={**company, "contact_age_band": "middle"}).status_code == 422
    record = client.put(path, json={**company, "contact_age_band": ""}).json()
    assert record["contact_gender"] == "女" and record["contact_age_band"] == ""


def test_recommendation_refresh_keeps_last_candidates_after_filtered_empty(client, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-exa")
    refresh = "/api/discovery/recommendations/refresh"
    hits = [{
        "title": "Truck parts company",
        "url": "https://parts.example",
        "description": "Workshops are our customers. We sell commercial vehicle brake parts.",
    }, {
        "title": "Truck Axle Manufacturer",
        "url": "https://axle.example",
        "description": "We are a truck axle manufacturer and offer a range of aftermarket parts.",
    }]
    monkeypatch.setattr(prospects, "public_search", lambda query: hits)
    previous = client.post(refresh).json()
    assert {item["title"]: item["direction"] for item in previous["items"]} == {
        "Truck parts company": "经销进口",
        "Truck Axle Manufacturer": "主机与车桥配套",
    }
    client.post("/api/companies", json={
        "name": "Archived Parts Seller",
        "country": "马来西亚",
        "website": "https://archived.example",
    }).raise_for_status()
    for candidate in (
        {
            "title": "Passenger car repairs",
            "url": "https://car.example",
            "description": "Passenger car repair workshops.",
        },
        {
            "title": "Archived Parts Seller catalog",
            "url": "https://archived.example/catalog",
            "description": "We sell commercial vehicle spare parts.",
        },
    ):
        hits[:] = [candidate]
        filtered = client.post(refresh).json()
        assert filtered["items"] == previous["items"]
        assert filtered["updated"] == previous["updated"]
        assert not filtered["error"] and "没有筛选出符合条件" in filtered["notice"]


def test_concurrent_recommendation_refresh_reports_in_progress(client, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-exa")
    feed = "/api/discovery/recommendations"
    refresh = f"{feed}/refresh"
    monkeypatch.setattr(prospects, "public_search", lambda query: [])
    previous = client.post(refresh).json()
    assert previous["updated"] and not previous["error"]

    started = Event()
    finish = Event()

    def failing_search(query):
        started.set()
        assert finish.wait(10)
        raise HTTPException(502, "上游检索失败")

    monkeypatch.setattr(prospects, "public_search", failing_search)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, refresh)
        try:
            assert started.wait(10)
            concurrent = client.post(refresh)
            assert concurrent.status_code == 409
            assert "正在更新" in concurrent.json()["detail"]
            automatic = client.post(refresh, params={"automatic": True})
            assert automatic.json() == previous
        finally:
            finish.set()
        result = first.result(timeout=10).json()

    assert result["error"] == "上游检索失败"
    assert result["updated"] == previous["updated"]
    assert client.get(feed).json() == result
