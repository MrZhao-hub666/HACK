import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from .db import one, utc

SAMPLES = [
    dict(
        name="L&R Haulage",
        kind="车队",
        url="https://lrh.com.my/facilities-workshop-depot.html",
        place="Labu, Negeri Sembilan",
        website="https://lrh.com.my",
        social="",
        evidence="企业设施页列有自营车队、Labu 维修场站及为车队服务的维修团队。",
        next_action="核实制动件由车队直接采购还是由维保商供应。",
    ),
    dict(
        name="Swee Siang / Dr Truck",
        kind="维修厂",
        url="https://www.newpages.com.my/v2/en/company/210093/Swee-Siang-Sdn--Bhd-.html",
        place="Batu Caves, Selangor",
        website="https://sweesiang.com",
        social="https://www.facebook.com/sweesiangdrtruck/",
        evidence="企业目录列出重卡与挂车的制动维修业务、公司官网和 Facebook 业务主页。",
        next_action="确认维修厂是否为客户车辆统一备货。",
    ),
    dict(
        name="Allegiance Malaysia",
        kind="维修及配件",
        url="https://allegiance.my/workshop/",
        place="Shah Alam / Johor Bahru",
        website="https://allegiance.my",
        social="",
        evidence="官网列有两地维修中心、商用车售后件采购与独立维修服务。",
        next_action="核实两地常用制动件是否集中采购。",
    ),
]
BUYER_TERMS = {
    "车队": "haulage fleet own workshop",
    "维修厂": "heavy truck brake repair workshop",
    "维修及配件": "commercial truck workshop aftermarket spare parts",
    "配件门店": "commercial vehicle brake parts shop",
    "贸易商": "commercial vehicle parts trader",
    "渠道伙伴": "trucking industry association",
    "待识别": "truck fleet OR commercial truck workshop",
}
MARKETS = {
    "马来西亚": "Malaysia",
    "菲律宾": "Philippines",
    "泰国": "Thailand",
    "巴西": "Brazil",
    "阿联酋": "United Arab Emirates",
    "墨西哥": "Mexico",
    "印尼": "Indonesia",
}


def valid_url(value):
    if not value:
        return ""
    try:
        p = urlsplit(value)
        if (
            p.scheme in {"https", "http"}
            and p.hostname
            and not (p.username or p.password)
        ):
            return value
    except ValueError:
        pass
    raise HTTPException(422, "证据与网站地址须为完整 HTTP(S) 链接")


def host(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def samples():
    return [
        dict(
            name=s["name"],
            country="马来西亚",
            website=s["website"],
            social=s["social"],
            evidence_url=s["url"],
            evidence=s["evidence"],
            next_action=s["next_action"],
            procurement="待核实",
            kind=s["kind"],
            notes=s["place"],
            checked="2026-11-21",
            source="已核验样例",
            contact="info@lrh.com.my" if s["name"] == "L&R Haulage" else "",
        )
        for s in SAMPLES
    ]


def discover(request):
    market = MARKETS.get(request.market, request.market)
    query = f"{market} {BUYER_TERMS[request.kind]} {request.keywords}".strip()
    if request.mode == "samples":
        result = []
        for row in samples():
            if market.lower() not in ("malaysia", "my", "全部", "all"):
                continue
            if request.kind not in ("待识别", row["kind"]) and not (
                request.kind == "维修厂" and row["kind"] == "维修及配件"
            ):
                continue
            if (
                request.keywords
                and request.keywords.casefold() not in " ".join(row.values()).casefold()
            ):
                continue
            result.append(row)
        return {"mode": request.mode, "query": query, "items": result}
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        raise HTTPException(503, "实时发现需要配置 BRAVE_API_KEY；可切换已核验样例。")
    try:
        r = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 12, "text_decorations": "false"},
            headers={"X-Subscription-Token": key},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("web", {}).get("results", [])
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(502, "实时搜索服务不可用，请稍后重试。") from exc
    items = []
    seen = set()
    for hit in results:
        url = str(hit.get("url", ""))
        if not url.startswith(("https://", "http://")):
            continue
        domain = host(url)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        title = str(hit.get("title", "")).strip() or domain
        snippet = str(hit.get("description", ""))[:1500]
        kind = "待识别"
        if re.search("workshop|truck repair|lorry repair|bengkel", snippet, re.I):
            kind = "维修厂"
        elif re.search("own fleet|our fleet|haulage operator", snippet, re.I):
            kind = "车队"
        # The hit can be a directory: never treat its domain as the company's verified website.
        items.append(
            dict(
                name=title[:200],
                country=request.market,
                website="",
                social="",
                evidence_url=url,
                evidence=snippet,
                kind=kind,
                procurement="待核实",
                notes="搜索结果；企业名称、经营地与官网待核对。",
                next_action="检查来源，确认企业身份、经营地及是否直接采购。",
                source="实时网页搜索",
                checked=utc()[:10],
            )
        )
    return {"mode": request.mode, "query": query, "items": items}


def save_company(db, data, source, checked=None):
    for field in ["website", "social", "evidence_url"]:
        valid_url(data[field])
    domain = host(data["website"])
    existing = db.execute(
        "SELECT id FROM companies WHERE domain=? AND domain<>''", (domain,)
    ).fetchone()
    if not existing:
        existing = db.execute(
            "SELECT id FROM companies WHERE lower(name)=lower(?) AND lower(country)=lower(?)",
            (data["name"], data["country"]),
        ).fetchone()
    if existing:
        db.execute("UPDATE companies SET saved=1 WHERE id=?", (existing["id"],))
        return one(db, "SELECT * FROM companies WHERE id=?", (existing["id"],))
    row = {
        **data,
        "domain": domain,
        "source": source,
        "saved": 1,
        "checked": checked or utc()[:10],
    }
    cols = list(row)
    ident = db.execute(
        f"INSERT INTO companies({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
        [row[k] for k in cols],
    ).lastrowid
    return one(db, "SELECT * FROM companies WHERE id=?", (ident,))
