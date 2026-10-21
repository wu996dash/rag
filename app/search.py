"""检索三通道之 wiki 导航与向量召回 + 本地重排（D4）。"""
import re
from functools import lru_cache
from . import config
WIKI = config.REPO / "wiki"
def _bigrams(s):
    s = re.sub(r"[\s　,，。、；;：:（）()【】《》]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}
@lru_cache(maxsize=1)
def _concepts():
    out = []
    for p in sorted((WIKI / "concepts").glob("*.md")):
        if p.name == "README.md":
            continue
        txt = p.read_text(encoding="utf-8")
        mt = re.search(r"^title:\s*(.+)$", txt, re.M)
        title = mt.group(1) if mt else p.stem
        heads = " ".join(re.findall(r"^##+\s*(.+)$", txt, re.M))
        links = set(re.findall(r"concepts/([^)]+?)\.md", txt))
        out.append({"path": p, "name": p.name, "title": title,
                    "body": txt.split("---", 2)[-1].strip(),
                    "bg": _bigrams(title + heads), "links": links})
    return tuple(out)
def nav_select(question, topk=3):
    """M4：制度页向量导航优先，空库回退 bigram。"""
    try:
        from .conceptnav import nav_pages
        pages = nav_pages(question, topk + 3)
        if pages:
            concepts = [p for p in pages if not p["name"].startswith("指导性案例")][:topk]
            cases = [p for p in pages if p["name"].startswith("指导性案例")][:1]
            picked = concepts + cases
            return [{"name": p["name"], "title": p["title"], "body": p["body"],
                     "bg": set(), "links": set()} for p in picked]
    except Exception:
        pass
    qb = _bigrams(question)
    scored = []
    for c in _concepts():
        ov = len(qb & c["bg"]) / max(1, len(c["bg"]) | len(qb))
        if qb and ov > 0:
            scored.append((ov, c))
    scored.sort(key=lambda x: -x[0])
    picked, names = [], set()
    for _, c in scored[:topk]:
        picked.append(c); names.add(c["name"])
    for _, c in list(scored[:topk]):
        for l in c["links"]:
            for d in _concepts():
                if d["name"] == l and d["name"] not in names and len(picked) < topk + 2:
                    picked.append(d); names.add(d["name"])
    return picked

_ABBR = {v["law"]: v["abbr"] for v in config.SOURCES.values()}
def _wiki_status(law: str, article_no: str):
    abbr = _ABBR.get(law)
    if not abbr:
        return None
    leaf = f"{abbr}第{article_no}.md" if "条" in article_no else f"{abbr}第{article_no}条.md"
    fp = config.REPO / "wiki" / "articles" / leaf
    if not fp.exists():
        return None
    m = re.search(r"^status:\s*(\S+)\s*$", fp.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None

def vector_recall(question, k=12, include_abolished=False):
    """M4：稠密+稀疏 RRF 混合召回。"""
    from .vectors import hybrid_search
    hits = hybrid_search(question, k=k)
    if include_abolished:
        return hits
    # 时效权威在 wiki frontmatter（Milvus 标量仅作冗余快照）：默认只回现行有效
    out = []
    for h in hits:
        stt = _wiki_status(h.get("law", ""), h["article_no"])
        if stt in (None, "现行有效"):
            out.append(h)
    return out
@lru_cache(maxsize=1)
def _reranker():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    dev = getattr(config, "EMBED_DEVICE", "cpu")
    tok = AutoTokenizer.from_pretrained(config.RERANKER_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(config.RERANKER_PATH).to(dev)
    model.eval()
    return tok, model, dev
import threading
_RR_LOCK = threading.Lock()
def rerank(question, hits, top=5):
    import torch
    tok, model, dev = _reranker()
    def _txt(h):
        e = h.get("entity", h)
        return e["text"]
    docs = [_txt(h)[:400] for h in hits]
    scores = []
    with _RR_LOCK, torch.no_grad():
        for i in range(0, len(docs), 4):
            b = tok([(question, d) for d in docs[i:i + 4]], truncation=True,
                    max_length=1024, padding=True, return_tensors="pt").to(dev)
            lg = model(**b).logits.squeeze(-1)
            if lg.dim() == 0:
                lg = lg.unsqueeze(0)
            scores.extend(torch.sigmoid(lg).tolist())
    order = sorted(range(len(scores)), key=lambda j: -scores[j])
    out = []
    for j in order[:top]:
        e = hits[j].get("entity", hits[j])
        out.append({"law": e["law"], "article_no": e["article_no"], "text": e["text"],
                    "status": "现行有效", "score": round(float(scores[j]), 4)})
    return out