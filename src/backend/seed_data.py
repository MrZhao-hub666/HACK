"""Build the initial catalogue snapshot from the supplied source package."""
import csv
import json
import sys
from hashlib import sha256
from pathlib import Path

from app.catalog import DOCS, PACK, order_specs

def snapshot():
    specs, media = {}, []
    with (DOCS / "materials/gys-page08.tsv").open(encoding="utf-8") as stream:
        rows = csv.reader(stream, delimiter="\t")
        next(rows)
        for row in rows:
            if not row:
                continue
            fields = ("code","wva","bfmc","fmsi","outer_arc","inner_arc","width","thickness","holes","rivet","brand")
            item = dict(zip(fields, row))
            key = item["code"]
            specs[key] = dict(item, spec_id=key, name=key, series="GYS（编号组）",
                              kind="鼓式", status="目录记录", source="kooying catalog.pdf · PDF 8 / "+key)
    cards = [
        ("EQ1094前","EQ1094","前","202","130","6",["14.5","16","18"]),
        ("EQ1094后","EQ1094","后","201","180","10",["14.5","16","18"]),
        ("EQ1094加宽","EQ1094",None,"211","220","12",["14.5"]),
        ("东风6.5T前","东风6.5T","前","202","150","6",["14.5","16"]),
        ("3T王前","3T王","前","154","120","6",["13.5","14.5"]),
        ("3T王后","3T王","后","158","150","6",["13.5","14.5"]),
    ]
    for i,(name,vehicle,pos,a,c,holes,thicknesses) in enumerate(cards,1):
        for j,d in enumerate(thicknesses,1):
            key = f"CAT13-{i:02}-{j:02}"
            specs[key] = dict(spec_id=key, name=name, vehicle=vehicle, position=pos, outer_arc=a,
                width=c, holes=holes, thickness=d, kind="鼓式", series="东风系列", brand="东风",
                status="目录记录", source=f"kooying catalog.pdf · PDF 13 / {name} / {a}×{c}×{d}")
    for path in sorted(PACK.rglob("*")):
        if path.suffix.lower() not in {".jpg",".jpeg",".png"}:
            continue
        rel = path.relative_to(PACK)
        name = path.parent.name
        kind = "鼓式" if rel.parts[0].startswith("鼓式") else "盘式"
        shared = any(x in str(rel) for x in ("喷码样板","宣传图","/样板/","\\样板\\","29115，29148","5200、5300"))
        key = None
        if name == "19932斯堪尼亚":
            key = "GYS-067"
        elif not shared:
            folder = rel.parent.as_posix()
            key = "IMG-"+sha256(folder.encode()).hexdigest()[:12].upper()
            specs.setdefault(key, dict(spec_id=key, name=name, kind=kind,
                status="照片组待核",source=folder))
        media.append(dict(spec_id=key, path=rel.as_posix(), label=path.stem))
    # Identical names alone cannot establish equivalence. Require the entire
    # album's content and product category to match before folding source copies.
    by_group = {}
    for picture in media:
        key = picture["spec_id"]
        if key and key.startswith("IMG-"):
            by_group.setdefault(key, []).append(sha256((PACK/picture["path"]).read_bytes()).hexdigest())
    canonical, aliases = {}, {}
    for key, hashes in by_group.items():
        item = specs[key]
        signature = (item["kind"],item["name"],tuple(sorted(hashes)))
        original = canonical.setdefault(signature,key)
        if original != key:
            aliases[key] = original
            del specs[key]
    for picture in media:
        picture["spec_id"] = aliases.get(picture["spec_id"],picture["spec_id"])
    return {"产品规格":order_specs(specs.values()),"图片索引":media}

if __name__ == "__main__":
    Path(sys.argv[1]).write_text(json.dumps(snapshot(),ensure_ascii=False),encoding="utf-8")

