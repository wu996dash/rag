"""问答流水线事件生成器（API/WS 共用）：qa_graph 六步的可流式消费版本。
与 CLI/评测共用底层函数，rid 串联单次请求的全部日志行。"""
import time
from . import config, log
L = log.get("pipeline")
def _norm_law(law: str) -> str:
    for v in config.SOURCES.values():
        if v["law"] == law or v["abbr"] in law:
            return v["abbr"]
    return law[:6] if law else "?"
def events(question: str, history=None, rid: str = "-"):
    from .search import nav_select, vector_recall, rerank
    from .answer import assemble, _messages
    from .query_rewrite import rewrite
    from .llm import chat_stream
    from .answer import verify
    t0 = time.time()
    t = time.time(); eq = rewrite(question, history)
    yield {"type": "stage", "stage": "rewrite", "ms": int((time.time()-t)*1000), "detail": eq}
    t = time.time(); nav = nav_select(eq)
    yield {"type": "stage", "stage": "nav", "ms": int((time.time()-t)*1000), "pages": [p["title"] for p in nav]}
    t = time.time(); hits = vector_recall(eq)
    yield {"type": "stage", "stage": "recall", "ms": int((time.time()-t)*1000),
           "n": len(hits), "items": [{"law": _norm_law(h["law"]), "no": h["article_no"]} for h in hits]}
    t = time.time(); top = rerank(eq, hits, top=5)
    yield {"type": "stage", "stage": "rerank", "ms": int((time.time()-t)*1000),
           "items": [{"law": _norm_law(r["law"]), "no": r["article_no"], "score": r["score"]} for r in top]}
    L.info("[%s] 检索 nav=%d recall=%d top5=%s", rid, len(nav), len(hits),
           "/".join(_norm_law(r["law"]) + "第" + r["article_no"] + "条" for r in top))
    ctx = assemble(question, nav, top, history)
    yield {"type": "stage", "stage": "assemble", "ms": 0, "chars": len(ctx)}
    parts = []
    for delta in chat_stream(_messages(ctx)):
        parts.append(delta)
        yield {"type": "token", "text": delta}
    raw = "".join(parts)
    rep = verify(raw, top, config.REPO / "wiki" / "articles", nav)
    yield {"type": "verify", "refs_ok": rep["refs_ok"], "refs_bad": rep["refs_bad"],
           "dropped": rep["quotes_dropped"]}
    yield {"type": "final", "text": rep["answer"]}
    yield {"type": "done", "elapsed_ms": int((time.time()-t0)*1000)}