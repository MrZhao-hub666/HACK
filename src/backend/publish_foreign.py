"""Publish the editable country tables to one illustrated workbook in PDF order."""
import base64
import io
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from openpyxl import load_workbook

from app.archive import MATERIALS
from app.foreign import BOOK, COUNTRIES, LABEL, fields
from app.sync import digest

def sheets_from_db(tables):
    pages={}
    sheets=[]
    for area,items in tables.items():
        keys=fields(area)
        rows=[]
        images=[]
        for r in items:
            page=r["page_key"]
            if page not in pages:
                with Image.open(MATERIALS/"pages"/(page+".jpg")) as src:
                    pages[page]=src.convert("L")
            im=pages[page].crop(r["picture_box"])
            im.thumbnail((125,54),Image.Resampling.LANCZOS)
            buf=io.BytesIO()
            im.save(buf,"PNG")
            images.append(dict(b64=base64.b64encode(buf.getvalue()).decode(),width=im.width,height=im.height))
            rows.append([None if k=="picture" else r[k] for k in keys])
        sheets.append(dict(area=area,name=COUNTRIES[area][0],keys=keys,headers=[LABEL[k] for k in keys],
                           rows=rows,images=images))
    return sheets

def verify(path,sheets):
    book=load_workbook(path)
    try:
        assert book.sheetnames==[s["name"] for s in sheets]
        for s in sheets:
            ws=book[s["name"]]
            assert list(ws.values)==[tuple(s["headers"]),*map(tuple,s["rows"])],s["name"]
            assert len(ws._images)==len(s["rows"]),s["name"]
            assert len(ws.tables)==1,s["name"]
    finally:
        book.close()

def render(tables, expected_file_hash):
    export_book(BOOK, sheets_from_db(tables), expected_file_hash)

def export_book(book, sheets, expected_file_hash):
    runtime=Path(os.environ.get("CATALOG_NODE_RUNTIME",Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/node"))
    with TemporaryDirectory(dir=book.parent) as work:
        payload=Path(work)/"input.json"
        payload.write_text(json.dumps(sheets,ensure_ascii=False),encoding="utf8")
        output=Path(work)/"export.xlsx"
        exe=runtime/"bin"/("node.exe" if os.name=="nt" else "node")
        subprocess.run([exe,Path(__file__).parent/"import_tools/foreign_excel.mjs",
                        payload,output,runtime/"node_modules"],check=True)
        verify(output,sheets)
        if (digest(book.read_bytes()) if book.exists() else None)!=expected_file_hash:
            raise ValueError("工作簿在导出时发生变化，请重新同步")
        output.replace(book)
        for sheet in sheets:
            print(sheet["name"],len(sheet["rows"]),sheet["rows"][0][0],sheet["rows"][-1][0])

if __name__=="__main__":
    from app.foreign_sync import synchronize
    print(synchronize())
