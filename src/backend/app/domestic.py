"""Printed domestic catalogue rows, with a distinct sales ID per thickness option."""
import base64
import io
import json
import re
from collections import Counter
from itertools import groupby

from openpyxl import load_workbook
from PIL import Image

from .archive import MANIFEST, MATERIALS
from .catalog import DOCS, db
from .sync import cell_text, data_hash, digest

BOOK = DOCS / "国内刹车片目录.xlsx"
LABELS = dict(part_id="唯一标识符", series="系列", name="名称", outer_arc="外弧", width="宽度",
              thickness="厚度", holes="孔数", picture="图片", fit_notes="适配车型")
EDITABLE = [k for k in LABELS if k not in ("part_id", "picture")]
PAIR = r"[0-9]+(?:\.[0-9]+)?/[0-9]+(?:\.[0-9]+)?"

def picture_box(page, entry):
    x,y,right,bottom = entry["box"]
    card = entry["reading"].get("card_box")
    if card:
        return [card[0],card[1],card[2],y-2]
    # Find the four interior dividers of this specific printed table row.
    strip = page.crop((x+8,y+5,right-4,bottom-5))
    pixels = strip.load()
    ink = [i for i in range(strip.width) if sum(pixels[i,j]<115 for j in range(strip.height))>.9*strip.height]
    edges = []
    for i in ink:
        if not edges or i-edges[-1][-1]>3:
            edges.append([])
        edges[-1].append(i)
    if len(edges)!=4:
        raise ValueError(f"无法定位图片栏 {entry['id']}")
    return [x+8+edges[2][-1]+2,y+3,x+8+edges[3][0]-2,bottom-3]

def printed_rows():
    source = [e for e in json.loads(MANIFEST.read_text(encoding="utf8"))
              if e["page_key"].startswith("cn") and e["reading"]["kind"] in ("鼓式","盘式")]
    def order(e):
        x,y,*_ = e["box"]
        if e["reading"]["kind"]=="盘式":
            return e["page_key"],x//1400,round(y/45),x
        return e["page_key"],x//700,y,int(e["id"].rsplit("-",1)[1])
    counters = Counter()
    for page, group in groupby(sorted(source,key=order),key=lambda e:e["page_key"]):
        with Image.open(MATERIALS/"pages"/(page+".jpg")) as src:
            image = src.convert("L")
        boxes = {}
        for e in group:
            r = e["reading"]
            prefix = "DCG" if r["kind"]=="鼓式" else "DCP"
            raw = r.get("thickness")
            options = [raw]
            if raw=="10/18.5(18,20)":
                options = ["10/18.5","18","20"]
            box = tuple(e["box"])
            if box not in boxes:
                boxes[box] = picture_box(image,e)
            for option_no,t in enumerate(options,1):
                if t and "/" not in t:
                    t = t+"/"+t
                if t and not re.fullmatch(PAIR,t):
                    raise ValueError(f"厚度格式异常 {e['id']} {t}")
                counters[prefix] += 1
                holes = "6" if r["name"]=="解放红塔后A" and r["holes"]=="C" else r["holes"]
                yield dict(part_id=f"{prefix}{counters[prefix]:04}",series="其他" if r["series"] in
                           ("其他系列","盘式刹车片","") else r["series"],name=r["name"],outer_arc=r.get("outer_arc"),
                           width=r.get("width"),thickness=t,holes=holes,picture=e["id"],fit_notes=r.get("fit_notes") or None,
                           legacy_key=e["spec_key"],option_no=option_no,page_key=page,picture_box=boxes[box])

def install(c):
    c.execute("SELECT pg_advisory_xact_lock(400714)")
    if c.execute("SELECT to_regclass('domestic_catalog.parts') AS t").fetchone()["t"]:
        return
    c.execute("CREATE SCHEMA IF NOT EXISTS domestic_catalog")
    c.execute(r"""CREATE TABLE domestic_catalog.parts (
        part_id text PRIMARY KEY CHECK(part_id ~ '^DC[GP][0-9]{4}$'), series text NOT NULL, name text NOT NULL,
        outer_arc text, width text, thickness text CHECK(thickness ~ '^[0-9]+(\.[0-9]+)?/[0-9]+(\.[0-9]+)?$'),
        holes text, picture text NOT NULL, fit_notes text, legacy_key text NOT NULL, option_no integer NOT NULL,
        page_key text NOT NULL, picture_box integer[] NOT NULL, UNIQUE(legacy_key,option_no))""")
    rows=list(printed_rows())
    with c.cursor() as cur:
        cur.executemany("INSERT INTO domestic_catalog.parts VALUES ("+",".join(["%s"]*13)+")",
                        [tuple(r.values()) for r in rows])
    c.execute("CREATE TABLE domestic_catalog.sync_state (id integer PRIMARY KEY CHECK(id=1), file_hash text, data_hash text)")

