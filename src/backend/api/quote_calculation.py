"""Parse and calculate a single material quote using the local price list."""
import json
import re
import unicodedata
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("quote_config.json")
NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
COUNT = rf"(?:[+-]?[0-9]{{1,3}}(?:,[0-9]{{3}})+|{NUMBER})"
DIMENSION_UNIT = r"毫米|厘米|公分|公尺|英寸|片|套|件|箱|寸|米|[a-z]+"
MEASUREMENT = rf"({NUMBER})(?![0-9.]|,\d)\s*({DIMENSION_UNIT})?"
RANGE = rf"\s*[/~–—至到-]\s*{NUMBER}"
ASSIGNMENT = r"\s*(?:为|是|=|:)?\s*"
DIMENSIONS = {
    "外弧": r"外弧(?:长(?:度)?)?",
    "宽度": r"宽度?",
    "厚度1": r"厚度\s*(?:1|一)(?![0-9.])|第一端厚度",
    "厚度2": r"厚度\s*(?:2|二)(?![0-9.])|第二端厚度",
}
CENT = Decimal("0.01")
MATERIAL_ALIASES = {
    "无石棉有机": "无石棉", "nao": "无石棉",
    "陶瓷": "陶瓷基", "无铜陶瓷基": "无铜陶瓷",
    "玻璃纤维增强": "玻纤增强", "芳纶纤维增强": "芳纶增强",
}


class QuoteConfigurationError(RuntimeError):
    pass


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def material_entries(entries) -> dict[str, tuple[str, Decimal]]:
    prices = {}
    for name, price in entries:
        key = normalize(name).strip()
        if not key or key in prices or not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise ValueError
        prices[key] = (name.strip(), price)
    return prices


def prices_by_material() -> dict[str, tuple[str, Decimal]]:
    try:
        prices = json.loads(
            CONFIG_PATH.read_text(encoding="utf-8"),
            parse_int=Decimal,
            parse_float=Decimal,
            object_pairs_hook=material_entries,
        )
        if not isinstance(prices, dict) or not prices:
            raise ValueError
        return prices
    except (OSError, DecimalException, ValueError) as exc:
        raise QuoteConfigurationError("报价配置暂不可用，请联系维护人员") from exc


def single_value(matches, label, units) -> Decimal | None:
    result = None
    for number, unit, alternate in matches:
        if alternate:
            raise ValueError(f"请给出一个确定的{label}")
        if unit not in units:
            raise ValueError(f"请用{units[-1]}填写{label}")
        value = Decimal(number.replace(",", ""))
        if value <= 0:
            raise ValueError(f"{label}须大于 0")
        if result is not None and value != result:
            raise ValueError(f"发现多个不同的{label}，请确认本次使用的数值")
        result = value
    return result


def read_dimensions(text: str) -> dict[str, Decimal | None]:
    matches = {
        label: re.findall(rf"(?:{field}){ASSIGNMENT}{MEASUREMENT}({RANGE})?", text)
        for label, field in DIMENSIONS.items()
    }
    for first, unit1, second, unit2, alternate in re.findall(
        rf"厚度{ASSIGNMENT}{MEASUREMENT}\s*/\s*{MEASUREMENT}({RANGE})?",
        text,
    ):
        matches["厚度1"].append((first, unit1 or unit2, alternate))
        matches["厚度2"].append((second, unit2 or unit1, alternate))
    return {
        label: single_value(values, label, ("", "mm", "毫米"))
        for label, values in matches.items()
    }


def material_in(text, prices):
    names = {name: name for name in prices}
    names.update({alias: name for alias, name in MATERIAL_ALIASES.items()
                  if name in prices and alias not in prices})
    if "无石棉" in prices:
        names.update({f"无石棉{name}": key for name, key in list(names.items())
                      if key != "无石棉" and f"无石棉{name}" not in names})
    if not names:
        return None
    names_pattern = "|".join(
        rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])" if name.isascii() else re.escape(name)
        for name in sorted(names, key=len, reverse=True)
    )
    materials = {
        names[match[0]] for match in re.finditer(names_pattern, text)
        if not re.search(r"(?:非|不要|不选|不用|不是)\s*$", text[:match.start()])
    }
    if len(materials) > 1:
        raise ValueError("发现多个预设材料，请确认本次使用的材料")
    return next(iter(materials), None)


