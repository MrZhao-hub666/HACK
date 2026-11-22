import logging
import os
import re
from html import unescape
from time import sleep
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from .db import one, utc
from .markets import DISCOVERY_MARKET_TERMS

logger = logging.getLogger(__name__)

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
    "批发进口商": "commercial vehicle parts importer wholesaler",
    "经销代理商": "commercial vehicle parts distributor",
    "车桥厂": "commercial vehicle axle manufacturer purchasing",
    "OEM采购商": "commercial vehicle OEM supplier purchasing",
    "ODM采购商": "commercial vehicle ODM procurement",
    "车队": "haulage fleet own workshop",
    "维修厂": "heavy truck brake repair workshop",
    "维修及配件": "commercial truck workshop aftermarket spare parts",
    "配件门店": "commercial vehicle brake parts shop",
    "贸易商": "commercial vehicle parts trader",
    "渠道伙伴": "trucking industry association",
    "待识别": "truck fleet OR commercial truck workshop",
}
PARTS_EVIDENCE = re.compile(
    r"\b(?:spare|aftermarket|vehicle|truck|brake) parts\b|ersatzteil|fahrzeugteil|配件|零部件",
    re.I,
)
PARTS_TRADE = re.compile(
    r"\b(?:wholesal\w*|distribut(?:es?|or\w*|ion)|trade in|spare parts shop|online shop|"
    r"gro(?:ß|ss)handel\w*|handelsunternehmen|fahrzeugteilehandel|anbieter von ersatzteilen)\b"
    r"|\b(?:range of|supplier of)\s+[^.!?\n]{0,65}"
    r"\b(?:spare|aftermarket|vehicle|truck|brake) parts\b"
    r"|批发|经销",
    re.I,
)
DIRECT_PARTS_TRADE = re.compile(
    r"\bwe (?:offer|supply|sell)\s+[^.!?\n]{0,65}"
    r"\b(?:spare|aftermarket|vehicle|truck|brake) parts\b|\bwholesale (?:company|business)\b"
)
FLEET_EVIDENCE = re.compile(
    r"own fleet|our fleet|haulage (?:operator|fleet|services)|prime movers?|车队"
)
REPAIR_EVIDENCE = re.compile(
    r"\b(?:(?:truck|lorry) repair|(?:truck|lorry|commercial vehicle|hgv|repair|service|our) workshops?|bengkel)\b"
    r"|\b(?:lkw|nutzfahrzeug)[ -]?werkst(?:att|ätten)\b"
    r"|维修厂|修理厂"
)
MARKETS = {
    **DISCOVERY_MARKET_TERMS,
    "印尼": DISCOVERY_MARKET_TERMS["印度尼西亚"],
}


MARKET_ALIASES = {
    "my": "malaysia",
    "th": "thailand",
    "ph": "philippines",
    "br": "brazil",
    "mx": "mexico",
    "ae": "united arab emirates",
    "id": "indonesia",
    "de": "germany",
    "deutschland": "germany",
}
MARKET_QUERY_NAMES = {name.casefold(): name for name in MARKETS.values()}


def market_key(country):
    country = country.strip()
    return MARKET_ALIASES.get(
        country.casefold(), MARKETS.get(country, country).casefold()
    )


def market_query_name(country):
    return MARKET_QUERY_NAMES.get(market_key(country))


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


def company_domain(data):
    for field in ("website", "social", "evidence_url"):
        valid_url(data[field])
    return host(data["website"])


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


def search_credentials():
    for provider, variable in (("exa", "EXA_API_KEY"), ("brave", "BRAVE_API_KEY")):
        if key := os.getenv(variable, "").strip():
            return provider, key
    return None


