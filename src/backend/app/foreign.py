"""Foreign brake lining catalogue, in the order of the printed English catalogue."""
import json
import re
from collections import Counter, defaultdict
from itertools import groupby

from .archive import MANIFEST
from .catalog import DOCS

BOOK = DOCS / "外贸刹车片国别目录.xlsx"
COUNTRIES = {
    "E": ("欧洲", "europe", ["wva", "bfmc"]),
    "A": ("美国", "america", ["fmsi"]),
    "J": ("日本", "japan", ["oem"]),
    "C": ("中国", "china", ["item", "wva"]),
    "K": ("韩国", "korea", ["item"]),
    "N": ("无国别", "unspecified", ["wva", "bfmc"]),
}
SECTIONS = dict(EUROPEAN="E", AMERICAN="A", JAPANESE="J", CHINESE="C", KOREA="K", EXISTING="N")

def canonical_id(value):
    return "FN"+value[2:] if re.fullmatch(r"FU[GP]\d{4}",value) else value

def country_candidates(rows, country):
    if not country:
        return rows
    labels={value[0]:code for code,value in COUNTRIES.items()}
    labels["欧盟"]="E"
    text=country.strip()
    scope=labels.get(text,text.upper())
    return [r for r in rows if r.get("country_code") in (scope,"N")]

def migrate_country_ids(conn):
    if not conn.execute("SELECT 1 FROM foreign_catalog.source WHERE part_id LIKE 'FU%' LIMIT 1").fetchone():
        return
    conn.execute("""ALTER TABLE foreign_catalog.unspecified
        DROP CONSTRAINT unspecified_part_id_check,
        DROP CONSTRAINT unspecified_part_id_fkey,
        ADD FOREIGN KEY (part_id) REFERENCES foreign_catalog.source(part_id) ON UPDATE CASCADE""")
    conn.execute("UPDATE foreign_catalog.source SET part_id='FN'||substr(part_id,3) WHERE part_id LIKE 'FU%'")
    conn.execute("""ALTER TABLE foreign_catalog.unspecified
        ADD CONSTRAINT unspecified_part_id_check CHECK(part_id ~ '^FN[GP][0-9]{4}$')""")
LABEL = {
    "part_id":"唯一标识符", "code":"冠英编号", "wva":"WVA", "bfmc":"BFMC", "fmsi":"FMSI",
    "oem":"OEM", "item":"Item（车型）", "a":"A 外弧", "b":"B 内弧", "c":"C 宽度",
    "d":"D 厚度", "length_mm":"盘片长度（mm）", "size_raw":"表列尺寸原文",
    "arc":"弧形图标值", "taper":"角度（Taper）", "holes":"孔数",
    "rivet":"铆钉规格", "rivet_dia":"铆钉直径（Rivet dia.）", "picture":"原册示意图",
    "application":"适用车型 / 原册系列",
}

def fields(country):
    keys=["part_id","code",*COUNTRIES[country][2],"a","b","c","d"]
    if country=="C":
        keys.extend(["length_mm","size_raw"])
    keys.extend(["arc","taper","holes","rivet"])
    if country=="C":
        keys.append("rivet_dia")
    return [*keys,"picture","application"]

# Visual readings of printed cells whose spaces, suffixes or punctuation were
# lost during OCR. Manufacturer spellings in the source are kept verbatim.
PRINTED_BRANDS = {
    9:"SAF,TRAILOR YORK TRAILERS",10:"SAF,TRAILOR YORK TRAILERS",27:"BOVA,DAF,NEOPLAN",
    28:"PERROT BREMSEN",29:"PERROT BREMSEN",34:"SAF,TRAILOR YORK TRAILERS",
    35:"SAF,TRAILOR YORK TRAILERS ROCKWELL",47:"MERITOR,ROCKWELL",
    129:"YUTONG,KINGLONG,HIGER",130:"YUTONG,KINGLONG,HIGER",
    181:"GE,MITSUBISH,FUSO",182:"GE,MITSUBISH,FUSO",183:"GE,MITSUBISH,FUSO",
}
ITEMS = [
    "STEYR F1","STEYR F2","STEYR R","HOWO1","HOWO2","EQ153 F","EQ153 R",
    "NEW EQ153 F","NEW EQ153 R","CA9T F","CA9T R",
    "HYUNDAI BUS F1","HYUNDAI BUS F2","HYUNDAI BUS R1","HYUNDAI BUS R2",
    "DAWOO BUS F","DAWOO BUS R","DAWOO F","DAWOO R","HYUNDAI R1","HYUNDAI R2",
]
MODEL_REFS = {
    173:"BELAZ 3T",174:"FAW 380 R",176:"FAW 380 FA",177:"FAW 380 FB",
    178:"FAW FJ NEW MODAL REAR A",179:"FAW FJ NEW MODAL REAR B",180:"TATA 1510",
    181:"MC 809770 /527R",184:"TATA NOVAS REAR",185:"FUSO F",186:"CXZ FRONT 1418 47115-406",
}

