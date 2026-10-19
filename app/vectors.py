"""向量层 v2（M4）：legal_articles 双通道（稠密+稀疏，Milvus 原生 hybrid+RRF）+ 幂等主键。"""
from . import config
def client():
    from pymilvus import MilvusClient
    return MilvusClient(uri=config.MILVUS_URI, consistency_level="Strong")
def ensure_collection():
    from pymilvus import DataType
    c = client()
    if config.MILVUS_COLLECTION in c.list_collections():
        cols = {f["name"]: f["type"] for f in c.describe_collection(config.MILVUS_COLLECTION)["fields"]}
        if "sparse" in cols:
            return c
        c.drop_collection(config.MILVUS_COLLECTION)  # v1->v2 升级：开发期重建（数据由 ingest 幂等重建）
    s = c.create_schema(auto_id=False, enable_dynamic_field=False)
    s.add_field("id", DataType.INT64, is_primary=True)
    s.add_field("law", DataType.VARCHAR, max_length=128)
    s.add_field("article_no", DataType.VARCHAR, max_length=32)
    s.add_field("part", DataType.VARCHAR, max_length=64)
    s.add_field("chapter", DataType.VARCHAR, max_length=64)
    s.add_field("status", DataType.VARCHAR, max_length=32)
    s.add_field("effective_date", DataType.VARCHAR, max_length=32)
    s.add_field("source_path", DataType.VARCHAR, max_length=512)
    s.add_field("text", DataType.VARCHAR, max_length=20000)
    s.add_field("embedding", DataType.FLOAT_VECTOR, dim=1024)
    s.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
    ip = c.prepare_index_params()
    ip.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE",
                 params={"M": 16, "efConstruction": 200})
    ip.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
    c.create_collection(config.MILVUS_COLLECTION, schema=s, index_params=ip)
    return c
def upsert_articles(name, lo, hi):
    from .parser import parse_law
    from .m3encode import encode
    meta = config.SOURCES[name]
    recs = [r for r in parse_law(name) if lo <= r["no"] <= hi]
    texts = [f'{meta["abbr"]}第{r["no"]}条 {r["text"]}' for r in recs]
    ds, ss = encode(texts)
    rows = [{"id": meta["id_base"] + r["no"], "law": meta["law"], "article_no": str(r["no"]),
             "part": r["part"], "chapter": r["chapter"], "status": meta["status"],
             "effective_date": meta["effective"], "source_path": meta["path"],
             "text": t, "embedding": d, "sparse": sp} for r, t, d, sp in zip(recs, texts, ds, ss)]
    n = 0
    for i in range(0, len(rows), 64):
        ensure_collection().upsert(collection_name=config.MILVUS_COLLECTION, data=rows[i:i + 64])
        n += len(rows[i:i + 64])
        print(f"upserted {n}/{len(rows)}", flush=True)
    return n
def set_status(law_index, article_no, status):
    """维护回路：只改标量（status），稠密/稀疏向量原样回写。"""
    c = ensure_collection()
    pk = law_index + int(article_no)
    rows = c.get(collection_name=config.MILVUS_COLLECTION, ids=[pk],
                 output_fields=["law", "article_no", "part", "chapter", "status",
                                "effective_date", "source_path", "text", "embedding", "sparse"])
    if not rows:
        return False
    r = dict(rows[0]); r["status"] = status
    c.upsert(collection_name=config.MILVUS_COLLECTION, data=[r])
    return True
def hybrid_search(qtext, k=12, status_filter='status == "现行有效"'):
    """稠密+稀疏双通道 ANN + RRF 融合（D4 增强，修 G-038 类叙事题）。"""
    from pymilvus import AnnSearchRequest, RRFRanker
    from .m3encode import encode
    ds, ss = encode([qtext])
    reqs = [
        AnnSearchRequest(data=[ds[0]], anns_field="embedding",
                         param={"metric_type": "COSINE", "params": {"ef": 64}}, limit=k),
        AnnSearchRequest(data=[ss[0]], anns_field="sparse",
                         param={"metric_type": "IP"}, limit=k),
    ]
    res = ensure_collection().hybrid_search(
        collection_name=config.MILVUS_COLLECTION, reqs=reqs, ranker=RRFRanker(60),
        limit=k, filter=status_filter,
        output_fields=["law", "article_no", "text", "status"])
    out = []
    for h in res[0]:
        e = h["entity"]
        out.append({"law": e["law"], "article_no": e["article_no"], "text": e["text"],
                    "status": e["status"], "distance": round(float(h["distance"]), 4)})
    return out
def search(q, k=5):
    ds, _ = encode([q])
    c = client()
    res = c.search(collection_name=config.MILVUS_COLLECTION, data=[ds[0]], limit=k,
                   filter='status == "现行有效"', output_fields=["law", "article_no", "text"])
    return res[0]