def search_request(send, url, **kwargs):
    for attempt in range(2):
        try:
            response = send(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if (
                attempt
                or exc.response.status_code not in {408, 500, 502, 503, 504}
                or "retry-after" in exc.response.headers
            ):
                raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
            if attempt:
                raise
        sleep(0.35)


def public_search(query, *, domains=()):
    credentials = search_credentials()
    if not credentials:
        raise HTTPException(503, "实时搜索需要配置 EXA_API_KEY 或 BRAVE_API_KEY。")
    provider, key = credentials
    try:
        if provider == "exa":
            payload = {
                "query": query,
                "numResults": 10,
                "contents": {"highlights": True},
            }
            if domains:
                payload["includeDomains"] = list(domains)
            response = search_request(
                httpx.post,
                "https://api.exa.ai/search",
                json=payload,
                headers={"x-api-key": key},
                timeout=10,
            )
            results = response.json().get("results")
        else:
            if domains:
                scope = " OR ".join(f"site:{domain}" for domain in domains)
                query = f"({scope}) {query}" if len(domains) > 1 else f"{scope} {query}"
            response = search_request(
                httpx.get,
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": 12, "text_decorations": "false"},
                headers={"X-Subscription-Token": key},
                timeout=10,
            )
            results = response.json().get("web", {}).get("results", [])
        if not isinstance(results, list):
            raise ValueError("invalid results")
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        reason = (
            exc.response.status_code
            if isinstance(exc, httpx.HTTPStatusError)
            else type(exc).__name__
        )
        logger.warning("Public search failed: provider=%s reason=%s", provider, reason)
        raise HTTPException(502, "实时搜索服务不可用，请稍后重试。") from exc
    items = []
    for hit in results:
        if not isinstance(hit, dict):
            continue
        url = str(hit.get("url") or "")
        if not url or len(url) > 1400:
            continue
        try:
            valid_url(url)
        except HTTPException:
            continue
        description = hit.get("description") or ""
        highlights = hit.get("highlights")
        if provider == "exa" and isinstance(highlights, list):
            description = "\n".join(part for part in highlights if isinstance(part, str))
        items.append(
            {
                "title": str(hit.get("title") or "")[:200],
                "url": url,
                "description": str(description)[:1500],
            }
        )
    return items


def inferred_buyer_kind(title, evidence):
    text = unescape(re.sub("<[^>]+>", " ", f"{title} {evidence}")).casefold()
    has_parts = PARTS_EVIDENCE.search(text)
    if has_parts and DIRECT_PARTS_TRADE.search(text):
        return "贸易商"
    if FLEET_EVIDENCE.search(text):
        return "车队"
    if REPAIR_EVIDENCE.search(text):
        return "维修厂"
    if has_parts and PARTS_TRADE.search(text):
        return "贸易商"
    return "待识别"


def discover(request):
    market = market_query_name(request.market) or request.market
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
    results = public_search(query)
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
        # The hit can be a directory: never treat its domain as the company's verified website.
        items.append(
            dict(
                name=title[:200],
                country=request.market,
                website="",
                social="",
                evidence_url=url,
                evidence=snippet,
                kind=inferred_buyer_kind(title, snippet),
                procurement="待核实",
                notes="搜索结果；企业名称、经营地与官网待核对。",
                next_action="检查来源，确认企业身份、经营地及是否直接采购。",
                source="实时网页搜索",
                checked=utc()[:10],
            )
        )
    return {"mode": request.mode, "query": query, "items": items}


def matching_company(db, data):
    domain = host(data["website"])
    if domain:
        row = db.execute(
            "SELECT * FROM companies WHERE domain=%s AND domain<>''", (domain,)
        ).fetchone()
        if row:
            return row
    for row in db.execute(
        "SELECT * FROM companies WHERE lower(name)=lower(%s) ORDER BY id",
        (data["name"],),
    ):
        if market_key(row["country"]) == market_key(data["country"]):
            return row
    return None


def save_company(db, data, source, checked=None, owner=""):
    domain = company_domain(data)
    existing = matching_company(db, data)
    if existing:
        db.execute(
            "UPDATE companies SET saved=1,archived_at=coalesce(archived_at,%s) WHERE id=%s AND saved=0",
            (utc(), existing["id"]),
        )
        return one(db, "SELECT * FROM companies WHERE id=%s", (existing["id"],))
    row = {
        **data,
        "domain": domain,
        "owner": owner,
        "source": source,
        "saved": 1,
        "archived_at": utc(),
        "checked": checked or utc()[:10],
    }
    cols = list(row)
    ident = db.execute(
        f"INSERT INTO companies({','.join(cols)}) VALUES({','.join('%s' for _ in cols)}) RETURNING id",
        [row[k] for k in cols],
    ).fetchone()["id"]
    return one(db, "SELECT * FROM companies WHERE id=%s", (ident,))
