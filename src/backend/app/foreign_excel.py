"""Publish the editable country tables to one illustrated workbook in PDF order."""
import base64
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as SheetImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

from .archive import MATERIALS
from .foreign import BOOK, COUNTRIES, LABEL, fields
from .sync import digest

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
    with TemporaryDirectory(dir=book.parent) as work:
        output=Path(work)/"export.xlsx"
        wb = Workbook()
        wb.remove(wb.active)
        widths = {"wva":34,"bfmc":17,"oem":28,"item":35,"application":38,"picture":22,
                  "size_raw":26,"rivet_dia":28,"length_mm":22}
        for spec in sheets:
            ws = wb.create_sheet(spec["name"])
            ws.append(spec["headers"])
            ws.freeze_panes = "A2"
            ws.row_dimensions[1].height = 28
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="18475A")
            for index, key in enumerate(spec["keys"], 1):
                ws.column_dimensions[get_column_letter(index)].width = widths.get(key,16)
            picture_col = get_column_letter(spec["keys"].index("picture") + 1)
            for number, (values, thumbnail) in enumerate(zip(spec["rows"],spec["images"],strict=True), 2):
                ws.append(values)
                for cell in ws[number]:
                    if cell.value is not None:
                        cell.data_type = "s"
                    cell.number_format = "@"
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                ws.row_dimensions[number].height = 44
                image = SheetImage(io.BytesIO(base64.b64decode(thumbnail["b64"])))
                ws.add_image(image, f"{picture_col}{number}")
            table = Table(displayName="Country_"+spec["area"], ref=ws.dimensions)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2",showRowStripes=True)
            ws.add_table(table)
        wb.save(output)
        wb.close()
        verify(output,sheets)
        if (digest(book.read_bytes()) if book.exists() else None)!=expected_file_hash:
            raise ValueError("工作簿在导出时发生变化，请重新同步")
        output.replace(book)
        for sheet in sheets:
            print(sheet["name"],len(sheet["rows"]),sheet["rows"][0][0],sheet["rows"][-1][0])