def printed_order(evidence):
    for page, items in groupby(sorted(evidence,key=lambda e:e["page_key"]),key=lambda e:e["page_key"]):
        group=list(items)
        # Numbered grids flow down the left printed page, then the right.
        numbered=[e for e in group if e["reading"].get("code")]
        yield from sorted(numbered,key=lambda e:int(e["reading"]["code"].split("-")[1]))
        cards=defaultdict(list)
        for e in group:
            if "card_box" in e["reading"]:
                cards[tuple(e["reading"]["card_box"])].append(e)
        # The facing pages are read separately. On each, card rows read across
        # and each card's thickness rows read down before moving to the next.
        for half in range(2):
            boxes=[b for b in cards if cards[b][0]["box"][0]//1400==half]
            bands=[]
            for box in sorted(boxes,key=lambda b:b[1]):
                if not bands or box[1]-bands[-1][0][1]>85:
                    bands.append([])
                bands[-1].append(box)
            for band in bands:
                for box in sorted(band):
                    yield from sorted(cards[box],key=lambda e:e["box"][1])

def source_rows():
    evidence=[e for e in json.loads(MANIFEST.read_text(encoding="utf8"))
              if e["page_key"].startswith("en") and e["reading"]["kind"] in ("鼓式","盘式")]
    counters=Counter()
    result=[]
    for order,e in enumerate(printed_order(evidence),1):
        r=e["reading"]
        code=r.get("code")
        n=int(code.split("-")[1]) if code else None
        disc=r["kind"]=="盘式"
        card=r.get("card_box")
        area="C" if disc or card else SECTIONS[r["section"]]
        prefix="F"+area+("P" if disc else "G")
        counters[prefix]+=1
        key=f"{prefix}{counters[prefix]:04}"
        x,y,X,Y=e["box"]
        values=dict(part_id=key,code=code,wva=r.get("wva"),bfmc=r.get("bfmc"),
                    fmsi=r.get("fmsi"),oem=r.get("oe_ref"),item=r.get("catalog_ref"),
                    a=r.get("outer_arc"),b=r.get("inner_arc"),c=r.get("width"),d=r.get("thickness"),
                    arc=r.get("arc_value"),taper=r.get("taper"),holes=r.get("holes"),
                    size_raw=r.get("size_raw"),rivet=r.get("rivet"),application=r.get("brand"))
        if disc:
            length,width,thickness=re.split(r"\s*[*×xX]\s*",r["size_raw"])
            values.update(length_mm=length,c=width,d=thickness,wva=r["reference_raw"])
            if n in (29,31,36,37,38):
                values["wva"]={29:"VOLVO86",31:"WG 9100",36:"AD 02",37:"AD 03",38:"DA 05"}[n]
            picture_box=(X-215,y+2,X-2,Y-2)
        elif card:
            values.update(item=r["name"],application=r["series"],rivet_dia=r.get("rivet"),rivet=None)
            picture_box=(card[0],card[1],x-3,card[3])
        else:
            if n in PRINTED_BRANDS:
                values["application"]=PRINTED_BRANDS[n]
            if n in MODEL_REFS:
                values["wva"]=MODEL_REFS[n]
            if 122<=n<=142:
                values["item"]=ITEMS[n-122]
            if n in (93,95):
                values["fmsi"]=values["fmsi"][:-1]+"c"
            if 114<=n<=121:
                values["oem"]=("MITSUBITSHI Canter F","MITSUBITSHI Canter R","MITSUBITSHI JUMPO R-1",
                               "MITSUBITSHI JUMPO R-2","HINO ZY F-1","HINO ZY F-2","HINO ZY R-1","HINO ZY R-2")[n-114]
            picture_box=(x+90,y+2,x+184,Y-2)
        values["picture"]=e["id"]
        result.append((area,{k:values.get(k) or None for k in fields(area)},
                       (order,e["id"],e["spec_key"],e["page_key"],list(picture_box))))
    if len(result)!=len(evidence) or len({m[1] for _,_,m in result})!=len(evidence):
        raise ValueError("英文册存在漏行或重复来源")
    return result

def install(conn):
    conn.execute("SELECT pg_advisory_xact_lock(400713)")
    conn.execute("CREATE SCHEMA IF NOT EXISTS foreign_catalog")
    conn.execute("""CREATE TABLE IF NOT EXISTS foreign_catalog.source (
        part_id text PRIMARY KEY, pdf_order integer UNIQUE NOT NULL, observation_id text UNIQUE NOT NULL,
        legacy_key text UNIQUE NOT NULL, page_key text NOT NULL, picture_box integer[] NOT NULL)""")
    entries=source_rows()
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO foreign_catalog.source VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT(part_id) DO NOTHING""",[(v["part_id"],*m) for _,v,m in entries])
        for area,(_,table,_) in COUNTRIES.items():
            keys=fields(area)
            cols=", ".join(k+" text" for k in keys[1:])
            cur.execute(f"""CREATE TABLE IF NOT EXISTS foreign_catalog.{table} (
                part_id text PRIMARY KEY REFERENCES foreign_catalog.source(part_id)
                CHECK(part_id ~ '^F{area}[GP][0-9]{{4}}$'), {cols})""")
            cur.executemany(f"INSERT INTO foreign_catalog.{table} ({','.join(keys)}) VALUES "
                            f"({','.join(['%s']*len(keys))}) ON CONFLICT(part_id) DO NOTHING",
                            [tuple(v[k] for k in keys) for a,v,_ in entries if a==area])
    saved=conn.execute("SELECT part_id,observation_id,pdf_order FROM foreign_catalog.source").fetchall()
    if {(r["part_id"],r["observation_id"],r["pdf_order"]) for r in saved} != {
            (v["part_id"],m[1],m[0]) for _,v,m in entries}:
        raise ValueError("已有编号的来源或 PDF 顺序已变动，需要显式迁移")

def read_tables(conn,prefixes=None):
    condition="" if prefixes is None else "WHERE left(t.part_id,3)=ANY(%s)"
    return {area:conn.execute(f"""SELECT t.*, s.page_key,s.pdf_order,s.picture_box,s.legacy_key
                FROM foreign_catalog.{table} t JOIN foreign_catalog.source s USING (part_id)
                {condition} ORDER BY s.pdf_order""",None if prefixes is None else (prefixes,)).fetchall()
            for area,(_,table,_) in COUNTRIES.items()
            if prefixes is None or any(p.startswith("F"+area) for p in prefixes)}

def sales_fields(row):
    """The sales API uses the same dimensions and identifiers as the country sheets."""
    return dict(spec_id=row["part_id"],code=row["code"],outer_arc=row["a"],inner_arc=row["b"],
                width=row["c"],thickness=row["d"],arc_value=row["arc"],taper=row["taper"],
                holes=row["holes"],rivet=row["rivet"] or row.get("rivet_dia"),wva=row.get("wva"),
                bfmc=row.get("bfmc"),fmsi=row.get("fmsi"),oe_ref=row.get("oem"),
                catalog_ref=row.get("item"),brand=row["application"],size_raw=row.get("size_raw"),
                country_code=row["part_id"][1],catalog_country=COUNTRIES[row["part_id"][1]][0],pdf_order=row["pdf_order"])
