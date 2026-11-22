"""Publish both source catalogues and keep legacy keys, sales fields and unrelated records."""
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import copy
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from app.archive import MATERIALS, MANIFEST, PDFS, MARKETS, page_use, restore
from app.catalog import BOOK, FIELDS, LEGACY_FIELDS, db, init_db
from app.sync import from_db, normalized, data_hash, digest, save_db, sync, write_snapshot

def clean(s):
    return re.sub(r"\s+","",unicodedata.normalize("NFKC",str(s or ""))).upper()

def name_key(s):
    return clean(s).removesuffix("刹")

def size_key(row):
    return tuple(clean(row.get(k)) for k in ("outer_arc","width","thickness"))

def signature(row):
    return (row["kind"],name_key(row["name"]),*size_key(row),clean(row.get("holes")))

def filled(data):
    return {k:str(data[k]).strip() if data.get(k) is not None and str(data[k]).strip() else None for k in FIELDS}

def build(src,existing):
    specs={r["spec_id"]:r.copy() for r in existing}
    oldcards={signature(r):r["spec_id"] for r in existing if r["spec_id"].startswith("CAT13-")}
    previous=defaultdict(list)
    if MANIFEST.exists():
        for observation in json.loads(MANIFEST.read_text(encoding="utf8")):
            previous[observation["spec_key"]].append(observation)
    references=set()
    evidence=[]
    serial=Counter()
    for r in src:
        doc=r["doc"]
        r["market"]=MARKETS[doc]
        key=f'{doc}-{r["page"]:02}'
        if r.get("doc")=="cn" and r["kind"]=="盘式":
            hit=re.fullmatch(r"WVA\s*(\d{5})",r["name"],re.I)
            if hit:r["wva"]=hit[1]
        if r.get("reference_raw") and not r.get("wva"):
            r["catalog_ref"]=r["reference_raw"]
        if r.get("kind")=="盘式" and r.get("size_raw"):
            nums=re.split("[xX×*]",clean(r["size_raw"]))
            if all(re.fullmatch(r"\d+(\.\d+)?",t) for t in nums) and len(nums) in (2,3):
                r["width"]=nums[1]
                if len(nums)==3:r["thickness"]=nums[2]
        r["holes"]=clean(r.get("holes")) or None
        for k in ["width","thickness","outer_arc","inner_arc"]:
            if r.get(k):r[k]=clean(r[k])
        # Only explicit front/rear markers in this catalogue's own part label.
        if r["kind"]=="鼓式" and not r.get("position"):
            positions=set(re.findall(r"[前后]",r["name"]))
            if len(positions)==1:
                r["position"]=positions.pop()
        box=r["box"]
        loc=f"{key}-{box[0]}-{box[1]}"
        serial[loc]+=1
        obs_id=f"{loc}-{serial[loc]}"
        sid=obs_id.upper()
        if doc=="en":
            sid=r.get("code") or (oldcards.get(signature(r)) if r["page"]==13 else None) or sid
        if sid in references:
            sid=obs_id.upper()
        if sid in references or not r.get("name"):
            raise ValueError(f"来源行或规格键异常 {obs_id}")
        references.add(sid)
        spec=specs.setdefault(sid,filled(dict(spec_id=sid,status="目录转录")))
        others=[o["reading"] for o in previous[sid] if not o["page_key"].startswith(doc+"-")]
        for k in FIELDS:
            # Drop inherited values from the other market. Preserve local edits
            # and independently confirmed seed fields on the surviving key.
            if spec[k] and any(spec[k]==o.get(k) for o in others):
                spec[k]=None
            if not spec[k] and r.get(k):
                spec[k]=str(r[k])
        spec.update(market=MARKETS[doc],page_refs=key,comparison="单册来源")
        if not spec["source"]:
            spec["source"]=f'{PDFS[doc]} · PDF {r["page"]} / {r["name"]}'
        evidence.append(dict(id=obs_id,page_key=key,spec_key=sid,box=box,
            reading={k:v for k,v in r.items() if k not in {"doc","page","box"}}))
    for spec in specs.values():
        if spec["status"]=="照片组待核":
            # An independent photo album has no market of its own on the basis
            # of a shared label. Explicit enterprise assignments can be kept.
            inferred=spec.get("comparison") or ""
            if not spec["market"] or spec["market"]=="待确认" or inferred.startswith("照片组名称精确命中"):
                spec.update(market="待确认",comparison="独立照片组，市场待企业确认")
    return list(specs.values()),evidence

def audit_sheet(wb,name,head,lines,widths):
    sh=wb[name] if name in wb.sheetnames else wb.create_sheet(name)
    sh.delete_rows(1,sh.max_row)
    sh.append(head)
    for row in lines:sh.append(row)
    for c in sh[1]:
        c.font=Font(bold=True,color="FFFFFF");c.fill=PatternFill("solid",fgColor="193C4B")
    sh.freeze_panes="C2";sh.auto_filter.ref=sh.dimensions
    for i,w in enumerate(widths,1):sh.column_dimensions[get_column_letter(i)].width=w

