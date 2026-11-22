"""Connect authenticated sales inquiries to the catalogue service."""
import re
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.backend.app import main as catalogue
from src.backend.app import quotes
from src.backend.app.catalog import FIELDS
from .db import database
from .inbox import get_inquiry
from .quote_calculation import (
    NUMBER, ORDER, QuoteConfigurationError, calculate_material_quote, material_in,
    manual_price, normalize, pack_size, prices_by_material, quote_order_text, read_dimensions, read_order,
)

router = APIRouter()


class Selection(BaseModel):
    customer_words: str = Field(default="", max_length=3000)


class Draft(quotes.QuoteLine):
    spec_id: str = Field(min_length=1, max_length=180)
    request_key: UUID


def assistant_price(item, words, quantity, unit, *, preview=False):
    thickness = (item["thickness"] or "").split("/")
    disc = item["kind"] == "盘式"
    length = item["outer_arc"]
    if disc and (size := re.fullmatch(
        rf"\s*({NUMBER})\s*[x×*]\s*{NUMBER}(?:\s*[x×*]\s*{NUMBER})?\s*(?:mm|毫米)?\s*",
        normalize(item.get("size_raw") or ""),
    )):
        length = size[1]
    dimensions = {}
    for label, raw in zip(
        ("外弧", "宽度", "厚度1", "厚度2"),
        (length, item["width"], thickness[0], thickness[-1] if len(thickness) <= 2 else None),
    ):
        if raw and re.fullmatch(NUMBER, normalize(raw).strip()):
            dimensions[label] = normalize(raw).strip()
    latest = {}
    for index, text in enumerate(words):
        try:
            supplied = read_dimensions(text)
        except ValueError:
            if index == 0:
                raise
            continue
        for label, value in supplied.items():
            if value is not None:
                latest.setdefault(label, value)
    for label, value in latest.items():
        if label in dimensions and value != Decimal(dimensions[label]):
            return None, f"客户提供的{label}与目录记录不同，请先与客户核对尺寸。"
        dimensions.setdefault(label, str(value))

    request = quotes.Quote(
        spec_id=item["spec_id"], market=item["market"], quantity=quantity, unit=unit
    )
    with database() as db:
        quote = quotes.quote_preview(db, request)
    if quote["total"] is not None:
        try:
            prices = prices_by_material()
        except QuoteConfigurationError:
            prices = {}
        if prices:
            requested = next((key for text in words if (key := material_in(text, prices))), None)
            official = material_in(normalize(quote["material"]), prices)
            if requested and requested != official:
                return None, f"目录价目适用于{quote['material']}，请核对客户指定的材质和规格。"
        return {
            **{key: quote[key] for key in ("unit_price", "total", "currency", "quantity", "unit")},
            "material": quote["material"], "valid_until": quote.get("valid_until"), "basis": "目录价目",
        }, ""
    if not preview and (price := manual_price(words, unit)) is not None:
        return {
            "unit_price": format(price, ".2f"), "total": format(price * quantity, ".2f"),
            "currency": "CNY", "quantity": quantity, "unit": unit, "basis": "已核单价试算",
        }, ""
    missing = [label for label in ("外弧", "宽度", "厚度1", "厚度2") if label not in dimensions]
    if item["kind"] != "鼓式" and missing:
        names = ["长度" if disc and label == "外弧" else label for label in missing]
        return None, (
            "目录缺少" + "、".join(names) +
            f"（毫米）。如已核对单价，可输入「单价 35 元/{unit}」计算合计。"
        )

    pieces = 1 if unit == "片" else pack_size(words, unit)
    if pieces is None:
        return None, f"请补充每{unit}的片数，例如「每{unit} 4 片」。"
    if quantity * pieces > 100000000:
        raise ValueError("折算后片数不能超过一亿。")

    prices = prices_by_material()
    material = next((key for text in words if (key := material_in(text, prices))), None)
    if not material:
        return None, "请确认客户需要的材质。可试算的材料有" + "、".join(name for name, _ in prices.values()) + "。"

    if missing:
        return None, "请用毫米补充" + "、".join(missing) + "，以便试算。"
    estimate = calculate_material_quote(dimensions, prices[material], quantity * pieces)
    return {
        "unit_price": format(Decimal(estimate["unit_price"]) * pieces, ".2f"),
        "total": estimate["total"], "material": estimate["material"],
        "currency": "CNY", "quantity": quantity, "unit": unit,
        "basis": "盘片目录尺寸试算" if disc else "预设材料价试算",
    }, ""


