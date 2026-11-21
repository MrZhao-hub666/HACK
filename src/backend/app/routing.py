"""Resolve the three catalogue letters before requesting detailed product records."""
import re
import unicodedata

from .foreign import COUNTRIES, canonical_id
from .match import norm

ID=re.compile(r"(?<![a-z0-9])((?:f[eajcknu]|dc)[gp]\d{4})(?![a-z0-9])",re.I)
PREFIX=re.compile(r"(?:F[EAJCKN]|DC)[GP]\d{4}")
SLOTS=("market","country","kind")
MARKETS={"F":"外贸","D":"国内"}
KINDS={"G":"鼓式","P":"盘式"}
QUESTIONS={"market":"这次按国内版还是外贸版采购？",
           "country":"车辆属于哪个国别或车系？例如美国、日本或中国。",
           "kind":"旧件是装在制动鼓内的弧形衬片，还是夹住制动盘的盘片？"}
TERMS={
    "market":{"D":r"国内(?:版|采购|销售|使用|用)?|内销|中国国内|domestic(?: chinese)?(?: market)?|china domestic",
              "F":r"外贸|出口|出口版|海外采购|外销|export(?:s|ing)?|overseas purchase"},
    "country":{"A":r"美国|美系|美式|american|us-made|\busa?\b","E":r"欧洲|欧盟|欧系|欧式|european|europe|\beu\b",
               "J":r"日本|日系|日式|japanese|japan","K":r"韩国|韩系|韩式|korean|korea",
               "C":r"中国|国产|中系|chinese|china","N":r"无国别|不限国别|国别不限|country.neutral"},
    "kind":{"G":r"鼓式|鼓刹|鼓片|制动鼓内|鼓型|鼓形|^鼓$|drum(?: brake)?(?: linings?)?",
            "P":r"盘式|盘刹|碟刹|碟式|盘片|盘型|盘形|夹住制动盘|^[盘碟]$|dis[ck](?: brake)?(?: pads?)?"}}

def mentions(text,slot):
    """Only affirmative descriptions of this vehicle count as country evidence."""
    found=[]
    for code,pattern in TERMS[slot].items():
        for m in re.finditer(pattern,text,re.I):
            before,after=text[:m.start()],text[m.end():]
            if re.search(r"(?:不是|不要|不用|非|not(?: an?)?|no)\s*$",before,re.I):
                continue
            if slot=="country" and not (
                text.strip(" 。.？?!")==m[0] or re.search(r"(车系|车辆国别|国别|制造地)\s*[:：为是]?\s*$",before)
                or (re.search(r"(?:^|[,，;；、])\s*$",before) and re.match(r"\s*(?:$|[,，;；、])",after))
                or re.match(r"(?:的)?(?:卡车|车辆|车型|车桥|货车|挂车|车系|车|制造)|\s+(?:truck|vehicle|axle|trailer|made)",after,re.I)
                or m[0] in ("无国别","不限国别","国别不限","欧系","美系","日系","韩系")):
                continue
            found.append((m.start(),code,m[0]))
    return sorted(found)

