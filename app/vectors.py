"""BGE-M3 稠密嵌入 + Milvus 读写（DECISIONS.md D2/D3/D4）。"""
import threading
from . import config
_model = None
_tok = None
_lock = threading.Lock()
def _lazy():
    global _model, _tok
    with _lock:
        if _model is None:
            import torch
            from transformers import AutoModel, AutoTokenizer
            _tok = AutoTokenizer.from_pretrained(config.EMBED_MODEL_PATH)
            _model = AutoModel.from_pretrained(config.EMBED_MODEL_PATH)
            _model.eval()
    return _model, _tok
def embed(texts):
    """CLS pooling + L2 归一（bge-m3 稠密配方）。"""
    import numpy as np, torch
    m, tok = _lazy()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 16):
            batch = texts[i:i+16]
            enc = tok(batch, padding=True, truncation=True, max_length=1024, return_tensors="pt")
            hs = m(**enc).last_hidden_state[:, 0]
            v = torch.nn.functional.normalize(hs, dim=1).numpy().astype("float32")
            out.extend(v.tolist())
            print(f"embedded {min(i+16,len(texts))}/{len(texts)}", flush=True)
    return out
def client():
    from pymilvus import MilvusClient
    return MilvusClient(uri=config.MILVUS_URI)
def ensure_collection():
    from pymilvus import DataType, MilvusClient
    c = client()
    if config.MILVUS_COLLECTION in c.list_collections():
        return c
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
    ip = c.prepare_index_params()
    ip.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE",
                 params={"M": 16, "efConstruction": 200})
    c.create_collection(config.MILVUS_COLLECTION, schema=s, index_params=ip)
    return c
def upsert_articles(name, lo, hi):
    from .parser import parse_law
    meta = config.SOURCES[name]
    recs = [r for r in parse_law(name) if lo <= r["no"] <= hi]
    texts = [f'{meta["abbr"]}第{r["no"]}条 {r["text"]}' for r in recs]
    vecs = embed(texts)
    rows = [{"id": meta["id_base"] + r["no"], "law": meta["law"], "article_no": str(r["no"]), "part": r["part"],
             "chapter": r["chapter"], "status": meta["status"],
             "effective_date": meta["effective"], "source_path": meta["path"],
             "text": t, "embedding": v} for r, t, v in zip(recs, texts, vecs)]
    c = ensure_collection()
    c.upsert(collection_name=config.MILVUS_COLLECTION, data=rows)
    return len(rows)
def search(q, k=5):
    c = client()
    qv = embed([q])[0]
    res = c.search(collection_name=config.MILVUS_COLLECTION, data=[qv], limit=k,
                   filter='status == "现行有效"',
                   output_fields=["law", "article_no", "text"])
    return res[0]