def customer_reply(item, quote, follow_up):
    if item is None:
        return follow_up
    title = item.get("code") or item.get("name") or item["spec_id"]
    reply = f"根据您提供的信息，目录对应型号为 {title}。"
    if quote and quote["basis"] == "目录价目":
        if quote.get("unit_only"):
            return reply + f"单价 {quote['currency']} {quote['unit_price']}/{quote['unit']}。" + follow_up
        reply += (
            f"材质为{quote['material']}，数量 {quote['quantity']}{quote['unit']}，"
            f"单价 {quote['currency']} {quote['unit_price']}/{quote['unit']}，"
            f"合计 {quote['currency']} {quote['total']}。"
        )
        if quote["valid_until"]:
            reply += f"报价有效至 {quote['valid_until']}。"
        return reply
    return reply + follow_up


@router.post("/api/sales-assistant")
def sales_assistant(req: catalogue.Inquiry):
    words = [
        normalize(turn.text.replace("，", "、"))
        for turn in reversed(req.turns) if turn.role == "customer"
    ]
    turns = [
        turn.model_copy(update={"text": clean})
        for turn in req.turns
        if (clean := ORDER.sub(" ", quote_order_text(turn.text)).strip())
    ]
    if not any(turn.role == "customer" for turn in turns):
        question = "请提供旧件编号、车型或车桥信息。"
        return {"question": question, "reply": question, "mode": "", "items": [], "count": 0,
                "confirmed": False, "quote": None, "fields": FIELDS}
    result = catalogue.analyze(req.model_copy(update={"turns": turns, "use_model": True}))
    items = result["items"]
    item = items[0] if len(items) == 1 else None
    clues = result["clues"]
    identified = bool(clues.get("number") or (
        (clues.get("vehicle") or clues.get("axle"))
        and sum(bool(clues.get(field)) for field in ("width", "thickness", "holes")) >= 2
    ))
    confirmed = bool(item and not item["conflict"] and not item["missing"]
                     and identified
                     and item["status"] in ("目录记录", "目录转录", "企业已核"))
    question = result["question"]
    if result["routing"]["status"] == "conflict":
        question = "您提供的编号与选型条件有出入。请核对旧件完整编号、采购版本和盘鼓类型。"
        if clues.get("number") and clues.get("market"):
            market = clues["market"]
            prefixes = result["routing"]["matched_prefixes"]
            other_market = "外贸" if market == "国内" else "国内"
            if prefixes and all(prefix.startswith("F" if market == "国内" else "D") for prefix in prefixes):
                question = (
                    f"编号 {clues['number']} 对应{other_market}目录，但您需要{market}版。"
                    f"请提供{market}版旧件编号或包装照片，以便核对。"
                )
    elif item and clues.get("holes") and item.get("holes") and "holes" in item["conflict"]:
        question = (
            f"编号 {clues['number']} 对应的目录规格为 {item['holes']} 孔，您需要的是 {clues['holes']} 孔。"
            "请核对旧件上的编号和孔数，或提供旧件照片。"
        )
    answer = {
        "question": question, "reply": question, "items": items[:4], "count": result["count"],
        "mode": result["mode"], "confirmed": confirmed, "quote": None, "fields": FIELDS,
    }
    if not confirmed:
        if item and (not identified or item["status"] not in ("目录记录", "目录转录", "企业已核")):
            answer["reply"] = answer["question"] = "请确认您现用的旧件编号或包装标称规格。"
        return answer
    follow_up = "请问您需要多少，按片、套还是件采购？"
    answer["question"] = follow_up
    try:
        for text in words:
            quantity, unit = read_order(quote_order_text(text))
            if quantity is not None:
                if quantity > 100000000:
                    raise ValueError("请核对采购数量，单次最多一亿。")
                answer["quote"], answer["question"] = assistant_price(item, words, int(quantity), unit)
                follow_up = (
                    "请问您需要什么材质？"
                    if answer["question"].startswith("请确认客户需要的材质")
                    else "这批货的价格还需核实。"
                )
                if answer["question"].startswith("请补充每"):
                    follow_up = f"请问您需要的规格每{unit}有几片？"
                break
        else:
            preview, question = assistant_price(item, words, 1, "片", preview=True)
            if preview:
                answer["quote"] = {**preview, "unit_only": True}
            elif not question.startswith("请确认客户需要的材质"):
                answer["question"] = question
    except ValueError as exc:
        answer["question"] = str(exc)
        follow_up = str(exc)
    except QuoteConfigurationError as exc:
        answer["question"] = str(exc)
        follow_up = "这批货的价格还需核实。"
    if answer["question"].endswith("请先与客户核对尺寸。"):
        follow_up = "您提供的尺寸与目录记录有出入，请核对旧件标称尺寸。"
        item = None
        answer["confirmed"] = False
    answer["reply"] = customer_reply(item, answer["quote"], follow_up)
    if item is not None and any(re.search(r"\bcarton\s+size\b|外箱尺寸|包装尺寸", text) for text in words):
        answer["reply"] += "外箱尺寸还需核实。"
    return answer