def route_inquiry(turns,index,clues,market=None,country=None):
    slots={k:dict(value=None,source=None,evidence=None) for k in SLOTS}
    def put(slot,value,source,evidence):
        slots[slot]=dict(value=value,source=source,evidence=evidence)

    # The model can resolve paraphrases and references to a preceding question.
    # Direct statements, later corrections and the salesperson's controls take priority.
    for slot,mapping in (("market",{"国内":"D","外贸":"F"}),("kind",{"盘式":"P","鼓式":"G"}),
                         ("country",{k:k for k in (*COUNTRIES,"OTHER")})):
        value=mapping.get(getattr(clues,slot))
        if value and slot in clues.routing_evidence:
            put(slot,value,"模型提取",clues.routing_evidence[slot])
    last_question=""
    customers=[]
    for t in turns:
        text=unicodedata.normalize("NFKC",t.text).strip()
        if t.role=="sales":
            last_question=text
            continue
        customers.append(text)
        for slot in SLOTS:
            answers=mentions(text,slot)
            if len({a[1] for a in answers})>1 and re.search(r"还是|或者|\bor\b",text,re.I):
                put(slot,None,None,None)
                continue
            if not answers and last_question:
                choices=mentions(last_question,slot)
                if len(choices)==1 and re.fullmatch(r"是的?|对的?|没错|yes|correct",text.strip(" 。.!"),re.I):
                    answers=[(0,choices[0][1],text)]
                if len(choices)==1 and slot in ("kind","market") and re.fullmatch(r"不是|不对|no",text.strip(" 。.!"),re.I):
                    opposite={"D":"F","F":"D","P":"G","G":"P"}
                    answers=[(0,opposite[choices[0][1]],text)]
                if len(choices)==2 and text in ("前者","后者","第一个","第二个"):
                    answers=[choices[int(text in ("后者","第二个"))]]
            if answers:
                _,code,term=answers[-1]
                put(slot,code,"客户表述",term)
        last_question=""
    country_names={v[0]:k for k,v in COUNTRIES.items()}
    if country:
        put("country",country_names.get(country,{"欧盟":"E"}.get(country,country.upper())),"销售选择",country)
    if market:
        put("market",{"国内":"D","外贸":"F"}[market],"销售选择",market)

    products=[r for r in index if PREFIX.fullmatch(r["spec_id"])]
    available={r["spec_id"][:3] for r in products}
    # Extract the last literal number even if a model rewrites punctuation or casing.
    explicit=re.compile(r"(?<![a-z0-9])(fmsi|bfmc|wva|oem|oe)\s*(?:号(?:码)?|no\.?|number)?\s*[:：#-]?\s*([a-z\d./-]*\d[a-z\d./-]*)",re.I)
    for text in reversed(customers):
        own=ID.search(text)
        ref=explicit.search(text)
        if own:
            clues.scheme,clues.number="spec_id",canonical_id(own[1].upper())
            break
        if ref:
            scheme=ref[1].lower()
            clues.scheme,clues.number=("oe_ref" if scheme in ("oe","oem") else scheme),ref[2].rstrip(".")
            break
        if clues.number and norm(clues.number) in norm(text):
            break
    clues.scheme=clues.scheme.lower()
    key=norm(clues.number)
    lookup_source="目录编码" if key else "目录型号"
    if key:
        matched={r["spec_id"][:3] for r in products if any(norm(ref["number"])==key and
                 (not clues.scheme or ref["scheme"]==clues.scheme) for ref in r["references"])}
        evidence=clues.number
    else:
        label=norm(clues.name)
        matched={r["spec_id"][:3] for r in products if label and norm(r.get("name"))==label}
        evidence=clues.name
        if not matched:
            measures={k:norm(getattr(clues,k)) for k in ("width","holes","thickness") if getattr(clues,k)}
            identifier=next((k for k in ("axle","vehicle","series","brand") if getattr(clues,k)),None)
            if len(measures)>=2 or (identifier and measures):
                def fits(r):
                    if identifier and norm(getattr(clues,identifier)) not in norm(r.get(identifier)):
                        return False
                    for k,v in measures.items():
                        if norm(r.get(k)) not in ({v,v+"/"+v} if k=="thickness" else {v}):
                            return False
                    return True
                matched={r["spec_id"][:3] for r in products if fits(r)}
                lookup_source="目录参数组合"
                evidence="、".join([f"{k}={v}" for k,v in measures.items()]+([getattr(clues,identifier)] if identifier else []))
    if clues.scheme=="spec_id" and PREFIX.fullmatch(clues.number):
        matched={clues.number[:3]}
    scheme=clues.scheme
    if not scheme:
        for text in reversed(customers):
            hit=re.search(r"\b(FMSI|BFMC)\b",text,re.I|re.ASCII)
            if hit:
                scheme=hit[1].lower()
                break
    if not slots["country"]["value"] and scheme in ("fmsi","bfmc"):
        put("country","A" if scheme=="fmsi" else "E","编号体系",scheme.upper())

    def compatible(prefix):
        m,c,k=(slots[s]["value"] for s in SLOTS)
        return ((not m or m==prefix[0]) and (not c or prefix[1] in (c,"N"))
                and (not k or k==prefix[2]))

    supported={p for p in matched if compatible(p)}
    conflict=bool(matched and not supported)
    for i,slot in enumerate(SLOTS):
        letters={p[i] for p in supported}
        if not slots[slot]["value"] and len(letters)==1:
            put(slot,letters.pop(),lookup_source,evidence)
    if slots["market"]["value"]=="D" and not slots["country"]["value"] and {
            p[1] for p in available if p.startswith("D")}=={"C"}:
        put("country","C","国内目录分区","DC")
    missing=[s for s in SLOTS if not slots[s]["value"]]
    letters=[slots[s]["value"] for s in SLOTS]
    prefix="".join(letters) if not missing and all(len(x)==1 for x in letters) else None
    eligible=sorted(p for p in available if compatible(p) and (not matched or p in supported or p[1]=="N"))
    language=None
    if not slots["market"]["value"]:
        words=" ".join(customers)
        if re.search(r"[\u4e00-\u9fff]",words):
            language="D"
        elif len(re.findall(r"\b[a-z]{2,}\b",words,re.I))>=3:
            language="F"
    suggested=None
    if language and letters[1] and len(letters[1])==1 and letters[2]:
        suggested=language+letters[1]+letters[2]
    status="needs_clarification" if missing else "resolved"
    question=QUESTIONS[missing[0]] if missing else ""
    if conflict:
        status="conflict"
        question=f"目录中「{evidence}」对应 {'、'.join(sorted(matched))}，与当前条件有冲突。请核对旧件完整编号、采购版本和盘鼓类型。"
    elif not eligible and not missing:
        status="no_catalog"
        question="现有目录没有覆盖这组条件，请提供旧件完整编号或铭牌，由销售核对。"
    actual=next(iter(supported)) if key and len(supported)==1 else prefix
    if not actual and not missing and len(eligible)==1:
        actual=eligible[0]
    return dict(status=status,prefix=None if conflict else actual,intent_prefix=prefix,suggested_prefix=suggested,slots=slots,language_hint=language,
                matched_prefixes=sorted(matched),search_prefixes=[] if conflict else eligible,
                missing=missing,question=question)
