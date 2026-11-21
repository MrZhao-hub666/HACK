"""Run bounded, authenticated MediaCrawler searches in its local Python environment."""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

Platform = Literal["dy", "xhs"]
PLATFORMS = ("dy", "xhs")
FOLDERS = {"dy": "douyin", "xhs": "xhs"}
SEARCH_FAILED = "上游搜索失败，请检查平台登录和网络后重试。"
INTERRUPTED = "采集服务已重启，请重新搜索。"


class Search(BaseModel):
    id: UUID
    q: str = Field(min_length=1, max_length=180)
    platform: Platform | None = None


def read_records(directory, platform):
    records = []
    for path in (directory / FOLDERS[platform] / "json").glob("search_*.json"):
        if not path.name.startswith(("search_contents_", "search_comments_")):
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("Invalid MediaCrawler export")
        records.extend(rows)
    return records


def collect(platform, q, directory):
    # Keep the interactive login in a separate browser profile.
    import config
    from media_platform.douyin.client import DouYinClient
    from media_platform.douyin.login import DouYinLogin
    from media_platform.xhs.client import XiaoHongShuClient
    from media_platform.xhs.login import XiaoHongShuLogin
    from playwright.async_api import BrowserContext, BrowserType, Page

    import main as crawler

    config.ENABLE_CDP_MODE = False
    config.SAVE_LOGIN_STATE = True
    add_script = BrowserContext.add_init_script
    launch = BrowserType.launch_persistent_context
    goto = Page.goto
    matched = None
    login_flag = directory / "login"

    async def browser_script(context, script=None, *, path=None):
        if str(path) != "libs/stealth.min.js":
            return await add_script(context, script, path=path)

    async def launch_browser(browser, *args, **options):
        if platform == "dy":
            options["args"] = [*(options.get("args") or []), "--no-proxy-server"]
        return await launch(browser, *args, **options)

    async def load_page(page, url, **options):
        options.setdefault("wait_until", "commit" if platform == "dy" else "domcontentloaded")
        options.setdefault("timeout", 60000)
        return await goto(page, url, **options)

    def observe_login(begin):
        async def login(user):
            login_flag.touch()
            await begin(user)
            login_flag.unlink(missing_ok=True)

        return login

    async def manual_verification(*args, **kwargs):
        login_flag.touch()

    def observe_search(search, key):
        async def run(client, *args, **kwargs):
            nonlocal matched
            response = await search(client, *args, **kwargs)
            if isinstance(response.get(key), list):
                matched = len(response[key])
                if key == "items" and matched:
                    # The upstream loop only exports a page when has_more is true.
                    # This run requests exactly one page, including a populated last page.
                    response = {**response, "has_more": True}
            return response

        return run

    BrowserContext.add_init_script = browser_script
    BrowserType.launch_persistent_context = launch_browser
    Page.goto = load_page
    DouYinLogin.begin = observe_login(DouYinLogin.begin)
    DouYinLogin.check_page_display_slider = manual_verification
    XiaoHongShuLogin.begin = observe_login(XiaoHongShuLogin.begin)
    DouYinClient.search_info_by_keyword = observe_search(
        DouYinClient.search_info_by_keyword, "data"
    )
    XiaoHongShuClient.get_note_by_keyword = observe_search(
        XiaoHongShuClient.get_note_by_keyword, "items"
    )

    sys.argv = [
        "main.py", "--platform", platform, "--lt", "qrcode", "--type", "search",
        "--keywords", q.replace(",", " "), "--crawler_max_notes_count",
        "10" if platform == "dy" else "20", "--max_comments_count_singlenotes",
        "5", "--get_comment", "yes", "--get_sub_comment", "no", "--get_media",
        "no", "--enable_ip_proxy", "no", "--max_concurrency_num", "1",
        "--headless", "false", "--save_data_option", "json",
        "--save_data_path", str(directory),
    ]

    async def run():
        try:
            async with asyncio.timeout(420):
                await crawler.main()
        finally:
            async with asyncio.timeout(15):
                await crawler.async_cleanup()

    try:
        asyncio.run(run())
        if matched is None or (matched and not read_records(directory, platform)):
            raise RuntimeError(SEARCH_FAILED)
    except Exception as exc:
        network = re.search(r"net::ERR_[A-Z_]+", str(exc))
        path = traceback.extract_tb(exc.__traceback__)
        (directory / "failure.json").write_text(
            json.dumps({
                "type": type(exc).__name__,
                "network": network.group() if network else None,
                "frames": [f"{Path(frame.filename).name}:{frame.lineno}" for frame in path[-5:]],
            }),
            encoding="utf-8",
        )
        raise
    (directory / "complete").touch()


