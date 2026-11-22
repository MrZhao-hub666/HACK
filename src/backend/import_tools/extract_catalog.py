"""Extract source observations from grid geometry; retain coordinates and source readings."""
import json
import re
from collections import Counter
from layout import BASE, Page
from appendix import append

rows=[]
issues=[]
def compact(s):
    return re.sub(r"\s+","",s or "").replace("（","(").replace("）",")")
def dims(s):
    separate=re.fullmatch(r"(\d+[×xX*]\d+[×xX*]\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",s)
    if separate:s=f"{separate[1]}({separate[2]})"
    triples=re.findall(r"\d+(?:\.\d+)?[×xX*]\d+(?:\.\d+)?[×xX*][\d./]+",s)
    if len(triples)>1 and compact("".join(triples))==compact(s):
        return [v for triple in triples for v in dims(triple)]
    if compact(s)=="157×85×16(14.5)18":s="157×85×16(14.5)(18)"
    m=re.fullmatch(r"(\d+(?:\.\d+)?)[×xX*](\d+(?:\.\d+)?)[×xX*]([\d./]+)((?:\([\d./]+\))*)",compact(s))
    if not m:return []
    a,b,c,extra=m.groups()
    return [(a,b,d) for d in [c,*re.findall(r"\(([\d./]+)\)",extra)]]
def line_groups(ls,gap=6):
    out=[]
    for v in ls:
        if not out or v-out[-1]>gap:out.append(v)
    return out
def add(p,box,**data):
    x,y,X,Y=map(int,box)
    pno=int(p.key[-2:])
    market={"en":"外贸","cn":"国内"}[p.key[:2]]
    item=dict(doc=p.key[:2],page=pno,box=[x,y,X,Y],market=market,**data)
    rows.append(item)
    return item
def grid_cells(p,xs,y,Y):
    return [p.text(a,y,b,Y).strip() for a,b in zip(xs,xs[1:])]

def export(p):
    for side in range(1 if p.key=="en-12" else 2):
        off=side*1400
        # The first column carries the local part number. Find the outer grid
        # using long horizontal rules to avoid characters and illustration lines.
        bounds=p.ys(off+115,off+1190,.90)
        for y,Y in zip(bounds,bounds[1:]):
            if y<180 or Y>1810 or not 45<=Y-y<=180:continue
            xs=[x for x in p.xs(y+5,Y-5,.86) if off+20<x<off+1380]
            xs=line_groups(xs)
            if len(xs)<9:continue
            c=grid_cells(p,xs,y,Y)
            for i in range(len(c)):
                if i!=1:c[i]=p.cell(xs[i],y,xs[i+1],Y)
            code=compact(c[0]).upper().strip("☆★")
            if not re.fullmatch(r"GYS-?\d{2,3}[A-Z]?",code):
                issues.append((p.key,y,"GYS号待核",c[0]))
            if len(c)==12:
                keys="code picture wva bfmc outer_arc inner_arc width thickness arc_value holes rivet brand".split()
            elif len(c)==11:
                keys="code picture fmsi outer_arc inner_arc width thickness arc_value holes rivet brand".split()
                headings=p.items(off,0,off+580,y)
                latest=[w for w in headings if w[4].upper() in {"OEM","FMSI","ITEM"}]
                keys[2]={"OEM":"oe_ref","FMSI":"fmsi","ITEM":"catalog_ref"}[latest[-1][4].upper()] if latest else "catalog_ref"
            else:
                issues.append((p.key,y,"外贸列数",len(c),c))
                keys=["code"]+["field"+str(i) for i in range(1,len(c))]
            data=dict(zip(keys,c));data.pop("picture",None)
            data["code"]=code
            if code in {"GYS-076","GYS-077"}:data["brand"]="FORD,IVECO"
            group=[r for r in p.items(off,0,off+275,y) if r[4].upper() in {"EUROPEAN","AMERICAN","JAPANESE","KOREA","CHINESE","EXISTING"}]
            add(p,(xs[0],y,xs[-1],Y),series="GYS（编号组）",section=group[-1][4] if group else "",kind="鼓式",name=code,**data)