@router.post("/api/inquiries/{ident}/selection")
def select(ident: int, req: Selection):
    with database() as db:
        get_inquiry(db, ident)
        rows = db.execute("""
            SELECT role, text FROM (
                SELECT 'customer' AS role, body AS text, at, id FROM messages WHERE inquiry_id=%s
                UNION ALL
                SELECT 'sales', detail, at, id FROM history WHERE inquiry_id=%s AND action='登记人工回复'
            ) AS conversation WHERE trim(text)<>'' ORDER BY at DESC, role DESC, id DESC LIMIT 30
        """, (ident, ident)).fetchall()
    turns = [{"role": row["role"], "text": row["text"][i:i+3000]}
             for row in reversed(rows) for i in range(0, len(row["text"]), 3000)]
    if words := req.customer_words.strip():
        turns.append({"role": "customer", "text": words})
    if not any(t["role"] == "customer" for t in turns[-30:]):
        raise HTTPException(422, "请先录入客户原话或补充旧件信息")
    return catalogue.analyze(catalogue.Inquiry(turns=turns[-30:]))


@router.post("/api/inquiries/{ident}/selection/quotes")
def create_quote(ident: int, req: Draft):
    with database(True) as db:
        get_inquiry(db, ident)
        workspace = db.execute("SELECT value FROM cursors WHERE name='selection-workspace'").fetchone()["value"]
        quote = quotes.save_quote(db, quotes.Quote(**req.model_dump(), inquiry_id=ident, workspace=workspace))
        db.execute("INSERT INTO inquiry_quotes(inquiry_id,quote_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (ident,quote["id"]))
        return quote


@router.get("/api/inquiries/{ident}/selection/quotes")
def prior_quotes(ident: int):
    with database() as db:
        get_inquiry(db, ident)
        rows = db.execute("""
            WITH RECURSIVE linked(id) AS (
                SELECT %s::integer UNION SELECT i.id FROM inquiries i JOIN linked l ON i.merged_into=l.id
            )
            SELECT q.id,q.snapshot FROM linked JOIN inquiry_quotes k ON k.inquiry_id=linked.id
            JOIN quote_draft q ON q.id=k.quote_id ORDER BY q.id DESC LIMIT 25
        """, (ident,)).fetchall()
    return [dict(id=row["id"], **row["snapshot"]) for row in rows]


@router.get("/api/selection/media/{kind}/{key:path}")
def image(kind: Literal["photo", "page", "observation", "domestic-picture", "evidence"], key: str):
    readers = {"photo": catalogue.photo, "page": catalogue.source_page, "observation": catalogue.source_row,
               "domestic-picture": catalogue.domestic_picture}
    if kind == "evidence":
        if key not in {"8", "13"}:
            raise HTTPException(404)
        return catalogue.evidence(int(key))
    return readers[kind](key)
