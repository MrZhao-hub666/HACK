from uuid import uuid4

import httpx

from src.api import selection
from .test_workbench import event


def test_handoff_preserves_speakers_and_skips_notes(client, monkeypatch):
    ident = event(client, body="FMSI 4702a").json()["inquiry_id"]
    base = f"/api/inquiries/{ident}"
    assert client.post(base + "/notes", json={"text": "内部判断：WVA 29174"}).is_success
    assert client.post(base + "/reply", json={"text": "是否出口？"}).is_success
    captured = []
    def match(method, path, payload):
        captured.extend(payload["turns"])
        return httpx.Response(200, json={"count": 1})
    monkeypatch.setattr(selection, "catalogue", match)
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
    calls = []
    def capture(method, path, payload):
        calls.append(payload)
        return httpx.Response(200, json={})
    monkeypatch.setattr(selection, "catalogue", capture)
    draft = {"spec_id":"FAG0001", "quantity":5, "unit":"套", "request_key":str(uuid4())}
    assert client.post(f"/api/inquiries/{source}/selection/quotes", json=draft).is_success
    assert client.post(f"/api/inquiries/{source}/merge", json={"target_id":target}).is_success
    assert client.get(f"/api/inquiries/{target}/selection/quotes").is_success
    assert calls[0]["workspace"] == calls[1]["workspace"]
    assert calls[0]["inquiry_id"] == source
    assert set(calls[1]["inquiries"]) == {source, target}
