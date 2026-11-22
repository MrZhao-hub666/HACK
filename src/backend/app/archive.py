"""Restore the immutable source-page and source-row indexes on a fresh database."""
import json
from hashlib import file_digest, sha256
from psycopg.types.json import Jsonb
from .catalog import DOCS, PACK

MATERIALS=DOCS/"materials"
MANIFEST=MATERIALS/"catalog-evidence.json"
SOURCE_HASHES=MATERIALS/"catalog-source-hashes.json"
PDFS={"en":"kooying catalog.pdf","cn":"冠隆产品册.pdf"}
MARKETS={"en":"外贸","cn":"国内"}

def page_use(doc,n):
    if doc=="en":
        if n<6:return "企业介绍及包装资料"
        if n<12:return "外贸鼓片"
        if n==12:return "外贸鼓片及东风系列"
        if n<30:return "外贸鼓片规格卡"
        return {30:"盘式刹车片",31:"摩擦材料及衬带",32:"制动蹄",33:"制动蹄及套装",34:"制动蹄及修理包"}[n]
    if n<10:return "企业、研发、生产及营销资料"
    if n==10:return "冠隆优品及东风系列"
    if n<20:return "国内鼓片及适配车型"
    if n==20:return "空白预留表及安装示意"
    return "国内盘片及适配车型"

def restore(conn):
    if not MANIFEST.exists():return
    raw=MANIFEST.read_bytes()
    revision=sha256(raw).hexdigest()
    conn.execute("CREATE TABLE IF NOT EXISTS catalog_archive_version(id int PRIMARY KEY, revision text NOT NULL)")
    state=conn.execute("SELECT revision FROM catalog_archive_version WHERE id=1").fetchone()
    if state and state["revision"]==revision:return
    data=json.loads(raw)
    hashes = json.loads(SOURCE_HASHES.read_text(encoding="utf8")) if SOURCE_HASHES.is_file() else {}
    with conn.cursor() as cur:
        pages=[]
        for doc,count in (("en",34),("cn",23)):
            file=PDFS[doc]
            source = PACK / file
            if source.is_file():
                with source.open("rb") as stream:
                    fingerprint = file_digest(stream, "sha256").hexdigest()
            else:
                fingerprint = hashes.get(file, "")
                if len(fingerprint) != 64 or len(bytes.fromhex(fingerprint)) != 32:
                    raise ValueError(f"缺少目录 PDF 或来源指纹：{file}")
            for n in range(1,count+1):
                key=f"{doc}-{n:02}"
                words=json.loads((MATERIALS/"ocr"/(key+".json")).read_text(encoding="utf8"))
                pages.append((key,file,n,fingerprint,page_use(doc,n),Jsonb(words)))
        cur.executemany("""INSERT INTO catalog_page VALUES(%s,%s,%s,%s,%s,%s)
            ON CONFLICT(page_key) DO UPDATE SET pdf_sha256=excluded.pdf_sha256,ocr=excluded.ocr,purpose=excluded.purpose""",pages)
        cur.execute("DELETE FROM catalog_observation")
        cur.executemany("INSERT INTO catalog_observation VALUES (%s,%s,%s,%s,%s)",
            [(r["id"],r["page_key"],r["spec_key"],r["box"],Jsonb(r["reading"])) for r in data])
    conn.execute("""INSERT INTO catalog_archive_version VALUES (1,%s) ON CONFLICT(id)
                    DO UPDATE SET revision=excluded.revision""",(revision,))

