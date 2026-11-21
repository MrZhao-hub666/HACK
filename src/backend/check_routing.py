"""Read-only end-to-end regression using the project's printed catalogue."""
from unittest.mock import patch

from app.main import Inquiry, analyze, routing_index, status


def inquiry(*messages, **options):
    turns=[{"role":role,"text":text} for role,text in messages]
    return analyze(Inquiry(turns=turns,use_model=False,**options))


def check():
    routing_index(status()["revision"])
    # No detail query while awaiting a decision, including for a number present
    # in both printed catalogues. Measurements on the two editions can differ.
    with patch("app.main.catalog",side_effect=AssertionError("premature detail query")):
        reply=inquiry(("customer","WVA 29174"))
        assert reply["routing"]["matched_prefixes"]==["DCP","FCP"] and not reply["items"]
        english=inquiry(("customer","I need disc pads for an American truck"))
        assert english["routing"]["suggested_prefix"]=="FAP" and not english["routing"]["prefix"]
        conflict=inquiry(("customer","外贸 FMSI 4702a，是盘式"))
        assert conflict["routing"]["status"]=="conflict" and not conflict["items"]
        absent=inquiry(("customer","Export order. American truck, disc brake pads."))
        assert absent["routing"]["status"]=="no_catalog" and absent["routing"]["prefix"]=="FAP"
    for messages,prefix in [
        ([("customer","FMSI 4702a")],"FAG"),
        ([("customer","WVA 29174"),("sales",reply["question"]),("customer","后者")],"FCP"),
        ([("customer","外贸 WVA 29174"),("customer","改为国内")],"DCP"),
        ([("customer","美国车 FUG0001")],"FNG"),
        ([("customer","国内采购，鼓式"),("customer","说错了，是盘刹")],"DCP"),
        ([("customer","这单出口美国，给日本车用的鼓片")],"FJG"),
    ]:
        result=inquiry(*messages)
        assert result["routing"]["prefix"]==prefix,(messages,result["routing"])
        assert result["items"] and all(r["spec_id"][:3] in result["routing"]["search_prefixes"] for r in result["items"])
    print("PASS: ambiguous numbers, weak language hints, conflict, missing partition, corrections, country-neutral routing and detail gating")


if __name__=="__main__":
    check()
