from uuid import uuid4

from psycopg.types.json import Jsonb

from src.backend.api import quote_calculation, selection
from src.backend.app.match import Clues, Turn, local_clues, match
from src.backend.app.routing import route_inquiry
from .test_workbench import event


def test_copilot_quote_uses_dimensions_and_configured_tonne_price(client, monkeypatch, tmp_path):
    route = "/api/copilot/quote"
    question = "外弧 ２００mm，宽度 100 mm，厚度 18/22，半金属，100 片多少钱？"
    response = client.post(route, json={"question": question})
    assert response.is_success
    quote = response.json()["quote"]
    assert quote["unit_price"] == "12.14"
    assert quote["total"] == "1214.00"
    assert quote["price_per_tonne"] == "12000"

    for material, expected, total in (
        ("无石棉半金属", "半金属", "1214.00"),
        ("陶瓷", "陶瓷基", "2226.00"),
        ("无铜陶瓷基", "无铜陶瓷", "2530.00"),
        ("芳纶纤维增强", "芳纶增强", "2732.00"),
        ("NAO", "无石棉", "2024.00"),
    ):
        response = client.post(route, json={"question": question.replace("半金属", material)})
        assert response.is_success, response.text
        trial = response.json()["quote"]
        assert trial["material"] == expected and trial["total"] == total
    assert client.post(route, json={"question": question.replace("半金属", "陶瓷基或半金属")}).status_code == 422

    question_with_units = "外弧是200毫米，宽100mm，厚度18毫米/22mm，半金属，1,200片"
    quote = client.post(route, json={"question": question_with_units}).json()["quote"]
    assert quote["quantity"] == "1200"
    assert quote["total"] == "14568.00"

    response = client.post(route, json={"question": "外弧 200，宽度 100，怎么报价？"})
    assert response.json()["missing"] == ["厚度1", "厚度2", "材料名称"]
    assert response.json()["quote"] is None
    for incorrect in (
        question.replace("100 片", "100 套"),
        question.replace("100 mm", "100 cm"),
        question.replace("100 mm", "-100 mm"),
        question.replace("２００mm", "200 到 300 mm"),
        question.replace("100 片", "100-200 片"),
        question.replace("100 mm", "100片"),
        question + " 宽度 110",
    ):
        assert client.post(route, json={"question": incorrect}).status_code == 422

    prices = tmp_path / "prices.json"
    prices.write_text('{"半金属": 10000}', encoding="utf-8")
    monkeypatch.setattr(quote_calculation, "CONFIG_PATH", prices)
    response = client.post(route, json={"question": question})
    assert response.json()["quote"]["unit_price"] == "10.12"
    for invalid in ('[["半金属", 10000]]', '{"半金属": 10000, "半金属": 20000}', '{"半金属": "10000"}'):
        prices.write_text(invalid, encoding="utf-8")
        assert client.post(route, json={"question": question}).status_code == 503

    client.cookies.clear()
    assert client.post(route, json={"question": question}).status_code == 401


def test_catalogue_refresh_keeps_running_after_a_workbook_error(monkeypatch):
    catalogue = selection.catalogue
    monkeypatch.setattr(catalogue, "state", {"foreign_revision": "last-foreign"})

    def locked_workbook():
        raise PermissionError

    monkeypatch.setattr(catalogue, "sync_foreign", locked_workbook)
    monkeypatch.setattr(catalogue.domestic, "synchronize", lambda: "new-domestic")
    completed = []
    monkeypatch.setattr(catalogue, "sync", lambda: completed.append("知识库已同步"))
    catalogue.refresh()

    assert catalogue.state["foreign_revision"] == "last-foreign"
    assert catalogue.state["domestic_revision"] == "new-domestic"
    assert "外贸目录文件已锁定" in catalogue.state["sync"]
    assert completed == ["知识库已同步"]


def test_oem_in_customer_wording_resolves_exact_catalogue_partition():
    index = [{
        "spec_id": "FJG0009",
        "references": [{"scheme": "oe_ref", "number": "MC828513"}],
        **dict.fromkeys(("brand", "vehicle", "axle", "name", "series", "fit_notes")),
    }]
    inquiry = "客户要买的刹车片是给出口日本的车用的，OEM是MC828513，帮我推荐型号"
    turns = [Turn(role="customer", text=inquiry), Turn(role="customer", text="鼓状")]
    clues = local_clues(turns, index)
    route = route_inquiry(turns, index, clues)
    assert clues.scheme == "oe_ref" and clues.number == "MC828513"
    assert route["status"] == "resolved"
    assert route["search_prefixes"] == ["FJG"]
    assert route["slots"]["country"]["source"] == "目录编码"
    assert route["slots"]["kind"]["evidence"] == "鼓状"

    turns = [Turn(role="customer", text=inquiry.replace("MC828513", "ZZ00000"))]
    route = route_inquiry(turns, index, local_clues(turns, index))
    assert route["status"] == "no_catalog" and route["search_prefixes"] == []
    assert "ZZ00000" in route["question"]


