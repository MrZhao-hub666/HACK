import json
import re
from pathlib import Path
from functools import lru_cache
import cv2
import numpy as np

BASE=Path(__file__).resolve().parents[3]/"docs/materials"
def runs(mask):
    indices=np.flatnonzero(mask)
    if not len(indices): return []
    return [(int(g[0])+int(g[-1]))//2 for g in np.split(indices,np.where(np.diff(indices)>1)[0]+1)]

def read(file):
    return cv2.imdecode(np.fromfile(file,dtype=np.uint8),1)

class Page:
    def __init__(self,key):
        self.key=key
        self.img=read(BASE/"pages"/(key+".jpg"))
        self.h,self.w=self.img.shape[:2]
        g=cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        bw=cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,21,9)
        self.horizontal=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,28),np.uint8))
        self.vertical=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((20,1),np.uint8))
        self.words=json.loads((BASE/"ocr"/(key+".json")).read_text(encoding="utf8"))
    def ys(self,x1,x2,ratio=.82):
        return runs((self.horizontal[:,int(x1):int(x2)]>0).mean(axis=1)>ratio)
    def xs(self,y1,y2,ratio=.75):
        return runs((self.vertical[int(y1):int(y2),:]>0).mean(axis=0)>ratio)
    def items(self,x1,y1,x2,y2):
        return [r for r in self.words if x1<=(r[0]+r[2])/2<x2 and y1<=(r[1]+r[3])/2<y2]
    def text(self,*box):
        return ' '.join(r[4] for r in sorted(self.items(*box),key=lambda r:(round((r[1]+r[3])/14),r[0])))
    def cell(self,x,y,X,Y):
        # Whole-page OCR can fuse a model label, a dimension and a hole count.
        # Re-read just the physical cell when a detection crosses its border.
        crossing=any(y<(a[1]+a[3])/2<Y and min(a[2],X)-max(a[0],x)>4 and
                     (a[0]<x-4 or a[2]>X+4) for a in self.words)
        plain=self.text(x,y,X,Y)
        if not crossing and plain:
            return plain
        tile=self.img[y+3:Y-3,x+3:X-3]
        if tile.size==0:return plain
        ink=cv2.cvtColor(tile,cv2.COLOR_BGR2GRAY)<147
        line=np.flatnonzero(ink.sum(axis=1)>=2)
        if not len(line):return ""
        strips=[]
        for group in np.split(line,np.where(np.diff(line)>4)[0]+1):
            if group[-1]-group[0]<6:continue
            a,b=group[0],group[-1]+1
            xx=np.flatnonzero(ink[a:b].any(axis=0))
            crop=tile[max(0,a-2):min(len(tile),b+2),max(0,xx[0]-2):xx[-1]+3]
            strips.append(cv2.copyMakeBorder(crop,3,3,3,3,cv2.BORDER_CONSTANT,value=(255,255,255)))
        if not strips:return plain
        return " ".join(t for t,s in recognizer()(strips)[0] if s>.55)
    def bars(self,lo,hi):
        b,g,r=cv2.split(self.img)
        if lo=="blue": m=(b>170)&(g>100)&(r<100)&((g.astype(int)-r)>65)
        if lo=="orange": m=(r>175)&(g>65)&(g<218)&(b<150)&((r.astype(int)-b)>75)
        mask=m.astype(np.uint8)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,14),np.uint8))
        ct,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        return sorted([tuple(map(int,(x,y,w,h))) for x,y,w,h in map(cv2.boundingRect,ct)
                       if hi[0]<=w<=hi[1] and hi[2]<=h<=hi[3]],key=lambda z:(z[1],z[0]))

@lru_cache(maxsize=1)
def recognizer():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1).text_rec

