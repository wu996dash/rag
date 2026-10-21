# -*- coding: utf-8 -*-
import json, time
from pathlib import Path
from app.vectors import client, ensure_collection, upsert_articles
from app.parser import parse_law
c = client()
c.drop_collection("legal_articles")
print("旧 collection 已删除，重建 schema…")
ensure_collection()
d = json.loads(Path("data/laws.json").read_text(encoding="utf-8"))
t0 = time.time()
tot = 0
for k, v in d.items():
    hi = max(r["no"] for r in parse_law(k))
    n = upsert_articles(k, 1, hi)
    tot += n
    print(f'{k} 重建 {n} 行（{time.time()-t0:.0f}s）', flush=True)
print("全部重建完成:", tot)
