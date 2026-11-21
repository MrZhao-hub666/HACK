from datetime import datetime, timedelta, timezone
import os

from .db import database
from .inbox import receive
from .models import Event
from .prospects import samples, save_company


def seed():
    if os.getenv("DEMO_DATA", "1") != "1":
        return
    with database(True) as db:
        if db.execute("SELECT 1 FROM cursors WHERE name='demo-seeded'").fetchone():
            return
    cases = [
        (
            "messenger",
            "Nadia · 演示维修厂",
            "Can you quote 100 sets of WVA 29289 for our workshop?",
            10,
        ),
        (
            "wechat_kf",
            "李师傅 · 演示车队",
            "我们车队想问一下，沃胜桥 11.5T 用什么型号？",
            8,
        ),
        (
            "facebook_comment",
            "Taller Norte · Demo",
            "¿Tienen catálogo de pastillas de freno para camiones?",
            5,
        ),
        (
            "facebook_form",
            "Demo Fleet Supply",
            "We need a price for 240 pieces, how soon could you deliver?",
            2,
        ),
    ]
    now = datetime.now(timezone.utc)
    for i, (ch, sender, body, age) in enumerate(cases):
        receive(
            Event(
                channel=ch,
                sender=sender,
                body=body,
                account="demo:showroom",
                event_id=f"initial-{i}",
                thread_key=f"seed-{i}",
                occurred_at=now - timedelta(hours=age),
            ),
            "模拟数据",
            False,
        )
    with database(True) as db:
        row = samples()[0]
        src, checked = row.pop("source"), row.pop("checked")
        save_company(db, row, src, checked)
        db.execute("INSERT OR IGNORE INTO cursors VALUES ('demo-seeded','1')")