ORDER = re.compile(rf"(?<![a-z0-9_./,+-])({COUNT})({RANGE})?\s*(片|套|件|箱|组|pcs\b|pieces?\b|sets?\b|units?\b)", re.I)
ORDER_UNITS = {"pcs": "片", "piece": "片", "pieces": "片", "set": "套", "sets": "套", "unit": "件", "units": "件"}
PACK_SIZE = re.compile(rf"(?:每|一)(套|件|箱|组)\s*(?:有|含|装|为|是|[:=])?\s*({NUMBER})(?![\d.])\s*片")
MANUAL_PRICE = re.compile(
    rf"(?:已核(?:准|对)?|确认)?单价{ASSIGNMENT}({NUMBER})(?![\d.])\s*(?:元|人民币|cny)\s*[/每]\s*(片|套|件|箱|组)",
    re.I,
)


def quote_order_text(text):
    return MANUAL_PRICE.sub(" ", PACK_SIZE.sub(" ", unicodedata.normalize("NFKC", text.replace("，", "、"))))


def pack_size(words, unit):
    for text in words:
        values = {Decimal(count) for package, count in PACK_SIZE.findall(text) if package == unit}
        if values:
            if len(values) != 1:
                raise ValueError(f"请确认每{unit}的片数。")
            count = values.pop()
            if count != count.to_integral_value() or not 1 <= count <= 10000:
                raise ValueError(f"每{unit}片数须为 1 到 10000 的整数。")
            return int(count)
    return None


def manual_price(words, unit):
    for text in words:
        prices = {(Decimal(value), priced_unit) for value, priced_unit in MANUAL_PRICE.findall(text)}
        if prices:
            if len(prices) != 1:
                raise ValueError("请确认本次使用的单价。")
            value, priced_unit = prices.pop()
            if priced_unit != unit:
                raise ValueError(f"请按本次采购单位填写单价，单位为元/{unit}。")
            if not 0 < value <= 100000000 or value != value.quantize(CENT):
                raise ValueError("单价须大于 0 且最多保留两位小数。")
            return value
    return None


def read_order(text):
    matches = [
        (number, ORDER_UNITS.get(unit, unit), alternate)
        for number, alternate, unit in ORDER.findall(text)
    ]
    if not matches:
        return None, None
    unit = matches[0][1]
    quantity = single_value(
        matches, "数量", (unit,),
    )
    if quantity != quantity.to_integral_value():
        raise ValueError("数量须为整数")
    return quantity, unit


def calculate_quote(question: str) -> dict:
    prices = prices_by_material()
    text = normalize(question.replace("，", "、"))
    dimensions = read_dimensions(text)
    material_key = material_in(text, prices)
    quantity, unit = read_order(text)
    if unit and unit != "片":
        raise ValueError("请用片填写数量")
    missing = [label for label, value in dimensions.items() if value is None]
    if material_key is None:
        missing.append("材料名称")
    answer = {"missing": missing, "materials": [name for name, _ in prices.values()], "quote": None}
    if missing:
        return answer

    answer["quote"] = calculate_material_quote(dimensions, prices[material_key], quantity)
    return answer


def calculate_material_quote(dimensions, material_price, quantity):
    dimensions = {label: Decimal(dimensions[label]) for label in DIMENSIONS}
    for label, value in dimensions.items():
        if value <= 0:
            raise ValueError(f"{label}须大于 0")
    arc, width, thickness1, thickness2 = dimensions.values()
    material, price_per_tonne = material_price
    try:
        weight_kg = arc * width * (thickness1 + thickness2) / 2 * Decimal("1.15") * Decimal("2.2") / 1_000_000
        unit_price = (weight_kg * price_per_tonne / 1_000).quantize(CENT, rounding=ROUND_HALF_UP)
        total = (unit_price * quantity).quantize(CENT) if quantity is not None else None
    except DecimalException as exc:
        raise ValueError("数值超出可核算范围，请核对尺寸、材料价格和片数") from exc

    return {
        "material": material,
        "price_per_tonne": format(price_per_tonne, "f"),
        "dimensions": {label: format(value, "f") for label, value in dimensions.items()},
        "unit_price": format(unit_price, "f"),
        "quantity": format(Decimal(quantity).to_integral_value(), "f") if quantity is not None else None,
        "total": format(total, "f") if total is not None else None,
    }
