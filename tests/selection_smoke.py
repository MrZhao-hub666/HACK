"""Exercise the built workspace against an isolated inbox and the running selector."""
from tests.pg_workspace import test_workspace
import os
import socket
import threading
import time
from uuid import uuid4

import uvicorn
from playwright.sync_api import expect, sync_playwright
from src.api.accounts import create_account, encode_password
from src.api.db import database
from src.api.main import app


def check_selection(context, url):
    page = context.new_page()
    try:
        page.goto(url + "/#inbox")
        page.set_viewport_size({"width":1440, "height":900})
        page.locator(".ticket").filter(has_text="李师傅").click()
        page.get_by_role("button", name="智能选型", exact=True).click()
        page.get_by_role("button", name="根据询盘匹配型号").click()
        expect(page.get_by_text("建议询问客户")).to_be_visible()
        # Use a clean thread for a precise lookup, with no unrelated axle clues.
        response = context.request.post(url + "/api/demo/inquiries", headers={"X-Workspace-Request":"1"},
            data={"channel":"manual","sender":"选型联调","thread_key":"select-demo","event_id":"select-1","body":"FMSI 4702a"})
        assert response.ok, response.text()
        page.reload()
        page.locator(".ticket").filter(has_text="选型联调").click()
        page.get_by_role("button", name="智能选型", exact=True).click()
        page.get_by_role("button", name="根据询盘匹配型号").click()
        panel = page.get_by_role("region", name="询盘选型")
        expect(panel.locator("article h3")).to_contain_text("FAG", timeout=15000)
        panel.get_by_label("采购数量").fill("3")
        panel.get_by_label("计价单位").fill("套")
        panel.get_by_role("button", name="生成报价草稿").click()
        expect(panel.get_by_role("status")).to_contain_text("#")
        panel.get_by_role("button", name="查看本询盘最近报价草稿").click()
        expect(panel.locator("li")).to_contain_text("FAG0002")
        endpoint = url + f"/api/inquiries/{response.json()['inquiry_id']}/selection/quotes"
        payload = {"spec_id":"FAG0002","unit":"套","quantity":2,"request_key":str(uuid4())}
        headers = {"X-Workspace-Request":"1"}
        first = context.request.post(endpoint, headers=headers, data=payload)
        retry = context.request.post(endpoint, headers=headers, data=payload)
        assert first.ok and retry.ok and first.json()["id"] == retry.json()["id"]
        assert len(context.request.get(endpoint).json()) == 2
        image = panel.locator("img").first
        expect(image).to_be_visible()
        assert context.request.get(url + image.get_attribute("src")).ok
        page.set_viewport_size({"width":390, "height":844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        page.close()


def main():
    with test_workspace(), socket.socket() as sock:
        os.environ.update(DEMO_DATA="1", ENABLE_SIMULATOR="1")
        os.environ.pop("LLM_API_KEY", None)
        sock.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets":[sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.1)
            assert server.started
            password = uuid4().hex
            with database(True) as db:
                create_account(db, "sales.test", "选型销售", "sales", encode_password(password), False)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel=os.getenv("WORKBENCH_BROWSER_CHANNEL") or None)
                context = browser.new_context()
                login = context.request.post(url + "/api/auth/login", headers={"X-Workspace-Request":"1"},
                    data={"username":"sales.test","password":password})
                assert login.ok
                check_selection(context, url)
                browser.close()
        finally:
            server.should_exit = True
            thread.join(8)
    print("PASS: authenticated inbox, FMSI match, linked quote, idempotent retry, product image and 390px layout")


if __name__ == "__main__":
    main()
