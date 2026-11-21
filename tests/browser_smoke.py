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
        expect(
            page.get_by_role("tabpanel", name="客户经营统计").get_by_role("status")
        ).to_be_visible()
        page.get_by_role("tab", name="询盘跟进统计").click()
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
    page.mouse.click(12, 100)
    expect(brief).to_be_hidden()
    page.set_viewport_size({"width": 1440, "height": 1000})
    expect(panel.locator(".alternative-card")).to_have_count(1)
    expect(panel).to_contain_text("已采纳")
    expect(panel).to_contain_text("负责人 · 林悦")


def check_outreach(page):
    page.get_by_role("button", name="展会拓客", exact=True).click()
    expect(page.get_by_role("heading", name="LKQ Europe Gmbh")).to_be_visible()
    page.get_by_label("来源", exact=True).select_option("广交会")
    page.get_by_role("button", name="检索线索").click()
    expect(page.get_by_role("heading", name="Command Auto Parts LTD")).to_be_visible()
    page.get_by_label("来源", exact=True).select_option("上海法兰克福")
    page.get_by_role("button", name="检索线索").click()
    page.locator(".companycard").filter(has_text="LKQ").get_by_role(
        "button", name="登记线索"
    ).click()
    page.get_by_role("button", name="保存并核实").click()
    page.get_by_label("原文摘录").fill("LKQ Europe Gmbh（瑞士）")
    page.get_by_label("核实理由").fill("展会主办方列为优选买家代表")
    page.get_by_role("button", name="保存核实结果").click()
    expect(page.get_by_role("heading", name="采购联系方式")).to_be_visible()
    page.get_by_role("button", name="填入待核实字段").first.click()
    page.get_by_role("button", name="保存核实联系方式").click()
    page.get_by_label("展会名称（邮件用）").fill("Automechanika Shanghai")
    page.get_by_label("展馆及展位").fill("Hall 2 / B15")
    page.get_by_label("开始日期").fill("2027-11-21")
    page.get_by_label("结束日期").fill("2027-11-25")
    page.get_by_label("收件邮箱", exact=True).select_option(
        label="lkqe-direct-purchasing@lkqeurope.com · 直接采购部门"
    )
    page.get_by_role("button", name="生成英文邀约草稿").click()
    expect(page.get_by_label("邮件正文")).to_have_value(re.compile("Hall 2 / B15"))
    page.get_by_label("产品匹配度", exact=True).select_option("C")
    with page.expect_download() as download:
        page.get_by_role("link", name="导出当前名单 Excel").click()
    assert download.value.suggested_filename.endswith(".xlsx")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="检索来源", exact=True).click()
    page.get_by_label("来源", exact=True).select_option("社媒原帖")
    page.get_by_role("button", name="检索线索").click()
    page.get_by_role("button", name="登记线索").click()
    page.get_by_role("button", name="保存并核实").click()
    page.get_by_label("原文摘录").fill("I'd rather show up to a shop with my own parts")
    page.get_by_role("button", name="辅助判断原帖意图").click()
    expect(page.get_by_label("来源意图")).to_have_value("待判断")
    page.get_by_label("处理结论").select_option("排除")
    page.get_by_label("核实理由").fill("历史车主需求，本轮展会名单只跟进企业采购。")
    page.get_by_role("button", name="保存核实结果").click()
    expect(
        page.locator(".out-row").filter(has_text="Trailer brake shoes")
    ).to_contain_text("排除")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 1440, "height": 1000})


