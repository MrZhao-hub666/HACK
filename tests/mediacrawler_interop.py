"""Run against the real upstream data router from an optional MediaCrawler checkout."""

import argparse
import io
import importlib.util
import json
import os
import socket
import tempfile
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import domestic
from src.api.accounts import create_account, encode_password
from src.api.db import database
from src.api.main import app


def command(*args):
    output = io.StringIO()
    with redirect_stdout(output):
        domestic.main(list(args))
    return json.loads(output.getvalue())


def run(checkout):
    path = Path(checkout) / "api/routers/data.py"
    spec = importlib.util.spec_from_file_location("mc_data_router", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    upstream = FastAPI()
    upstream.include_router(module.router, prefix="/api")
    with tempfile.TemporaryDirectory() as tmp, socket.socket() as sock:
        root = Path(tmp)
        module.DATA_DIR = root / "exports"
        posts = [{"aweme_id": str(i), "desc": "重卡刹车片维修手记"} for i in range(101)]
        comments = [
            {
                "aweme_id": "100",
                "comment_id": "01",
                "content": "需要 100 套，请报价。",
                "create_time": 1795136400,
            }
        ]
        notes = [{"note_id": "n1", "title": "求购刹车片", "time": 1795136400000}]
        for filename, records in [
            ("douyin/json/search_contents_test.json", posts),
            ("douyin/json/search_comments_test.json", comments),
            ("xhs/json/search_contents_test.json", notes),
        ]:
            out = module.DATA_DIR / filename
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(records, ensure_ascii=False), encoding="utf8")
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(upstream, log_level="error"))
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            assert server.started, "upstream router did not start"
            os.environ.update(
                DB_PATH=str(root / "leads.db"),
                DEMO_DATA="0",
                MEDIACRAWLER_URL=f"http://127.0.0.1:{port}",
                MEDIACRAWLER_OWN_POSTS="dy:100",
            )
            with TestClient(app, headers={"X-Workspace-Request": "1"}) as c:
                with database(True) as db:
                    create_account(
                        db,
                        "mc.test",
                        "渠道测试",
                        "sales",
                        encode_password("Upstream-test-only-123"),
                        False,
                    )
                c.post(
                    "/api/auth/login",
                    json={"username": "mc.test", "password": "Upstream-test-only-123"},
                ).raise_for_status()
                listed = command("list")
                assert len(listed) == 3
                for target, expected in [("inserted", 103), ("unchanged", 103)]:
                    counts = [command("sync", file["path"])[target] for file in listed]
                    assert sum(counts) == expected, counts
                hits = c.get("/api/domestic/signals", params={"signal": "求购"}).json()
                assert hits["total"] == 2
                hit = next(row for row in hits["items"] if row["owned"])
                promoted = c.post(f"/api/domestic/signals/{hit['id']}/inquiry")
                promoted.raise_for_status()
                assert (
                    c.get("/api/inquiries").json()[0]["id"]
                    == promoted.json()["inquiry_id"]
                )
        finally:
            server.should_exit = True
            thread.join(6)
    print(
        "Upstream HTTP passed: 3 files, 103 records, 103 duplicates, 2 buying signals, 1 owned comment in the inbox."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "checkout", help="MediaCrawler source checkout with api/routers/data.py"
    )
    run(parser.parse_args().checkout)