def test_oem_and_holes_survive_model_number_types_and_market_correction():
    index = [{
        "spec_id": "FJG0007", "holes": "10",
        "references": [{"scheme": "oe_ref", "number": "MC809750"}],
        **dict.fromkeys(("brand", "vehicle", "axle", "name", "series", "fit_notes")),
    }]
    turns = [Turn(role="customer", text=text) for text in (
        "用户的卡车要出口日本，OEM的编号是MC809750，怎么推荐",
        "客户需要孔数6孔的",
    )]
    from_model = Clues.model_validate_json('{"holes": 6}')
    from_rules = local_clues(turns, index)
    for clues in (from_model, from_rules):
        route = route_inquiry(turns, index, clues)
        assert clues.number == "MC809750" and clues.holes == "6"
        assert route["search_prefixes"] == ["FJG"]
        corrected = [*turns, Turn(role="customer", text="用于国内")]
        route = route_inquiry(corrected, index, clues)
        assert route["status"] == "conflict" and route["search_prefixes"] == []
        assert clues.number == "MC809750"


def test_sales_assistant_prices_a_single_discussed_specification(client, monkeypatch):
    item = {
        "spec_id": "DCG0001", "market": "国内", "kind": "鼓式", "status": "目录转录",
        "outer_arc": "200", "width": "100", "thickness": "18/22",
        "conflict": [], "missing": [],
    }

    def analyze(req):
        assert req.use_model
        assert all("1,200片" not in turn.text for turn in req.turns)
        return {"items": [item], "count": 1, "question": "请补充信息。",
                "mode": "模型提取", "clues": {"number": "DCG0001"}, "routing": {"status": "resolved"}}

    monkeypatch.setattr(selection.catalogue, "analyze", analyze)
    monkeypatch.setattr(selection.quotes, "quote_preview", lambda *_: {"total": None})
    route = "/api/sales-assistant"
    turns = [{"role": "customer", "text": "客户旧件是 DCG0001"}]
    assert "多少" in client.post(route, json={"turns": turns}).json()["question"]
    turns.append({"role": "customer", "text": "半金属"})
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"]["unit_only"] and answer["quote"]["unit_price"] == "12.14"
    assert "多少" in answer["reply"] and "12.14" not in answer["reply"]
    turns.pop()
    turns.append({"role": "customer", "text": "半金属，1,200片"})
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["confirmed"]
    assert answer["quote"]["total"] == "14568.00"
    assert answer["quote"]["basis"] == "预设材料价试算"
    assert "14568.00" not in answer["reply"] and "价格还需核实" in answer["reply"]

    turns[-1]["text"] = "半金属，100套"
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"] is None and "每套" in answer["reply"]
    turns.append({"role": "customer", "text": "每套4片"})
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"]["unit_price"] == "48.56"
    assert answer["quote"]["total"] == "4856.00"
    assert answer["quote"]["unit"] == "套" and answer["quote"]["quantity"] == 100
    assert "4856.00" not in answer["reply"]
    turns.pop()

    item["kind"] = "盘式"
    item["outer_arc"] = None
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"] is None and "单价 35 元/套" in answer["question"]
    turns.append({"role": "customer", "text": "已核单价35.50元/套"})
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"]["total"] == "3550.00"
    assert answer["quote"]["basis"] == "已核单价试算" and "3550.00" not in answer["reply"]
    turns[-1]["text"] = "单价 35.50 元/片"
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"] is None and "元/套" in answer["question"]
    turns.pop()
    turns[-1]["text"] = "半金属，1,200片"
    item["kind"] = "鼓式"
    item["outer_arc"] = "200"

    monkeypatch.setattr(selection.quotes, "quote_preview", lambda *_: {
        "total": "24000", "unit_price": "20", "currency": "CNY", "quantity": 1200,
        "unit": "片", "material": "无石棉", "valid_until": "2030-12-31",
    })
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"] is None and "无石棉" in answer["question"]
    turns[-1]["text"] = "无石棉，1,200片"
    answer = client.post(route, json={"turns": turns}).json()
    assert answer["quote"]["total"] == "24000"
    assert answer["quote"]["basis"] == "目录价目"
    assert "DCG0001" in answer["reply"] and "CNY 24000" in answer["reply"]
    assert "2030-12-31" in answer["reply"]

    turns[-1]["text"] = "无石棉，1,200片，外弧210mm"
    answer = client.post(route, json={"turns": turns}).json()
    assert not answer["confirmed"] and answer["quote"] is None
    assert "尺寸有出入" in answer["reply"] or "标称尺寸" in answer["reply"]

    item["conflict"] = ["thickness"]
    answer = client.post(route, json={"turns": turns}).json()
    assert not answer["confirmed"]
    assert answer["quote"] is None


