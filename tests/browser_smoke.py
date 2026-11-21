"""Run against an isolated SQLite database and the real Vue UI in Chromium."""

import os
import re
import socket
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright, expect

from src.api.main import app
from src.api.accounts import create_account, encode_password
from src.api.db import database
from src.api.domestic import examples as seed_domestic_examples


def check_loading_states(context, url):
    # Hold real GETs at the browser boundary so intermediate states are deterministic.
    page = context.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    lists, details, searches = [], [], []
    page.route("**/api/inquiries", lambda route: lists.append(route))
    page.route("**/api/inquiries/*", lambda route: details.append(route))
    page.route("**/api/discovery/search", lambda route: searches.append(route))
    try:
        with page.expect_request("**/api/inquiries"):
            page.goto(url + "/#overview")
        expect(page.locator(".sk-number")).to_have_count(4)
        expect(page.locator('[data-layout="chart"]')).to_be_visible()
        expect(page.locator(".donut")).to_have_count(0)
        page.get_by_role("button", name="客户档案", exact=True).click()
        expect(page.locator('[data-layout="cards"]')).to_be_visible()
        page.get_by_role("button", name="询盘收件箱").click()
        skeleton = page.locator('[data-layout="inbox"]')
        expect(skeleton).to_be_visible()
        assert (
            skeleton.locator(".skeleton-paint").evaluate(
                "el => getComputedStyle(el).animationName"
            )
            == "none"
        )
        lists.pop().fulfill(status=503, json={"detail": "队列暂不可用"})
        expect(page.get_by_role("alert")).to_contain_text("队列暂不可用")
        expect(skeleton).to_have_count(0)
        with page.expect_request("**/api/inquiries"):
            page.get_by_role("button", name="重试").click()
        expect(skeleton).to_be_visible()
        with page.expect_request("**/api/inquiries/*"):
            lists.pop().continue_()
        expect(page.locator(".ticket")).to_have_count(4)
        detail = page.locator('[data-layout="detail"]')
        expect(detail).to_be_visible()
        expect(page.locator("article.detail")).to_have_count(0)
        with page.expect_request("**/api/inquiries/*"):
            page.locator(".ticket").nth(1).click()
        selected = page.locator(".ticket.picked strong").inner_text()
        details.pop().continue_()
        expect(page.locator("article.detail h2")).to_have_text(selected)
        details.pop().continue_()
        note = page.get_by_label("跟进记录", exact=True)
        note.fill("保留正在编辑的内容")
        with page.expect_request("**/api/inquiries"):
            page.get_by_role("button", name="刷新数据").click()
        expect(note).to_have_value("保留正在编辑的内容")
        expect(page.locator(".content .loading-skeleton")).to_have_count(0)
        with page.expect_request("**/api/inquiries/*"):
            lists.pop().continue_()
        expect(detail).to_have_count(0)
        details.pop().continue_()
        expect(note).to_have_value("保留正在编辑的内容")
        with page.expect_request("**/api/discovery/search"):
            page.get_by_role("button", name="买家发现", exact=True).click()
        expect(page.locator('[data-layout="cards"]')).to_be_visible()
        searches.pop().fulfill(json={"mode": "samples", "query": "", "items": []})
        expect(page.get_by_text("没有匹配的企业", exact=False)).to_be_visible()
        expect(page.locator(".content .loading-skeleton")).to_have_count(0)
    finally:
        page.close()


def check_alternative_buyers(page):
    panel = page.locator(".alternative-panel")
    panel.locator("summary").click()
    page.get_by_role("button", name="去关联企业").click()
    expect(page.get_by_label("关联企业", exact=True)).to_be_focused()
    page.get_by_label("关联企业", exact=True).select_option(label="L&R Haulage")
    expect(
        page.get_by_label("关联企业", exact=True).locator("option:checked")
    ).to_have_text("L&R Haulage")
    expect(panel.locator("h3", has_text="L&R Haulage")).to_be_attached()
    panel.locator("summary").click()
    panel.get_by_role("button", name="认领并查找").click()
    expect(panel.locator(".alternative-card")).to_have_count(2)
    expect(panel.locator(".alt-batch")).to_contain_text("本地公开资料")
    expect(page.get_by_label("负责人", exact=True)).to_have_value("林悦")
    expect(page.locator(".desktop-nav .assistant-count")).to_have_text("2")
    page.locator(".desktop-nav .assistant-entry").click()
    brief = page.get_by_role("dialog", name="销售跟进简报")
    cards = brief.locator(".alternative-card")
    expect(cards).to_have_count(2)
    page.set_viewport_size({"width": 390, "height": 844})
    assert brief.evaluate("el=>el.scrollWidth<=el.clientWidth")
    first = cards.first
    expect(first).to_contain_text("同市场潜客")
    expect(first.get_by_role("link", name="业务依据")).to_have_attribute(
        "href", re.compile("^https://")
    )
    first.get_by_role("button", name="加入客户档案").click()
    expect(cards).to_have_count(1)
    cards.first.get_by_role("button", name="不相关").click()
    expect(brief).to_contain_text("暂无待处理推荐")
    brief.get_by_role("button", name="关闭简报").click()
    page.set_viewport_size({"width": 1440, "height": 1000})
    expect(panel.locator(".alternative-card")).to_have_count(1)
    expect(panel).to_contain_text("已采纳")
    expect(panel).to_contain_text("负责人 · 林悦")