def domestic_cards(p):
    bars=p.bars("blue",(280,530,16,44))
    for x,y,w,h in bars:
        if y<220 or (p.key=="en-12" and x<1400):continue
        name=p.text(x-7,y-58,x+w,y-2)
        # First data column has a horizontal rule for every dimension variant.
        ls=p.ys(x+15,x+int(w*.34),.90)
        top=min((k for k in ls if y+h-9<=k<=y+h+5),key=lambda k:abs(k-(y+h)),default=y+h)
        edges=[top]
        for k in ls:
            if k<=top+7:continue
            if k-edges[-1]>68:break
            if k-edges[-1]>45 and not (p.vertical[edges[-1]+3:k-2,x-6:x+6].any(axis=1).mean()>.80):break
            if k-edges[-1]>=13:edges.append(k)
        if len(edges)<2:
            issues.append((p.key,x,y,"卡片缺行"));edges.append(top+30)
        X=x+w
        divisions=[x,x+round(.39*w),x+round(.535*w),x+round(.725*w),X]
        base=[r for r in p.words if (x//1400)*1400<=r[0]<(x//1400+1)*1400 and r[1]<y and ("系列" in r[4] or r[4]=="其他")]
        series=base[-1][4] if base else ""
        # For merged cells use the actual horizontal borders in that column.
        for j,(a,b) in enumerate(zip(edges,edges[1:])):
            cells=[]
            for l,r in zip(divisions,divisions[1:]):
                separators=p.ys(l+5,r-5,.84)
                bounds=[top]+[k for k in separators if top+6<k<edges[-1]-6]+[edges[-1]]
                parts=[p.cell(l,u,r,v) for u,v in zip(bounds,bounds[1:]) if min(b,v)-max(a,u)>4]
                cells.append("；".join(dict.fromkeys(s for s in parts if s)))
            size,holes,taper,rivet=cells
            if p.key=="en-20" and (x,a)==(1657,869): size="202×155×17.5/19.5"
            v=dims(size)
            if not v:issues.append((p.key,x,a,"尺寸待核",size))
            data=dict(outer_arc=v[0][0],width=v[0][1],thickness=v[0][2]) if v else {}
            add(p,(x-5,a,X,b),card_box=[max(x//1400*1400,x-270),max(0,y-70),X+3,edges[-1]+6],
                name=name,series=series,kind="鼓式",size_raw=size,holes=holes,taper=taper,rivet=rivet,**data)

def cn_table(p):
    for half in range(2):
        if half==0 and p.key=="cn-10" or half==1 and p.key=="cn-20":continue
        of=half*1400
        # Tables contain two five-column grids per printed page.
        for col in range(2):
            probe=of+130+col*630
            edges=p.ys(probe-20,probe+50,.90)
            for y,Y in zip(edges,edges[1:]):
                if not (270<y<1775 and Y<=1795 and 85<Y-y<160):continue
                ls=[x for x in p.xs(y+5,Y-5,.85) if of+15<x<of+1390]
                left=max((x for x in ls if x<probe),default=None)
                if left is None:continue
                xs=[left]+[x for x in ls if left+5<x<left+660]
                xs=line_groups(xs)[:6]
                if len(xs)!=6:
                    issues.append((p.key,col,y,"中文表缺线",xs));continue
                name,size,holes,fit=[p.cell(xs[i],y,xs[i+1],Y) for i in (0,1,2,4)]
                if not any((name,size,holes,fit)):continue
                title=p.text(xs[0],152,xs[-1],238)
                variants=dims(size)
                # The parenthetical 18,20 is not identified as a separate SKU.
                # Preserve its printed meaning rather than interpreting the pair.
                if compact(size)=="195×220×10/18.5(18,20)":
                    variants=[("195","220","10/18.5 (18,20)")]
                for a,c,d in variants or [(None,None,None)]:
                    add(p,(xs[0],y,xs[-1],Y),name=compact(name),series=title,kind="鼓式",size_raw=size,
                        outer_arc=a,width=c,thickness=d,holes=holes,fit_notes=fit)
                if not variants: issues.append((p.key,probe,y,"中文尺寸",size))
def cn_disc(p):
    for x,y,w,h in p.bars("orange",(70,140,60,175)):
        if y<205:continue
        X=x+int(w*5.05)
        ls=p.ys(x+7,x+w-10)
        ls=[v for v in ls if y-6<=v<=y+h+6]
        if len(ls)<3:ls=[y,y+28,y+56,y+h]
        name=p.text(x+w,ls[0],X,ls[1])
        size=p.text(x+w,ls[1],X,ls[2])
        fit=p.text(x+w,ls[2],X,max(y+h,ls[-1])+8)
        add(p,(x,y,X,y+h),card_box=[x,max(145,y-245),X,y+h+5],name=name,kind="盘式",series="盘式刹车片",size_raw=size,fit_notes=fit)
def en_disc(p):
    for col,probe in enumerate((125,750,1510,2140)):
        ys=p.ys(probe,probe+50)
        for y,Y in zip(ys,ys[1:]):
            if y<275 or Y>1800 or not 80<Y-y<140:continue
            xs=p.xs(y+5,Y-5,.90)
            left=max(k for k in xs if k<probe)
            xs=[left]+[k for k in xs if left+6<k<left+680][:4]
            code,wva,size=[p.cell(xs[i],y,xs[i+1],Y) for i in range(3)]
            if not any((code,wva,size)):continue
            code=compact(code); refs=re.findall(r"(?<!\d)\d{5}(?!\d)",wva)
            add(p,(xs[0],y,xs[-1],Y),name=code,code=code,kind="盘式",series="GY（编号组）",wva="；".join(refs),reference_raw=wva,size_raw=size)
def extract():
    for n in range(6,35):
        p=Page(f"en-{n:02}")
        if n<=12:export(p)
        if 12<=n<=29:domestic_cards(p)
        if n==30:en_disc(p)
        if n>=31:append(p,add)
    for n in range(10,24):
        p=Page(f"cn-{n:02}")
        if n==10:
            for i,name in enumerate(("金钻王","皇冠","富华通","耐磨之星","耐磨王")):
                y=305+i*255
                add(p,(60,y,1350,y+240),name=name,series="冠隆优品系列",kind="配方系列",
                    fit_notes=p.text(446,y+73,1350,y+235))
        if n<=20:cn_table(p)
        else:cn_disc(p)
    (BASE/"catalog-observations.json").write_text(json.dumps(rows,ensure_ascii=False),encoding="utf-8")
    print(Counter((r["doc"],r["page"]) for r in rows))
    (BASE/"ocr"/"layout-review.json").write_text(json.dumps(issues,ensure_ascii=False),encoding="utf-8")

if __name__=="__main__":
    extract()

