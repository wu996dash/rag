"""司法解释《诉讼时效规定》（2020修正）加载/建页/嵌入。md 源含网页残留，本模块负责清洗。"""
import json, re
from datetime import date
from pathlib import Path
from . import config

KEY = "诉讼时效规定"

def meta():
    return config.SOURCES[KEY]

def load_articles():
    cache = config.REPO / "vectors" / "jieshi_parsed.json"
    if cache.exists():
        return [(int(n), t) for n, t in json.loads(cache.read_text(encoding="utf-8"))]
    raise FileNotFoundError("先运行解析生成 vectors/jieshi_parsed.json")

def build_pages():
    m = meta()
    arts = load_articles()
    out = config.REPO / "wiki" / "articles"
    made = 0
    for no, text in arts:
        fn = f'{m["abbr"]}第{no}条.md'
        path = out / fn
        if path.exists():
            continue
        org = "\n".join(f'> 【原文】 {ln}' for ln in text.splitlines() if ln.strip())
        page = f'''---
id: article/{m["slug"]}-{no}
type: article
title: {m["abbr"]}第{no}条
law: {m["law"]}
article_no: "{no}"
effective_date: 2020-12-23
status: {m["status"]}
sources:
  - {m["path"]}
updated_at: {date.today().isoformat()}
---

## 原文

{org}

## 款项拆解

（司法解释条款：假定条件→规范效果；深度拆解按 SCHEMA §1.1 于精编轮完成）

## 关联制度页

[诉讼时效](../concepts/诉讼时效.md)

## 时效说明

2008-08-11 审委会通过制定；2020-12-23 审委会修正（民法典配套清理）。公布/施行具体日期以公报文号文本为准（登记待核）。
'''
        path.write_text(page, encoding="utf-8")
        made += 1
    return {"made": made, "skipped": len(arts) - made}

def upsert():
    from .m3encode import encode
    from .vectors import ensure_collection, client
    m = meta()
    arts = load_articles()
    texts = [f'{m["abbr"]}第{no}条 {t}' for no, t in arts]
    ds, ss = encode(texts)
    rows = [{"id": m["id_base"] + no, "law": m["law"], "article_no": str(no),
             "part": "司法解释", "chapter": m["abbr"], "status": m["status"],
             "effective_date": "2020-12-23", "source_path": m["path"],
             "text": t, "embedding": d, "sparse": sp}
            for (no, _), t, d, sp in zip(arts, texts, ds, ss)]
    ensure_collection().upsert(collection_name=config.MILVUS_COLLECTION, data=rows)
    return len(rows)