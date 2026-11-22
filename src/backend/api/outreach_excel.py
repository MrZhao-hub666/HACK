"""Build a true Excel workbook; all externally supplied values remain literal text."""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def worksheet(book, title, headers, rows, widths):
    sheet = book.create_sheet(title)
    sheet.append(headers)
    for row_index, row in enumerate(rows, start=2):
        for column, value in enumerate(row, start=1):
            if isinstance(value, str):
                text = (
                    ILLEGAL_CHARACTERS_RE.sub("", value)
                    .replace("\ufffe", "")
                    .replace("\uffff", "")
                )
                cell = sheet.cell(row_index, column, text)
                cell.data_type = "s"
                if headers[column - 1] in {
                    "证据链接",
                    "来源链接",
                    "官方网站",
                    "企业社媒",
                } and text.startswith(("https://", "http://")):
                    cell.hyperlink = text
                    cell.style = "Hyperlink"
            else:
                sheet.cell(row_index, column, value)
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="245C64")
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 24
    for i, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    return sheet


def buyer_workbook(data, grade):
    buyers = {
        r["id"]: r
        for r in data["buyers"]
        if grade == "全部" or (r["grade"] or "待评级") == grade
    }
    book = Workbook()
    book.remove(book.active)
    worksheet(
        book,
        "买家分级",
        [
            "档案号",
            "企业名称",
            "市场",
            "业务角色",
            "产品匹配度",
            "采购能力",
            "官方网站",
            "企业社媒",
            "档案联系方式",
            "负责人",
        ],
        (
            (
                r["id"],
                r["name"],
                r["country"],
                r["kind"],
                r["grade"] or "待评级",
                r["procurement"],
                r["website"],
                r["social"],
                r["contact"],
                r["owner"],
            )
            for r in buyers.values()
        ),
        [12, 34, 17, 17, 15, 18, 38, 42, 36, 18],
    )
    worksheet(
        book,
        "核实依据",
        [
            "档案号",
            "企业名称",
            "来源",
            "届次",
            "等级",
            "意图",
            "原始标题",
            "来源链接",
            "发布方",
            "发布日期",
            "来源原句",
            "分级依据",
            "核实人",
            "核实时间（UTC）",
        ],
        (
            (
                r["company_id"],
                buyers[r["company_id"]]["name"],
                r["source"],
                r["edition"],
                r["fit"],
                r["intent"],
                r["title"],
                r["url"],
                r["author"],
                r["published"],
                r["quote"],
                r["reason"],
                r["reviewer"],
                r["updated"],
            )
            for r in data["evidence"]
            if r["company_id"] in buyers and r["verdict"] == "已核实"
        ),
        [12, 32, 17, 15, 9, 18, 38, 64, 23, 16, 64, 46, 15, 30],
    )
    worksheet(
        book,
        "采购联系渠道",
        [
            "档案号",
            "企业名称",
            "类型",
            "联系方式",
            "归属（人员或部门）",
            "证据链接",
            "核实人",
            "更新时间（UTC）",
        ],
        (
            (
                r["company_id"],
                buyers[r["company_id"]]["name"],
                r["kind"],
                r["value"],
                r["holder"],
                r["url"],
                r["reviewer"],
                r["updated"],
            )
            for r in data["contacts"]
            if r["company_id"] in buyers
        ),
        [12, 32, 18, 40, 34, 64, 15, 30],
    )
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