def check_domestic(page):
    expect(page.get_by_role("button", name="国内线索", exact=True)).to_have_count(0)
    page.get_by_role("button", name="买家发现", exact=True).click()
    page.get_by_label("数据来源").select_option("domestic")
    expect(page.get_by_text("接入 MediaCrawler 数据")).to_have_count(0)
    expect(page.locator('input[type="file"]')).to_have_count(0)
    cards = page.locator(".domestic-card")
    expect(cards).to_have_count(2)
    expect(cards.filter(has_text="80 套")).to_contain_text("重卡刹车片")
    page.get_by_role("textbox", name="关键词", exact=True).fill("29087")
    page.get_by_role("button", name="搜索线索").click()
    expect(cards).to_have_count(1)
    expect(cards.first).to_contain_text("小红书")
    page.get_by_role("textbox", name="关键词", exact=True).fill("")
    page.get_by_label("内容意图").select_option("供应推广")
    page.get_by_role("button", name="搜索线索").click()
    expect(cards.first).to_contain_text("厂家直销")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_role("button", name="工作台总览", exact=True).click()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(
            DB_PATH=str(Path(tmp) / "ui.sqlite3"), DEMO_DATA="1", ENABLE_SIMULATOR="1"
        )
        os.environ.pop("LLM_API_KEY", None)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        thread.start()
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            initial = "Smoke-initial-password"
            chosen = "Smoke-personal-password"
            with database(True) as db:
                encoded = encode_password(initial)
                create_account(db, "lin.yue", "林悦", "admin", encoded)
                create_account(db, "chen.zhou", "陈舟", "sales", encoded)
            seed_domestic_examples()
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(url)
                expect(page.get_by_role("heading", name="登录工作台")).to_be_visible()
                page.get_by_role("textbox", name="账号", exact=True).fill("lin.yue")
                page.locator('input[name="password"]').fill(initial)
                page.get_by_role("button", name="登录", exact=True).click()
                expect(page.get_by_role("heading", name="设置新密码")).to_be_visible()
                page.get_by_label("当前密码", exact=True).fill(initial)
                page.get_by_label("新密码", exact=True).fill(chosen)
                page.get_by_label("确认新密码", exact=True).fill(chosen)
                page.get_by_role("button", name="保存新密码").click()
                expect(
                    page.get_by_role("heading", name="海外销售工作台")
                ).to_be_visible()
                heading = page.get_by_role("heading", name="海外销售工作台")
                assert heading.evaluate("""async el => {
                    const font = getComputedStyle(el).fontFamily;
                    const faces = await document.fonts.load('600 16px "Noto Sans SC Variable"', el.textContent);
                    return font.includes("Noto Sans SC Variable") && faces.length > 0;
                }""")
                expect(
                    page.locator(".desktop-nav .lucide-layout-dashboard")
                ).to_be_visible()
                expect(page.locator(".priority-row")).to_have_count(4)
                expect(page.locator(".donut strong")).to_have_text("4")
                check_loading_states(context, url)
                check_domestic(page)
                page.get_by_role("button", name="查看跟进简报").click()
                brief = page.get_by_role("dialog", name="销售跟进简报")
                expect(brief.locator(".brief-card")).to_have_count(4)
                brief.get_by_role("button", name="我的交接", exact=True).click()
                expect(brief).to_contain_text("林悦名下有 0 条未结束的询盘")
                brief.get_by_role("button", name="客户核实", exact=True).click()
                brief.locator(".brief-card").first.click()
                expect(page.get_by_role("heading", name="编辑客户档案")).to_be_visible()
                page.get_by_role("button", name="关闭", exact=True).click()
                page.get_by_role("button", name="工作台总览").click()
                page.get_by_role("button", name="待回复询盘", exact=False).click()
                expect(page.locator(".pills .on")).to_have_text("业务待回")
                expect(page.locator(".ticket")).to_have_count(4)
                check_alternative_buyers(page)
                page.get_by_role("button", name="买家发现", exact=True).click()
                expect(page.locator(".companycard")).to_have_count(3)
                card = page.locator(".companycard").filter(has_text="Swee Siang")
                card.get_by_role("button", name="加入客户档案").click()
                expect(card.get_by_role("button", name="已存入档案")).to_be_visible()
                page.get_by_role("button", name="客户档案", exact=True).click()
                card = page.locator(".companycard").filter(has_text="Swee Siang")
                card.get_by_role("button", name="编辑档案").click()
                page.get_by_label("本企业采购能力", exact=True).select_option(
                    "可直接采购"
                )
                page.get_by_role("button", name="保存档案").click()
                expect(card).to_contain_text("可直接采购")
                page.get_by_role("button", name="渠道模拟器", exact=True).click()
                for provider in (
                    "WhatsApp 商业号码",
                    "Instagram 私信",
                    "X 私信、提及与回复",
                    "TikTok 企业私信",
                    "Telegram 机器人",
                    "LINE 官方账号",
                ):
                    expect(
                        page.locator("article.companycard").get_by_text(
                            provider, exact=True
                        )
                    ).to_be_visible()
                page.get_by_role("button", name="填入询价样例").click()
                page.get_by_label("消息来源").select_option("whatsapp")
                page.get_by_role("button", name="发送模拟事件").click()
                expect(page.get_by_text("消息已入库", exact=False).last).to_be_visible()
                page.get_by_role("button", name="发送模拟事件").click()
                expect(page.get_by_text("重复事件已忽略", exact=False)).to_be_visible()
                page.get_by_role("button", name="打开询盘").click()
                expect(page.locator("article.detail h2")).to_contain_text(
                    "Nadia · Demo Workshop"
                )
                page.get_by_text("查看来源编号", exact=True).click()
                expect(page.locator(".message-source")).to_contain_text("demo:kooying")
                expect(page.locator(".bubble b")).to_have_text("WhatsApp 商业号码")
                page.get_by_label("负责人", exact=True).select_option("陈舟")
                expect(page.get_by_label("负责人", exact=True)).to_have_value("陈舟")
                page.get_by_label("跟进记录", exact=True).fill("已向客户询问每套片数。")
                page.get_by_role("button", name="登记已回复", exact=True).click()
                expect(page.get_by_label("处理状态")).to_have_value("等客户补充")
                page.get_by_role("button", name="处理记录", exact=False).click()
                expect(
                    page.locator(".hist").filter(has_text="登记人工回复")
                ).to_be_visible()
                page.reload()
                expect(page.locator(".ticket")).to_have_count(5)
                page.set_viewport_size({"width": 390, "height": 844})
                expect(page.locator("h1")).to_be_visible()
                page.emulate_media(reduced_motion="reduce")
                menu = page.get_by_role("button", name="打开导航")
                menu.click()
                assert page.locator(".mobile-nav[open]").evaluate(
                    "el => getComputedStyle(el).transitionDuration === '0s'"
                )
                page.keyboard.press("Escape")
                expect(menu).to_be_focused()
                for name in [
                    "工作台总览",
                    "买家发现",
                    "客户档案",
                    "消息补录",
                    "渠道模拟器",
                    "询盘收件箱",
                ]:
                    page.get_by_role("button", name="打开导航").click()
                    page.locator(".mobile-nav").get_by_role("button", name=name).click()
                    expect(page.locator("h1")).to_have_text(
                        "海外销售工作台" if name == "工作台总览" else name
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    ), name
                page.get_by_role("button", name="打开导航").click()
                page.get_by_role("button", name="我的账号与团队").click()
                page.get_by_role("button", name="成员管理").click()
                page.get_by_role("button", name="添加成员").click()
                page.get_by_label("登录账号").fill("new.sales")
                page.get_by_label("成员姓名").fill("新成员")
                page.get_by_label("临时密码").fill("Temporary-new-member")
                page.get_by_role("button", name="创建成员").click()
                expect(page.locator(".member-list")).to_contain_text("new.sales")
                page.get_by_role("button", name="我的账号", exact=True).click()
                page.get_by_role("button", name="退出登录").click()
                expect(page.get_by_role("heading", name="登录工作台")).to_be_visible()
                page.reload()
                expect(page.get_by_role("heading", name="登录工作台")).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                )
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(8)
            sock.close()
    print(
        "Browser smoke passed: discovery, company review, simulator, deduplication, handoff and mobile layout."
    )


if __name__ == "__main__":
    main()
