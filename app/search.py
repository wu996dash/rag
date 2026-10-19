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
def vector_recall(question, k=20):
    from .vectors import search
    return search(question, k=k)
@lru_cache(maxsize=1)
def _reranker():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(config.RERANKER_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(config.RERANKER_PATH)
    model.eval()
    return tok, model
def rerank(question, hits, top=5):
    import torch
    tok, model = _reranker()
    docs = [h["entity"]["text"][:800] for h in hits]
    scores = []
    with torch.no_grad():
        for i in range(0, len(docs), 4):
            b = tok([(question, d) for d in docs[i:i + 4]], truncation=True,
                    max_length=1024, padding=True, return_tensors="pt")
            lg = model(**b).logits.squeeze(-1)
            if lg.dim() == 0:
                lg = lg.unsqueeze(0)
            scores.extend(torch.sigmoid(lg).tolist())
    order = sorted(range(len(scores)), key=lambda j: -scores[j])
    out = []
    for j in order[:top]:
        e = hits[j]["entity"]
        out.append({"law": e["law"], "article_no": e["article_no"], "text": e["text"],
                    "status": "现行有效", "score": round(float(scores[j]), 4)})
    return out