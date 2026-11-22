"""Exercise the built workspace against an isolated inbox and the running selector."""
from tests.pg_workspace import test_workspace
import os
import socket
import threading
import time
from uuid import uuid4

import uvicorn
from playwright.sync_api import expect, sync_playwright
from src.backend.api.accounts import create_account, encode_password
from src.backend.api.db import database
from src.backend.api.main import app


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


def check_assistant_and_products(context, url):
    page = context.new_page()
    try:
        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(url + "/#assistant")
        expect(page.get_by_role("heading", name="销售助手")).to_be_visible()
        composer = page.get_by_role("textbox", name="客户需求")
        send = page.get_by_role("button", name="发送", exact=True)
        composer.fill("客户要配刹车片")
        send.click()
        expect(page.get_by_text("这次按国内版还是外贸版采购？")).to_be_visible()
        composer.fill("外贸美国车，鼓式，旧件编号 FMSI 4702a")
        composer.press("Enter")
        expect(page.get_by_text("请问您需要多少", exact=False)).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        composer.fill("半金属，100片")
        send.click()
        expect(page.get_by_text("预设材料价试算", exact=False)).to_be_visible()
        expect(page.locator(".answer-quote")).to_contain_text("CNY 1,021.00")
        customer_reply = page.locator("[data-customer-reply]").last
        expect(customer_reply).to_contain_text("价格还需核实")
        expect(customer_reply).not_to_contain_text("1,021.00")
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
        page.get_by_role("button", name="复制对客答复").last.click()
        expect(page.get_by_text("已复制", exact=True)).to_be_visible()
        assert page.evaluate("navigator.clipboard.readText()") == customer_reply.inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        page.get_by_role("button", name="打开导航").click()
        page.locator(".mobile-nav").get_by_role("button", name="产品管理").click()
        page.get_by_role("button", name="美国", exact=True).click()
        search = page.get_by_role("searchbox", name="搜索产品")
        search.fill("FMSI 4702a")
        detail = page.get_by_role("article", name="产品详情")
        expect(detail).to_contain_text("FAG0002")
        expect(detail.get_by_role("heading", name="详细规格")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        search.fill("")
        page.get_by_role("button", name="国内", exact=True).click()
        expect(page.get_by_role("button", name="美国", exact=True)).to_be_hidden()
        expect(detail).to_contain_text("DCG0001")
        page.get_by_role("button", name="打开导航").click()
        page.locator(".mobile-nav").get_by_role("button", name="销售助手").click()
        quote = page.locator(".answer-quote")
        expect(quote).to_contain_text("CNY 1,021.00")
        expect(quote).to_be_in_viewport(ratio=1)
        page.get_by_role("button", name="新建对话").click()
        composer.fill("客户要买的刹车片是给出口日本的车用的，OEM是MC828513，帮我推荐型号")
        send.click()
        expect(page.get_by_role("heading", name="GYS-108")).to_be_visible()
        expect(page.get_by_text("OEM MC828513", exact=True)).to_be_visible()
        expect(page.locator(".product-answer")).to_have_count(1)
        page.set_viewport_size({"width": 1440, "height": 960})
        page.get_by_role("button", name="新建对话").click()
        composer.fill("用户的卡车要出口日本，OEM的编号是MC809750，怎么推荐")
        send.click()
        card = page.get_by_role("button", name="查看 GYS-106 详情")
        card.click()
        detail = page.get_by_role("article", name="产品详情")
        expect(detail.get_by_role("heading", name="GYS-106")).to_be_visible()
        expect(detail.get_by_text("孔数", exact=True).locator("..")).to_contain_text("10")
        assert detail.bounding_box()["x"] > page.get_by_role("region", name="销售对话").bounding_box()["x"]
        expect(detail.locator("img").first).to_be_visible()
        page.wait_for_function("document.querySelector('.assistant-detail img')?.naturalWidth > 0")
        composer.fill("客户需要孔数6孔的")
        send.click()
        expect(page.locator("[data-customer-reply]").last).to_contain_text("目录规格为 10 孔，您需要的是 6 孔")
        composer.fill("用于国内")
        send.click()
        expect(page.locator("[data-customer-reply]").last).to_contain_text("编号 MC809750 对应外贸目录")
        composer.fill("鼓片")
        send.click()
        expect(page.locator("[data-customer-reply]")).to_have_count(4)
        expect(page.locator("[data-customer-reply]").last).to_contain_text("请提供国内版旧件编号")
        assert page.locator(".product-answer").count() == 2
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("button", name="关闭详情").click()
        card.first.click()
        expect(detail).to_be_in_viewport()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.get_by_role("button", name="关闭详情").click()
        expect(detail).to_have_count(0)
        expect(card.first).to_be_focused()
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
                check_assistant_and_products(context, url)
                browser.close()
        finally:
            server.should_exit = True
            thread.join(8)
    print("PASS: inbox selection, linked quote, assistant conversation, product catalogue and 390px layout")


if __name__ == "__main__":
    main()
