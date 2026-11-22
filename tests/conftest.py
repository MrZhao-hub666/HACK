from .pg_workspace import test_workspace as pg_workspace
import pytest
from fastapi.testclient import TestClient

from src.backend.api.accounts import create_account, encode_password
from src.backend.api.db import database
from src.backend.api.main import app


@pytest.fixture(autouse=True)
def isolated_database():
    with pg_workspace():
        yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_DATA", "0")
    monkeypatch.setenv("ENABLE_SIMULATOR", "1")
    for key in (
        "ADMIN_BOOTSTRAP_PASSWORD_HASH",
        "EXA_API_KEY",
        "BRAVE_API_KEY",
        "LLM_API_KEY",
        "AUTO_ASSIGN",
    ):
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
