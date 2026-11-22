import pytest
from fastapi.testclient import TestClient

from src.backend.api.accounts import create_account, encode_password
from src.backend.api.auth import COOKIE
from src.backend.api.db import database
from src.backend.api.main import app

HEADERS = {"X-Workspace-Request": "1"}
INITIAL = "Initial-password-for-test"
PERSONAL = "Personal-password-for-test"


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setenv("DEMO_DATA", "0")
    with TestClient(app, headers=HEADERS) as client:
        with database(True) as db:
            create_account(
                db, "admin", "林悦", "admin", encode_password(INITIAL), False
            )
        yield client


def login(client, name="admin", password=INITIAL, remember=False):
    return client.post(
        "/api/auth/login",
        json={"username": name, "password": password, "remember": remember},
    )


def test_session_and_actor(browser):
    assert browser.get("/api/health").status_code == 200
    for path in ["config", "companies", "inquiries", "auth/members", "auth/me"]:
        assert browser.get("/api/" + path).status_code == 401
    assert login(browser, password="wrong").status_code == 401
    response = login(browser, remember=True)
    assert response.json()["user"]["username"] == "admin"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=" in cookie
    assert browser.get("/api/config").headers["cache-control"] == "no-store"
    no_marker = browser.post("/api/auth/logout", headers={"X-Workspace-Request": ""})
    assert no_marker.status_code == 403
    assert browser.get("/api/auth/me").is_success
    before = browser.cookies.get(COOKIE)
    msg = browser.post(
        "/api/inquiries/manual",
        json={
            "event_id": "a",
            "channel": "manual",
            "thread_key": "a",
            "sender": "Customer",
            "body": "price?",
        },
    )
    ident = msg.json()["inquiry_id"]
    record = browser.post(
        f"/api/inquiries/{ident}/notes", json={"text": "Reviewed", "actor": "另一个人"}
    )
    assert record.json()["history"][0]["actor"] == "林悦"
    assert browser.post("/api/auth/logout").status_code == 204
    with TestClient(app, cookies={COOKIE: before}) as other:
        assert other.get("/api/auth/me").status_code == 401


def test_members_and_password_lifecycle(browser):
    assert login(browser).is_success
    member = {
        "username": "chen.zhou",
        "display_name": "陈舟",
        "role": "sales",
        "password": INITIAL,
    }
    row = browser.post("/api/auth/members", json=member).json()
    ident = row["id"]
    assert row["must_change"] and "password_hash" not in row
    assert browser.post("/api/auth/members", json=member).status_code == 409
    assert (
        browser.patch("/api/auth/members/1", json={"active": False}).status_code == 409
    )
    with (
        TestClient(app, headers=HEADERS) as seller,
        TestClient(app, headers=HEADERS) as prior,
    ):
        assert login(seller, member["username"]).is_success
        assert login(prior, member["username"]).is_success
        assert seller.get("/api/config").status_code == 403
        assert (
            seller.post(
                "/api/auth/password",
                json={"current_password": "invalid", "password": PERSONAL},
            ).status_code
            == 400
        )
        assert seller.post(
            "/api/auth/password",
            json={"current_password": INITIAL, "password": PERSONAL},
        ).is_success
        assert prior.get("/api/auth/me").status_code == 401
        assert seller.get("/api/config").is_success
        assert seller.get("/api/auth/members").status_code == 403
        assert seller.post("/api/auth/members", json=member).status_code == 403
        assert (
            browser.post(
                f"/api/auth/members/{ident}/password",
                json={"password": "Temporary-recovery-value"},
            ).status_code
            == 204
        )
        assert seller.get("/api/auth/me").status_code == 401
        assert login(seller, member["username"], PERSONAL).status_code == 401
        assert login(seller, member["username"], "Temporary-recovery-value").json()[
            "user"
        ]["must_change"]
        assert browser.patch(
            f"/api/auth/members/{ident}", json={"active": False}
        ).is_success
        assert seller.get("/api/auth/me").status_code == 401
        assert "陈舟" not in browser.get("/api/config").json()["team"]
        assert (
            login(seller, member["username"], "Temporary-recovery-value").status_code
            == 401
        )
        assert browser.patch(
            f"/api/auth/members/{ident}", json={"active": True}
        ).is_success
        assert login(seller, member["username"], "Temporary-recovery-value").is_success


def test_expiry_and_attempt_limit(browser):
    assert login(browser).is_success
    with database(True) as db:
        db.execute("UPDATE sessions SET expires_at=0")
    assert browser.get("/api/inquiries").status_code == 401
    for _ in range(10):
        assert login(browser, password="invalid").status_code == 401
    assert login(browser).status_code == 429