def sales_fields(part):
    values = dict(spec_id=part["part_id"],**{k:part[k] for k in EDITABLE},country_code="C",
                  pdf_order=int(part["part_id"][3:]) + (10000 if part["part_id"][2]=="P" else 0))
    if part["option_no"]>1:
        # A newly distinguished thickness has no independently verified price or SKU.
        values.update(dict.fromkeys(("sku","price","material","currency","sale_unit","price_source","valid_until")))
    return values

def read_rows(c,prefixes=None):
    if prefixes is None:
        return c.execute("SELECT * FROM domestic_catalog.parts ORDER BY part_id").fetchall()
    return c.execute("SELECT * FROM domestic_catalog.parts WHERE left(part_id,3)=ANY(%s) ORDER BY part_id",(prefixes,)).fetchall()

def export(rows, file_hash):
    from publish_foreign import export_book
    sheets=[]
    for prefix,group in groupby(rows,key=lambda r:r["part_id"][:3]):
        data=[]; images=[]
        for page,items in groupby(group,key=lambda r:r["page_key"]):
            with Image.open(MATERIALS/"pages"/(page+".jpg")) as im:
                for r in items:
                    thumb=im.crop(r["picture_box"])
                    thumb.thumbnail((125,54),Image.Resampling.LANCZOS)
                    buf=io.BytesIO()
                    thumb.save(buf,"PNG")
                    images.append(dict(b64=base64.b64encode(buf.getvalue()).decode(),width=thumb.width,height=thumb.height))
                    data.append([None if k=="picture" else r[k] for k in LABELS])
        sheets.append(dict(area=prefix,name="鼓式" if prefix=="DCG" else "盘式",keys=list(LABELS),
                           headers=list(LABELS.values()),rows=data,images=images))
    export_book(BOOK,sheets,file_hash)

def synchronize():
    with db() as c:
        install(c)
        c.execute("LOCK TABLE domestic_catalog.parts IN SHARE ROW EXCLUSIVE MODE")
        rows=read_rows(c)
        current=[[r[k] for k in LABELS if k!="picture"] for r in rows]
        db_hash=data_hash(current)
        raw=BOOK.read_bytes() if BOOK.exists() else None
        file_hash=digest(raw) if raw is not None else None
        state=c.execute("SELECT * FROM domestic_catalog.sync_state WHERE id=1").fetchone()
        if state and (file_hash,db_hash)==(state["file_hash"],state["data_hash"]):
            return db_hash
        if raw is not None and (not state or file_hash!=state["file_hash"]):
            wb=load_workbook(io.BytesIO(raw),read_only=True)
            try:
                if wb.sheetnames!=["鼓式","盘式"]:
                    raise ValueError("国内工作表名称或顺序有变动")
                incoming=[]
                for ws,prefix in zip(wb.worksheets,("DCG","DCP")):
                    lines=iter(ws.values)
                    if list(next(lines,()))!=list(LABELS.values()):
                        raise ValueError("国内工作表表头有变动")
                    for line in lines:
                        if not any(line):continue
                        values=[cell_text(v) for k,v in zip(LABELS,line,strict=True) if k!="picture"]
                        if not (values[0] or "").startswith(prefix) or any(v and v.startswith("=") for v in values):
                            raise ValueError("国内工作表须按原册填写实际值")
                        incoming.append(values)
            finally:
                wb.close()
            if [r[0] for r in incoming]!=[r[0] for r in current]:
                raise ValueError("国内规格编号或顺序有变动")
            new_hash=data_hash(incoming)
            if db_hash!=new_hash and (not state or state["data_hash"]!=db_hash):
                raise ValueError("国内目录 Excel 与数据库均有变动，请核对后合并")
            changed=[new[1:]+[new[0]] for old,new in zip(current,incoming) if old!=new]
            with c.cursor() as cur:
                cur.executemany("UPDATE domestic_catalog.parts SET "+",".join(k+"=%s" for k in EDITABLE)+
                                " WHERE part_id=%s",changed)
            if digest(BOOK.read_bytes())!=file_hash:
                raise ValueError("国内工作簿在读取时又被保存，请重试")
            db_hash=new_hash
        else:
            export(rows,file_hash)
            file_hash=digest(BOOK.read_bytes())
        c.execute("""INSERT INTO domestic_catalog.sync_state VALUES(1,%s,%s) ON CONFLICT(id)
            DO UPDATE SET file_hash=excluded.file_hash,data_hash=excluded.data_hash""",(file_hash,db_hash))
        return db_hash

if __name__=="__main__":
    print(synchronize())
