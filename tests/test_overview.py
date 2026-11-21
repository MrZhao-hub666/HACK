from src.api.db import database, initialize


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