def check_customer_statistics(context, url):
    from datetime import datetime, timezone

    page = context.new_page()
    try:
        page.clock.set_fixed_time(datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc))
        base = context.request.get(url + "/api/companies").json()[0]
        dates = [
            "2026-11-20T16:01:00Z",
            "2026-11-20T15:59:59Z",
            "2026-11-03T03:00:00Z",
            None,
        ]
        countries = ["MY", "Malaysia", "德国", ""]
        test_buyers = [
            dict(
                base,
                id=i + 100,
                name=f"统计验收企业{i}",
                country=countries[i],
                archived_at=d,
                outreach_grade="A" if i == 2 else None,
                won_at=d if i == 1 else None,
                owner="销售" if i == 2 else "",
                source="广交会" if i < 2 else "销售录入",
                contact_gender="女" if i < 2 else "",
                contact_age_band="35-44" if i == 0 else "",
            )
            for i, d in enumerate(dates)
        ]
        page.route("**/api/companies", lambda route: route.fulfill(json=test_buyers))
        rows = context.request.get(url + "/api/inquiries").json()
        for i, row in enumerate(rows):
            row.update(
                company_id=100 if i < 2 else 101, state="跟进中" if i < 2 else "已结束"
            )
        page.route("**/api/inquiries", lambda route: route.fulfill(json=rows))
        page.goto(url + "/#overview")
        customers = page.get_by_role("tab", name="客户经营统计")
        inquiries = page.get_by_role("tab", name="询盘跟进统计")
        expect(customers).to_have_attribute("aria-selected", "true")
        recommendation_card = page.get_by_role(
            "tabpanel", name="客户经营统计"
        ).get_by_role("region", name="潜在客户推荐")
        expect(recommendation_card).to_be_visible()
        expect(page.get_by_role("heading", name="渠道分布")).to_be_hidden()
        for label, number in [
            ("全部客户", 4),
            ("今日新增", 1),
            ("已确认成交", 1),
            ("待分配客户", 3),
            ("跟进中客户", 1),
        ]:
            expect(
                page.get_by_role("button", name=f"{label} {number} 家，查看明细")
            ).to_be_visible()
        page.get_by_role("button", name="马来西亚 2 家 50%").click()
        dialog = page.get_by_role("dialog", name="马来西亚")
        expect(dialog.get_by_role("link")).to_have_count(2)
        dialog.get_by_role("button", name="关闭明细").click()
        page.get_by_label("客户分布维度").select_option("procurement")
        expect(page.locator(".trend-summary strong")).to_have_text("2")
        page.get_by_role("button", name="近30天").click()
        expect(page.locator(".trend-summary strong")).to_have_text("3")
        page.get_by_role("button", name="档龄", exact=True).click()
        expect(page.get_by_role("button", name="入档时间未知 1 家 25%")).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        gender = page.get_by_role("region", name="主联系人性别")
        age = page.get_by_role("region", name="主联系人年龄段")
        expect(gender.get_by_role("button", name="女 2 家 50%")).to_be_visible()
        expect(gender.get_by_role("button", name="未登记 2 家 50%")).to_be_visible()
        expect(age.get_by_role("button", name="未登记 3 家 75%")).to_be_visible()
        age.get_by_role("button", name="35–44 岁 1 家 25%").click()
        breakdown = page.get_by_role("dialog", name="主联系人年龄段 · 35–44 岁")
        expect(breakdown.get_by_role("link")).to_contain_text("统计验收企业0")
        page.mouse.click(2, 2)
        expect(breakdown).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        inquiries.click()
        expect(page.get_by_role("tabpanel", name="询盘跟进统计")).to_be_visible()
        expect(recommendation_card).to_be_hidden()
        expect(page.get_by_role("heading", name="优先跟进")).to_be_visible()
        expect(page.get_by_role("heading", name="客户分级")).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        inquiries.press("ArrowLeft")
        expect(customers).to_be_focused()
        expect(page.get_by_label("客户分布维度")).to_have_value("procurement")
        expect(page.get_by_role("button", name="档龄", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        page.get_by_role("button", name="今日新增 1 家，查看明细").click()
        expect(page.get_by_role("dialog").get_by_role("link")).to_contain_text(
            "统计验收企业0"
        )
        page.keyboard.press("Escape")
        test_buyers.clear()
        page.reload()
        expect(page.get_by_text("客户入档后显示分布")).to_be_visible()
        expect(
            page.get_by_role("button", name="全部客户 0 家，查看明细")
        ).to_be_visible()
    finally:
        page.close()


def check_recommendation_markdown(context, url):
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.route(
            "**/api/discovery/recommendations",
            lambda route: route.fulfill(json={
                "configured": True, "auto_due": False, "directions": [],
                "items": [{
                    "id": "formatting", "title": "证据排版验收", "market": "",
                    "source": "实时网页搜索", "grade": "B", "direction": "经销进口",
                    "reason": "业务证据", "url": "https://example.com/about", "published": "",
                    "evidence": (
                        "## Company overview\n\n- **Truck parts**\n\n"
                        "| Part | Type |\n| --- | --- |\n| Pads | Brake |\n\n"
                        "|First excerpt|\n\n|Second excerpt|\n\n"
                        "[Products](/parts) · [Email](mailto:sales@example.com)\n\n"
                        "<button>外部 HTML</button>"
                    ),
                }],
            }),
        )
        page.goto(url + "/#overview")
        recommendation = page.get_by_role("button", name=re.compile("证据排版验收"))
        recommendation.click()
        popup = page.get_by_role("dialog", name="证据排版验收")
        expect(popup.get_by_role("heading", name="Company overview", level=3)).to_be_visible()
        expect(popup.locator("li strong")).to_have_text("Truck parts")
        expect(popup.get_by_role("columnheader", name="Part")).to_be_visible()
        expect(popup.get_by_role("cell", name="Second excerpt")).to_be_visible()
        expect(popup.get_by_role("link", name="Products")).to_have_attribute(
            "href", "https://example.com/parts"
        )
        expect(popup.get_by_role("link", name="Email")).to_have_count(0)
        expect(popup.get_by_text("<button>外部 HTML</button>", exact=True)).to_be_visible()
        expect(popup.get_by_role("link", name="查看原文")).to_have_attribute(
            "href", "https://example.com/about"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.keyboard.press("Escape")
        expect(popup).to_be_hidden()
        recommendation.click()
        heading = popup.get_by_role("heading", name="Company overview", level=3)
        heading.click()
        expect(popup).to_be_visible()
        bounds = heading.bounding_box()
        page.mouse.move(bounds["x"] + 5, bounds["y"] + 5)
        page.mouse.down()
        page.mouse.move(2, 2)
        page.mouse.up()
        expect(popup).to_be_visible()
        page.mouse.click(2, 2)
        expect(popup).to_be_hidden()
        expect(recommendation).to_be_focused()

        page.route(
            "**/api/discovery/recommendations/refresh",
            lambda route: route.fulfill(status=409, json={"detail": "推荐正在更新，请稍后查看结果。"}),
        )
        page.get_by_role("button", name="更新推荐", exact=True).click()
        expect(page.locator(".toast-info")).to_contain_text("推荐正在更新")
        expect(page.locator(".toast-success, .toast-error")).to_have_count(0)
        expect(recommendation).to_be_visible()
    finally:
        page.close()


def check_domestic(page):
    expect(page.get_by_role("button", name="国内线索", exact=True)).to_have_count(0)
    page.get_by_role("button", name="买家发现", exact=True).click()
    page.get_by_label("数据来源").select_option("domestic")
    expect(page.get_by_text("接入 MediaCrawler 数据")).to_have_count(0)
    expect(page.locator('input[type="file"]')).to_have_count(0)
    search = page.get_by_role("button", name="搜索线索", exact=True)
    expect(search).to_be_enabled()
    page.get_by_role("textbox", name="关键词", exact=True).fill("刹车片")
    with page.expect_response("**/api/domestic/searches") as response:
        search.click()
    assert response.value.status == 503
    assert response.value.request.method == "POST"
    assert response.value.request.post_data_json["q"] == "刹车片"
    expect(page.get_by_role("alert")).to_contain_text("尚未配置 MediaCrawler")
    expect(page.locator(".domestic-card")).to_have_count(0)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_role("button", name="工作台总览", exact=True).click()


def check_domestic_import_retry(context, url):
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    jobs = {}
    imports = []

    def start_job(route):
        request = route.request.post_data_json
        jobs[request["id"]] = {
            "id": request["id"], "q": request["q"], "status": "complete",
            "channels": [{"platform": "dy", "status": "complete", "count": 0}],
        }
        route.fulfill(status=202, json=jobs[request["id"]])

    def import_job(route):
        imports.append(route.request.url.split("/")[-2])
        if len(imports) == 1:
            route.fulfill(status=502, json={"detail": "采集服务暂不可用"})
        elif len(imports) == 2:
            route.fulfill(status=413, json={"detail": "批次超出导入上限"})
        else:
            route.fulfill(json={"count": 0})

    try:
        page.route("**/api/domestic/searches", start_job)
        page.route(
            "**/api/domestic/searches/*",
            lambda route: route.fulfill(json=jobs[route.request.url.rsplit("/", 1)[-1]]),
        )
        page.route("**/api/domestic/searches/*/import", import_job)
        page.route("**/api/domestic/signals?**", lambda route: route.fulfill(json={
            "items": [], "total": 0, "index_state": "indexed",
        }))
        page.goto(url + "/#discovery")
        page.get_by_label("数据来源").select_option("domestic")
        keyword = page.get_by_role("textbox", name="关键词", exact=True)
        search = page.get_by_role("button", name="搜索线索", exact=True)
        keyword.fill("刹车片")
        search.click()
        expect(page.get_by_role("alert")).to_have_text("采集服务暂不可用")
        search.click()
        expect(page.get_by_role("alert")).to_have_text("批次超出导入上限")
        keyword.fill("车队")
        search.click()
        expect(page.get_by_text("本次采集没有符合筛选条件的线索。", exact=True)).to_be_visible()
        assert [job["q"] for job in jobs.values()] == ["刹车片", "车队"]
        first, second = jobs
        assert imports == [first, first, second]
        expect(keyword).to_have_value("车队")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        page.close()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(
            DB_PATH=str(Path(tmp) / "ui.sqlite3"), DEMO_DATA="1", ENABLE_SIMULATOR="1"
        )
        os.environ.pop("ADMIN_BOOTSTRAP_PASSWORD_HASH", None)
        os.environ.pop("EXA_API_KEY", None)
        os.environ.pop("BRAVE_API_KEY", None)
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("MEDIACRAWLER_URL", None)
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
                page.get_by_role("tab", name="询盘跟进统计").click()
                expect(page.locator(".priority-row")).to_have_count(4)
                expect(page.locator(".donut strong")).to_have_text("4")
                check_loading_states(context, url)
                check_customer_statistics(context, url)
                check_recommendation_markdown(context, url)
                check_domestic(page)
                check_domestic_import_retry(context, url)
                open_brief = page.get_by_role("button", name="查看跟进简报")
                open_brief.click()
                brief = page.get_by_role("dialog", name="销售跟进简报")
                expect(brief.locator(".brief-card")).to_have_count(4)
                brief.get_by_role("button", name="我的交接", exact=True).click()
                expect(brief).to_contain_text("林悦名下有 0 条未结束的询盘")
                page.mouse.click(12, 100)
                expect(brief).to_be_hidden()
                open_brief.click()
                expect(brief.get_by_role("button", name="优先跟进")).to_have_attribute("aria-pressed", "true")
                brief.get_by_role("button", name="客户核实", exact=True).click()
                brief.locator(".brief-card").first.click()
                editor = page.get_by_role("dialog", name="编辑客户档案")
                expect(editor).to_be_visible()
                page.mouse.click(2, 2)
                expect(editor).to_be_hidden()
                expect(page).to_have_url(url + "/#companies")
                page.get_by_role("button", name="工作台总览").click()
                page.get_by_role("tab", name="询盘跟进统计").click()
                page.get_by_role("button", name="待回复询盘", exact=False).click()
                expect(page.locator(".pills .on")).to_have_text("业务待回")
                expect(page.locator(".ticket")).to_have_count(4)
                check_alternative_buyers(page)
                check_outreach(page)
                page.get_by_role("button", name="买家发现", exact=True).click()
                expect(page.locator(".companycard")).to_have_count(3)
                page.set_viewport_size({"width": 390, "height": 844})
                market = page.get_by_role("combobox", name="目标市场", exact=True)
                source = page.get_by_role("combobox", name="数据来源", exact=True)
                expect(market).to_have_value("马来西亚")
                for region, country in (
                    ("欧洲", "德国"),
                    ("北美洲", "美国"),
                    ("南美洲", "巴西"),
                ):
                    expect(
                        market.locator(
                            f'optgroup[label="{region}"] option[value="{country}"]'
                        )
                    ).to_have_count(1)
                    expect(market.locator(f'option[value="{region}"]')).to_have_count(0)
                market.select_option("德国")
                search = page.get_by_role("button", name="搜索企业")
                search.click()
                expect(page.get_by_text("没有匹配的企业", exact=False)).to_be_visible()
                source.select_option("live")
                market.select_option("")
                page.get_by_label("自定义市场", exact=True).fill("Rotterdam")
                with page.expect_request("**/api/discovery/search") as request:
                    search.click()
                assert request.value.post_data_json["market"] == "Rotterdam"
                expect(page.get_by_role("alert")).to_contain_text("EXA_API_KEY")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.set_viewport_size({"width": 1440, "height": 1000})
                source.select_option("samples")
                market.select_option("马来西亚")
                search.click()
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
                page.get_by_label("主联系人性别", exact=True).select_option("女")
                page.get_by_label("主联系人年龄段", exact=True).select_option("35-44")
                page.set_viewport_size({"width": 390, "height": 844})
                page.route(
                    "**/api/companies/*",
                    lambda route: route.fulfill(status=409, json={"detail": "档案信息有冲突"}),
                    times=1,
                )
                page.get_by_role("button", name="保存档案").click()
                error_toast = editor.locator(".toast-error")
                expect(error_toast).to_have_text("客户档案保存失败")
                expect(editor.get_by_role("alert")).to_have_text("档案信息有冲突")
                assert error_toast.evaluate("el => {const r = el.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth}")
                page.get_by_role("button", name="保存档案").click()
                expect(page.locator("body > .toast-success")).to_have_text("客户档案已保存")
                expect(editor).to_be_hidden()
                expect(card).to_contain_text("可直接采购")
                page.set_viewport_size({"width": 1440, "height": 1000})
                card.get_by_role("button", name="编辑档案").click()
                expect(page.get_by_label("主联系人性别", exact=True)).to_have_value("女")
                expect(page.get_by_label("主联系人年龄段", exact=True)).to_have_value("35-44")
                page.get_by_label("企业名称", exact=True).fill("未保存的名称")
                page.mouse.click(2, 2)
                expect(editor).to_be_hidden()
                card.get_by_role("button", name="编辑档案").click()
                expect(page.get_by_label("企业名称", exact=True)).not_to_have_value("未保存的名称")
                editor.get_by_role("button", name="关闭", exact=True).click()
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
                menu.click()
                mobile_nav = page.get_by_role("dialog", name="工作台导航")
                expect(mobile_nav).to_be_visible()
                page.mouse.click(350, 100)
                expect(mobile_nav).to_be_hidden()
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
                account = page.get_by_role("dialog", name="账号与团队")
                account.get_by_role("button", name="成员管理").click()
                page.mouse.click(2, 2)
                expect(account).to_be_hidden()
                menu.click()
                page.get_by_role("button", name="我的账号与团队").click()
                expect(account.get_by_role("button", name="我的账号")).to_have_attribute("aria-pressed", "true")
                account.get_by_role("button", name="成员管理").click()
                page.get_by_role("button", name="添加成员").click()
                page.get_by_label("登录账号").fill("new.sales")
                page.get_by_label("成员姓名").fill("新成员")
                page.get_by_label("临时密码").fill("Temporary-new-member")
                page.get_by_role("button", name="创建成员").click()
                expect(page.locator(".member-list")).to_contain_text("new.sales")
                expect(account.locator(".toast-success")).to_have_text("成员已创建")
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