def crosswalk(evidence,specs):
    groups=defaultdict(lambda:{"en":[],"cn":[]})
    for e in evidence:
        r=e["reading"];doc=e["page_key"][:2]
        if r["kind"]=="鼓式":
            keys=[name_key(r["name"])]
        elif r["kind"]=="盘式":
            keys=[clean(n) for n in (r.get("wva") or "").split("；") if n]
            if not keys:
                keys=[clean(r.get("catalog_ref") or r["name"])]
        else:continue
        for k in keys:groups[(r["kind"],k)][doc].append(e)
    index={s["spec_id"]:s for s in specs}
    def measure(e):
        r=e["reading"]
        if r["kind"]=="盘式":
            return "×".join(re.split("[xX×*]",clean(r["size_raw"]))[:2])
        return "×".join(size_key(r))+" / "+(r.get("holes") or "?")+"孔"
    def summarize(items):
        return ("；".join(dict.fromkeys(e["reading"].get("code") or e["reading"]["name"] for e in items)),
                "；".join(dict.fromkeys(e["reading"].get("size_raw") or "" for e in items)),
                "；".join(sorted(set(e["page_key"] for e in items))))
    lines=[]
    for (kind,k),g in sorted(groups.items()):
        if not g["en"] or not g["cn"]:continue
        def normalized_measure(t):
            return re.sub(r"(?<=\d)\.0+(?!\d)","",measure(t))
        equal={normalized_measure(e) for e in g["en"]}=={normalized_measure(e) for e in g["cn"]}
        if kind=="盘式":
            conclusion="前两维相符；厚度另核" if equal else "同参考号，前两维有差异"
        else:
            conclusion="所比尺寸、孔数相符" if equal else "规格集合有差异"
        for e in g["en"]+g["cn"]:
            index[e["spec_key"]]["comparison"]="跨市场同名或同号；"+conclusion
        lines.append([kind,k,*summarize(g["en"]),*summarize(g["cn"]),conclusion])
    return lines

def publish():
    init_db()
    try:
        sync()
    except PermissionError:
        pass  # The original remains untouched until Excel releases its lock.
    src=json.loads((MATERIALS/"catalog-observations.json").read_text(encoding="utf8"))
    for prefix,expected in [("GYS-",191),("GY-",52)]:
        actual=[r["code"] for r in src if (r.get("code") or "").startswith(prefix)]
        assert sorted(actual)==[prefix+f"{i:03}" for i in range(1,expected+1)]
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(400712)")
        c.execute("LOCK TABLE catalog_product,catalog_spec,catalog_media IN SHARE ROW EXCLUSIVE MODE")
        pending=c.execute("SELECT snapshot FROM catalog_pending_excel WHERE id=1").fetchone()
        active=BOOK.with_name(pending["snapshot"]) if pending else BOOK
        raw=active.read_bytes();filehash=digest(raw)
        base=from_db(c); state=c.execute("SELECT * FROM catalog_sync WHERE id=1").fetchone()
        legacy={**base,"产品规格":[{k:r[k] for k in LEGACY_FIELDS} for r in base["产品规格"]]}
        if state["file_hash"]!=filehash or state["data_hash"] not in (data_hash(base),data_hash(legacy)):
            raise RuntimeError("工作簿或数据库在发布前发生变化，请重试")
        base["产品规格"],evidence=build(src,base["产品规格"])
        if len(evidence)!=len({e["spec_key"] for e in evidence}):
            raise RuntimeError("来源规格键不唯一")
        data=normalized(base)
        wb=load_workbook(io.BytesIO(raw))
        ws=wb["产品规格"]
        for i,label in enumerate(FIELDS.values(),1):
            cell=ws.cell(1,i);cell.value=label;cell._style=copy(ws["A1"]._style)
            if i>28:ws.column_dimensions[get_column_letter(i)].width=26
        stats=Counter(e["page_key"] for e in evidence)
        compare=crosswalk(evidence,data["产品规格"])
        audit_sheet(wb,"双册对照",["产品类型","同名或编号线索","英文册型号","英文规格原文","英文位置","中文册型号","中文规格原文","中文位置","核对结果"],
            compare,[14,27,28,64,20,28,64,20,35])
        audit_sheet(wb,"逐页清单",["原文件","PDF 页","页面内容","规格观察数","原页索引"],
            [(fn,n,page_use(d,n),stats[f"{d}-{n:02}"],f"{d}-{n:02}") for d,fn in PDFS.items() for n in range(1,35 if d=="en" else 24)], [28,12,40,14,18])
        audit_sheet(wb,"双册原始记录",["来源页","规格唯一键","市场","原名","原册尺寸","外弧","宽度","厚度","孔数","车型原文","观察键"],
            [(e["page_key"],e["spec_key"],*[e["reading"].get(k) for k in ("market","name","size_raw","outer_arc","width","thickness","holes","fit_notes")],e["id"]) for e in evidence],
            [14,32,12,26,46,12,12,14,9,58,32])
        audit_sheet(wb,"待企业补充",["市场","规格唯一键","名称","来源","待补信息"],[],[12,34,26,65,65])
        save_db(c,data)
        serialized=json.dumps(evidence,ensure_ascii=False,separators=(",",":"))
        with NamedTemporaryFile(dir=MANIFEST.parent,delete=False,suffix=".tmp") as f:
            f.write(serialized.encode());temp=Path(f.name)
        temp.replace(MANIFEST)
        restore(c)
        try:
            after=write_snapshot(wb,data,filehash,source=active)
        except PermissionError:
            alternate=BOOK.with_name("冠英产品知识库-全目录.xlsx")
            if active!=BOOK or alternate.exists():
                raise RuntimeError("已有待回写的全目录副本，请先核对文件")
            after=write_snapshot(wb,data,filehash,alternate)
            c.execute("INSERT INTO catalog_pending_excel VALUES (1,%s,%s)",(filehash,alternate.name))
            print("Locked workbook; published",alternate.name)
        c.execute("UPDATE catalog_sync SET file_hash=%s,data_hash=%s WHERE id=1",(after,data_hash(data)))
        print("source observations",len(evidence),"catalog records",len(data["产品规格"]))
        print(Counter(r["market"] for r in data["产品规格"]))
        print("linked across both",sum("；" in (r["page_refs"] or "") for r in data["产品规格"]))
        print("different sets",sum("有差异" in (r["comparison"] or "") for r in data["产品规格"]))

if __name__=="__main__":publish()

