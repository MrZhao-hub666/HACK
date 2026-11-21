"""Recognize both catalogues locally. Coordinates use the 2800px page renders."""
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

BASE = Path(__file__).resolve().parents[3] / "docs/materials"
ENGINE = None

def recognize(file):
    global ENGINE
    target = BASE / "ocr" / (file.stem + ".json")
    if target.exists():
        return
    cv2.setNumThreads(1)
    if ENGINE is None:
        ENGINE = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, use_angle_cls=False)
    image = cv2.imdecode(np.fromfile(file,dtype=np.uint8),1)
    h,w=image.shape[:2]
    words=[]
    for x0,x1 in [(0,w//2),(w//2,w)]:
        # Keep the original spread geometry, including repeated column headers.
        tile=image[:,x0:x1]
        hits,_=ENGINE(tile,use_cls=False,max_side_len=2200)
        for box,text,score in hits or []:
            points=np.array(box)
            box=[int(points[:,0].min()+x0),int(points[:,1].min()),int(points[:,0].max()+x0),int(points[:,1].max())]
            words.append([*box,text,round(score,3)])
    target.write_text(json.dumps(words,ensure_ascii=False),encoding="utf-8")
    print(file.stem,len(words),flush=True)

if __name__=="__main__":
    (BASE/"ocr").mkdir(exist_ok=True)
    paths=sorted((BASE/"pages").glob("*.jpg"))
    paths.sort(key=lambda p: (p.stem not in {"en-12","en-13","en-06","cn-10","cn-21","en-30"}, p.stem))
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(recognize,paths))

