"""制度页向量索引（legal_concepts）：把"叙事型提问 -> 制度页"变成语义匹配（修 G-038 的通道之一）。"""
from . import config
COL = "legal_concepts"
def ensure_index(rebuild=False):
    from pymilvus import DataType
    from .m3encode import encode
    from .vectors import client
    c = client()
    if COL in c.list_collections():
        if not rebuild:
            return c
        c.drop_collection(COL)
    s = c.create_schema(auto_id=False, enable_dynamic_field=False)
    s.add_field("id", DataType.INT64, is_primary=True)
    s.add_field("name", DataType.VARCHAR, max_length=256)
    s.add_field("title", DataType.VARCHAR, max_length=256)
    s.add_field("body", DataType.VARCHAR, max_length=8000)
    s.add_field("embedding", DataType.FLOAT_VECTOR, dim=1024)
    ip = c.prepare_index_params()
    ip.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE",
                 params={"M": 16, "efConstruction": 200})
    c.create_collection(COL, schema=s, index_params=ip)
    return c
def build(rebuild=True):
    import re as _re
    from .m3encode import encode
    c = ensure_index(rebuild=rebuild)
    pages = sorted((config.REPO / "wiki" / "concepts").glob("*.md"))
    pages += sorted((config.REPO / "wiki" / "cases").glob("*.md"))
    pages = [p for p in pages if p.name != "README.md"]
    rows = []
    for i, p in enumerate(pages):
        txt = p.read_text(encoding="utf-8")
        body = txt.split("---", 2)[-1].strip()
        mt = _re.search(r"^title:\s*(.+)$", txt, _re.M)
        title = mt.group(1) if mt else p.stem
        d, _ = encode([f"{title}\n{body[:700]}"])
        rows.append({"id": (1000 if p.parent.name == "concepts" else 5000) + i, "name": p.name, "title": title, "body": body[:6500], "embedding": d[0]})
    for i in range(0, len(rows), 32):
        c.upsert(collection_name=COL, data=rows[i:i + 32])
    return len(rows)
def nav_pages(question, k=3):
    from .m3encode import encode
    from .vectors import client
    c = client()
    if COL not in c.list_collections():
        return []
    d, _ = encode([question])
    res = c.search(collection_name=COL, data=[d[0]], limit=k,
                   output_fields=["name", "title", "body"])
    out = []
    for h in res[0]:
        e = h["entity"]
        out.append({"name": e["name"], "title": e["title"], "body": e["body"], "score": round(float(h["distance"]), 4)})
    return out