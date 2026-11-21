from uuid import uuid4

from psycopg.types.json import Jsonb

from src.api import selection
from .test_workbench import event


def test_handoff_preserves_speakers_and_skips_notes(client, monkeypatch):
    ident = event(client, body="FMSI 4702a").json()["inquiry_id"]
    base = f"/api/inquiries/{ident}"
    assert client.post(base + "/notes", json={"text": "内部判断：WVA 29174"}).is_success
    assert client.post(base + "/reply", json={"text": "是否出口？"}).is_success
    captured = []
    def match(req):
        captured.extend(t.model_dump() for t in req.turns)
        return {"count": 1}
    monkeypatch.setattr(selection.catalogue, "analyze", match)
    assert client.post(base + "/selection", json={"customer_words": "出口"}).json() == {"count": 1}
    assert captured == [
        {"role": "customer", "text": "FMSI 4702a"},
        {"role": "sales", "text": "是否出口？"},
        {"role": "customer", "text": "出口"},
    ]
    assert client.post("/api/inquiries/99999/selection", json={}).status_code == 404
    client.cookies.clear()
    assert client.post(base + "/selection", json={}).status_code == 401


def test_quote_workspace_and_merged_inquiries(client, monkeypatch):
    source = event(client).json()["inquiry_id"]
    target = event(client, "e2", thread_key="other", sender="Other").json()["inquiry_id"]
    def store(db, req):
        row = db.execute("INSERT INTO quote_draft(snapshot,request_key) VALUES(%s,%s) RETURNING id",
                         (Jsonb({"spec_id": req.spec_id}), req.request_key)).fetchone()
        return dict(id=row["id"], spec_id=req.spec_id)
    monkeypatch.setattr(selection.catalogue, "save_quote", store)
    draft = {"spec_id":"FAG0001", "quantity":5, "unit":"套", "request_key":str(uuid4())}
    assert client.post(f"/api/inquiries/{source}/selection/quotes", json=draft).is_success
    assert client.post(f"/api/inquiries/{source}/merge", json={"target_id":target}).is_success
    result = client.get(f"/api/inquiries/{target}/selection/quotes")
    assert result.is_success
    assert result.json() == [{"id":1,"spec_id":"FAG0001"}]
