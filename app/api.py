"""FastAPI 服务：REST 统计/页面 + WebSocket 流式问答；挂载 web/dist 静态前端。
启动：python -m uvicorn app.api:app --host 127.0.0.1 --port 8000"""
import asyncio, json, queue, threading
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from . import config
app = FastAPI(title="viki_rag API")
@app.on_event("startup")
def _warm():
    def _go():
        from .m3encode import _load
        from .search import _reranker
        _load(); _reranker()
    threading.Thread(target=_go, daemon=True).start()
@app.get("/api/stats")
def stats():
    import glob
    a = len(list((config.REPO / "wiki" / "articles").glob("*.md")))
    n_concepts = len([p for p in (config.REPO / "wiki" / "concepts").glob("*.md") if p.name != "README.md"])
    ca = len([p for p in (config.REPO / "wiki" / "cases").glob("*.md") if p.name != "README.md"])
    srcs = len(list((config.REPO / "sources").glob("*.docx"))) + len([p for p in (config.REPO / "sources").glob("*.md") if p.name != "README.md"])
    rows = None
    try:
        from .vectors import client
        c = client()
        rows = sum(int(c.query(collection_name=config.MILVUS_COLLECTION, filter='law == "' + v["law"] + '"', output_fields=["count(*)"])[0]["count(*)"]) for v in config.SOURCES.values())
    except Exception:
        pass
    return {"articles": a, "concepts": n_concepts, "cases": ca, "sources": srcs,
            "milvus_rows": rows, "laws": list(config.SOURCES.keys())}
@app.get("/api/page")
def page(path: str = Query(...)):
    rel = str(path)
    if not rel.startswith("wiki/") or not rel.endswith(".md") or ".." in rel:
        return JSONResponse({"error": "仅允许读取 wiki/ 下的 .md 文件"}, status_code=400)
    p = config.REPO / rel
    if not p.exists():
        return JSONResponse({"error": "不存在"}, status_code=404)
    return {"path": rel, "content": p.read_text(encoding="utf-8")}
@app.post("/api/feedback")
async def feedback(payload: dict):
    import json, time, re
    q = str(payload.get("question") or "").strip()
    v = payload.get("verdict")
    if not q or v not in ("up", "down"):
        return JSONResponse({"error": "参数不合法"}, status_code=400)
    note = str(payload.get("note") or "")[:500]
    ans = str(payload.get("answer") or "")[:3000]
    ans = re.sub(r"\s+", " ", ans).strip()
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M"), "question": q[:200], "verdict": v,
           "note": note, "answer": ans, "reviewed": False}
    with open(config.REPO / "eval" / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True}

@app.websocket("/ws/ask")
async def ws_ask(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = json.loads(await ws.receive_text())
            q = (payload.get("text") or "").strip()
            if not q:
                continue
            evtq: queue.Queue = queue.Queue()
            def _worker(question=q, sink=evtq):
                try:
                    from .pipeline import events
                    for ev in events(question):
                        sink.put(ev)
                except Exception as e:
                    sink.put({"type": "error", "msg": repr(e)})
                finally:
                    sink.put(None)
            threading.Thread(target=_worker, daemon=True).start()
            while True:
                ev = await asyncio.to_thread(evtq.get)
                if ev is None:
                    break
                await ws.send_json(ev)
    except WebSocketDisconnect:
        pass
dist = config.REPO / "web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