def serve(checkout, port):
    import uvicorn
    from api.routers.data import router as data_router

    root = checkout / ".workbench-searches"
    root.mkdir(exist_ok=True)
    app = FastAPI()
    data_router.routes = [
        route for route in data_router.routes
        if route.methods == {"GET"} and route.path.startswith("/data/files")
    ]
    app.include_router(data_router, prefix="/api")
    lock = threading.Lock()
    active = None

    def save(job):
        path = root / job["id"] / "state.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def load(ident):
        path = root / ident / "state.json"
        if not path.is_file():
            raise HTTPException(404, "找不到采集任务，请重新搜索。")
        job = json.loads(path.read_text(encoding="utf-8"))
        if job["status"] == "running" and active != ident:
            job["status"] = "complete"
            for channel in job["channels"]:
                if channel["status"] != "complete":
                    channel.update(status="failed", error=INTERRUPTED)
            save(job)
        return job

    def worker(job):
        nonlocal active
        try:
            for channel in job["channels"]:
                platform = channel["platform"]
                directory = root / job["id"] / platform
                directory.mkdir()
                with lock:
                    channel["status"] = "running"
                    save(job)
                try:
                    subprocess.run(
                        [
                            sys.executable, str(Path(__file__).resolve()), str(checkout),
                            "--collect", platform, "--keyword", job["q"],
                            "--output", str(directory),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=450,
                        check=True,
                    )
                    if not (directory / "complete").is_file():
                        raise RuntimeError(SEARCH_FAILED)
                    with lock:
                        channel.update(
                            status="complete",
                            count=len(read_records(directory, platform)),
                        )
                        save(job)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    error = (
                        "平台登录未完成，请在本机浏览器扫码后重试。"
                        if (directory / "login").exists() else SEARCH_FAILED
                    )
                    with lock:
                        channel.update(status="failed", error=error)
                        save(job)
        finally:
            with lock:
                for channel in job["channels"]:
                    if channel["status"] in {"queued", "running"}:
                        channel.update(status="failed", error=SEARCH_FAILED)
                job["status"] = "complete"
                active = None
                save(job)

    @app.post("/api/workbench/searches", status_code=202)
    def start(request: Search):
        nonlocal active
        ident = str(request.id)
        requested = (request.platform,) if request.platform else PLATFORMS
        with lock:
            directory = root / ident
            if directory.exists():
                existing = load(ident)
                if existing["q"] != request.q or requested != tuple(
                    c["platform"] for c in existing["channels"]
                ):
                    raise HTTPException(409, "采集任务已用于其他检索条件。")
                return existing
            if active:
                raise HTTPException(409, "已有采集任务正在运行，请稍后重试。")
            directory.mkdir()
            job = {
                "id": ident, "q": request.q, "status": "running",
                "channels": [
                    {"platform": platform, "status": "queued"} for platform in requested
                ],
            }
            active = ident
            save(job)
            threading.Thread(target=worker, args=(job,), daemon=True).start()
            return job

    @app.get("/api/workbench/searches/{ident}")
    def status(ident: UUID):
        with lock:
            job = load(str(ident))
            for channel in job["channels"]:
                if channel["status"] == "running" and (
                    root / str(ident) / channel["platform"] / "login"
                ).exists():
                    channel["status"] = "login"
            return job

    @app.get("/api/workbench/searches/{ident}/records/{platform}")
    def records(ident: UUID, platform: Platform):
        with lock:
            job = load(str(ident))
            if not any(
                c["platform"] == platform and c["status"] == "complete"
                for c in job["channels"]
            ):
                raise HTTPException(409, "该平台尚无可导入的采集结果。")
        return read_records(root / str(ident) / platform, platform)

    uvicorn.run(app, host="127.0.0.1", port=port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--collect", choices=PLATFORMS)
    parser.add_argument("--keyword", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    sys.path.insert(0, str(checkout))
    os.chdir(checkout)
    for name in ("EXA_API_KEY", "KOOYING_EXA_API_KEY", "BRAVE_API_KEY", "LLM_API_KEY"):
        os.environ.pop(name, None)
    proxies = [os.getenv("NO_PROXY", ""), ".douyin.com", ".xiaohongshu.com"]
    os.environ["NO_PROXY"] = ",".join(filter(None, proxies))
    if args.collect:
        collect(args.collect, args.keyword, args.output)
    else:
        serve(checkout, args.port)


if __name__ == "__main__":
    main()
