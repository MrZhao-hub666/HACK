"""Run a round-trip regression against an isolated schema and a temporary Excel copy."""
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from openpyxl import load_workbook
from psycopg import sql
from fastapi import HTTPException

from app import sync as bridge
from app.catalog import BOOK, FIELDS, db, init_db
from app.main import DraftSearch, catalog, inquiry_drafts
from app.match import Turn, match
from app.quotes import Quote, save_quote


def draft(request):
    with db() as conn:
        return save_quote(conn, request)

def run():
    schema="check_"+uuid.uuid4().hex
    with db() as admin, tempfile.TemporaryDirectory() as folder:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        admin.commit()
        original_options=os.environ.get("PGOPTIONS")
        os.environ["PGOPTIONS"]="-c search_path="+schema
        try:
            bridge.BOOK=Path(folder)/"check.xlsx"
            pending=admin.execute("SELECT snapshot FROM catalog_pending_excel WHERE id=1").fetchone()
            source=BOOK.with_name(pending["snapshot"]) if pending else BOOK
            shutil.copyfile(source,bridge.BOOK)
            init_db()
            bridge.sync()
            with db() as c:
                assert c.execute("select current_schema() as s").fetchone()["s"]==schema
            wb=load_workbook(bridge.BOOK)
            sheet=wb["产品规格"]
            records = [
                {"code":"TEST-10","name":"测试件","series":"测试系列","status":"企业已核","price":"2.35",
                 "material":"样例","sku":"TEST-SKU","currency":"USD","sale_unit":"套",
                 "price_source":"测试专用","valid_until":"2099-01-01","supplier_ref":"甲厂|OLD-06；乙厂|ALT-52"},
                {"code":"TEST-2","name":"另一型号","series":"测试系列","supplier_ref":"丙厂|OLD-06"},
                {"code":"TEST-10","name":"另一尺寸","series":"测试系列","thickness":"18"},
            ]
            for row in records:
                sheet.append([row.get(k) for k in FIELDS])
            wb.save(bridge.BOOK)
            bridge.sync()
            with db() as c:
                rows=c.execute("select * from catalog_spec where code='TEST-10'").fetchall()
                assert len(rows)==2 and rows[0]["spec_id"]!=rows[1]["spec_id"]
                key=next(r["spec_id"] for r in rows if r["sku"])
                q=draft(Quote(spec_id=key,quantity=3,unit="套"))
                assert q["total"]=="7.05"
                workspace=uuid.uuid4()
                request=Quote(spec_id=key,quantity=3,unit="套",request_key=uuid.uuid4(),inquiry_id=1,workspace=workspace)
                saved=draft(request)
                assert draft(request)["id"]==saved["id"]
                assert inquiry_drafts(DraftSearch(workspace=workspace,inquiries=[1]))[0]["id"]==saved["id"]
                assert inquiry_drafts(DraftSearch(workspace=uuid.uuid4(),inquiries=[1]))==[]
                try:
                    draft(request.model_copy(update={"quantity":4}))
                except HTTPException as exc:
                    assert exc.status_code==409
                else:
                    raise AssertionError("changed retry payload was accepted")
                items=catalog()
                turns=[Turn(role="customer",text="EQ1094加宽")]
                both=match(turns,items,False)
                assert both["count"]==2 and "国内版还是外贸版" in both["question"]
                for market,arc in (("国内","206"),("外贸","211")):
                    selected=match(turns,items,False,market)["items"]
                    assert len(selected)==1 and selected[0]["outer_arc"]==arc
                    spec_id=selected[0]["spec_id"]
                    quote=draft(Quote(spec_id=spec_id,market=market,quantity=1,unit="片"))
                    assert quote["market"]==market and quote["status"]=="待核价"
                    try:
                        draft(Quote(spec_id=spec_id,market="国内" if market=="外贸" else "外贸",quantity=1,unit="片"))
                    except HTTPException as e:
                        assert e.status_code==409
                    else:
                        raise AssertionError("Cross-market quote accepted")
                assert match([Turn(role="customer",text="完全未知型号")],items,False,"国内")["count"]==0
                for query,count in [("OLD-06",2),("甲厂 OLD-06",1),("ALT-52",1)]:
                    assert match([Turn(role="customer",text=query)],items,False)["count"]==count
                assert draft(Quote(spec_id=key,quantity=1,unit="片"))["status"]=="待核价"
                c.execute("update catalog_spec set material='复核样例' where spec_id=%s",(key,))
            bridge.sync()
            wb=load_workbook(bridge.BOOK)
            vals=list(wb["产品规格"].values)
            assert [r[0] for r in vals if r[1]=="测试系列"]==["TEST-2","TEST-10","TEST-10"]
            assert any("复核样例" in r for r in vals)
            wb["产品规格"].append(next(r for r in vals if key in r))
            wb.save(bridge.BOOK)
            try:
                bridge.sync()
            except ValueError as e:
                assert "重复" in str(e)
            else:
                raise AssertionError("Duplicate key accepted")
            with db() as c:
                assert c.execute("select count(*) as n from catalog_spec where code='TEST-10'").fetchone()["n"]==2
            print("PASS: XLSX to PostgreSQL, stable generated IDs, multi-spec codes, numeric ordering, DB to XLSX, draft totals and duplicate rollback")
        finally:
            bridge.BOOK=BOOK
            if original_options is None:
                os.environ.pop("PGOPTIONS",None)
            else:
                os.environ["PGOPTIONS"]=original_options
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

if __name__=="__main__":
    run()