def test_sales_assistant_quotes_wva_29289_after_local_fallback(client, monkeypatch):
    part = {
        **dict.fromkeys(("brand", "vehicle", "axle", "series", "fit_notes", "outer_arc")),
        "spec_id": "FCP0052", "code": "GY-052", "name": "GY-052", "kind": "盘式",
        "market": "外贸", "status": "目录记录", "width": "78.1", "thickness": "26/26",
        "size_raw": "181*78.1*26", "references": [{"scheme": "wva", "number": "29289"}],
    }
    photo_group = {**part, "spec_id": "IMG-29289", "name": "29289", "references": []}

    def analyze(req):
        clues = local_clues(req.turns, [part, photo_group])
        assert clues.name == "29289"
        result = match(req.turns, [part], False, extracted=(clues, "本地检索"))
        return {**result, "routing": {"status": "resolved"}}

    monkeypatch.setattr(selection.catalogue, "analyze", analyze)
    monkeypatch.setattr(selection.quotes, "quote_preview", lambda *_: {"total": None})
    turns = [{"role": "customer", "text": text} for text in (
        "Please quote WVA 29289 for our truck parts range and confirm carton size",
        "1000片", "半金属材质的",
    )]
    answer = client.post("/api/sales-assistant", json={"turns": turns}).json()
    assert answer["confirmed"] and answer["items"][0]["spec_id"] == "FCP0052"
    assert answer["quote"]["unit_price"] == "11.16" and answer["quote"]["total"] == "11160.00"
    assert answer["quote"]["basis"] == "盘片目录尺寸试算"
    assert "外箱尺寸还需核实" in answer["reply"]


def test_handoff_preserves_speakers_and_skips_notes(client, monkeypatch):
    ident = event(client, body="FMSI 4702a").json()["inquiry_id"]
    base = f"/api/inquiries/{ident}"
    assert client.post(base + "/notes", json={"text": "内部判断：WVA 29174"}).is_success
    assert client.post(base + "/reply", json={"text": "是否出口？"}).is_success
    captured = []
    def match(req):
        captured.extend(t.model_dump() for t in req.turns)
        return {"count": 1}
    monkeypatch.setattr(selection.catalogue, "analyze", match)
    assert client.post(base + "/selection", json={"customer_words": "出口"}).json() == {"count": 1}
    assert captured == [
        {"role": "customer", "text": "FMSI 4702a"},
        {"role": "sales", "text": "是否出口？"},
        {"role": "customer", "text": "出口"},
    ]
    assert client.post("/api/inquiries/99999/selection", json={}).status_code == 404
    client.cookies.clear()
    assert client.post(base + "/selection", json={}).status_code == 401


def test_quote_workspace_and_merged_inquiries(client, monkeypatch):
    source = event(client).json()["inquiry_id"]
    target = event(client, "e2", thread_key="other", sender="Other").json()["inquiry_id"]
    def store(db, req):
        row = db.execute("INSERT INTO quote_draft(snapshot,request_key) VALUES(%s,%s) RETURNING id",
                         (Jsonb({"spec_id": req.spec_id}), req.request_key)).fetchone()
        return dict(id=row["id"], spec_id=req.spec_id)
    monkeypatch.setattr(selection.quotes, "save_quote", store)
    draft = {"spec_id":"FAG0001", "quantity":5, "unit":"套", "request_key":str(uuid4())}
    assert client.post(f"/api/inquiries/{source}/selection/quotes", json=draft).is_success
    assert client.post(f"/api/inquiries/{source}/merge", json={"target_id":target}).is_success
    result = client.get(f"/api/inquiries/{target}/selection/quotes")
    assert result.is_success
    assert result.json() == [{"id":1,"spec_id":"FAG0001"}]
