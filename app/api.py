"""FastAPI 服务：认证(MySQL) + 流式问答(WS) + 会话记忆 + 管理员材料录入 + 反馈。
启动：python -m uvicorn app.api:app --host 127.0.0.1 --port 8100"""
import asyncio, json, queue, re, threading, time
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from . import config, auth
app = FastAPI(title="viki_rag API")
def _who(req: Request):
    h = req.headers.get("authorization") or ""
    tok = h[7:] if h.startswith("Bearer ") else (req.query_params.get("token") or "")
    return auth.user_of(tok)
@app.on_event("startup")
def _warm():
    auth.init_db()
    auth.create_default_admin()
    def _go():
        from .m3encode import _load
        from .search import _reranker
        _load(); _reranker()
    threading.Thread(target=_go, daemon=True).start()
# ---------- 账号 ----------
@app.post("/api/auth/register")
async def register(req: Request):
    b = await req.json()
    return JSONResponse(auth.register(b.get("username"), b.get("password")))
@app.post("/api/auth/login")
async def login(req: Request):
    b = await req.json()
    return JSONResponse(auth.login(b.get("username"), b.get("password")))
@app.get("/api/auth/me")
async def me(req: Request):
    u = _who(req)
    return JSONResponse(u or {"error": "未登录"}, status_code=200 if u else 401)
# ---------- 会话记忆 ----------
@app.get("/api/sessions")
async def sessions(req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    return JSONResponse(auth.list_sessions(u["username"]))
@app.post("/api/sessions")
async def save_session(req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    b = await req.json()
    return {"ok": True, "count": auth.save_session(u["username"], b)}
# ---------- 统计与原文 ----------
@app.get("/api/stats")
def stats():
    a = len(list((config.REPO / "wiki" / "articles").glob("*.md")))
    nc = len([p for p in (config.REPO / "wiki" / "concepts").glob("*.md") if p.name != "README.md"])
    ca = len([p for p in (config.REPO / "wiki" / "cases").glob("*.md") if p.name != "README.md"])
    rows = 0
    try:
        from .vectors import client
        c = client()
        total = 0
        for v in config.SOURCES.values():
            res = c.query(collection_name=config.MILVUS_COLLECTION,
                          filter='law == "' + v["law"] + '"', output_fields=["count(*)"])
            total += int(res[0]["count(*)"])
        rows = total
    except Exception:
        pass
    return {"articles": a, "concepts": nc, "cases": ca, "vectors": rows, "laws": list(config.SOURCES.keys())}
@app.get("/api/page")
def page(path: str = Query(...)):
    rel = str(path)
    if not rel.startswith("wiki/") or not rel.endswith(".md") or ".." in rel:
        return JSONResponse({"error": "仅允许读取 wiki/ 下的 .md 文件"}, status_code=400)
    p = config.REPO / rel
    if not p.exists():
        return JSONResponse({"error": "不存在"}, status_code=404)
    return {"path": rel, "content": p.read_text(encoding="utf-8")}
# ---------- 管理员：法律材料录入 ----------
_SAFE = re.compile(r"^[\w\u4e00-\u9fff（）()·-]{2,48}$")
@app.post("/api/materials")
async def add_material(req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if u["role"] != "admin":
        return JSONResponse({"error": "仅管理员可录入法律材料"}, status_code=403)
    b = await req.json()
    name = str(b.get("name") or "").strip()
    text = str(b.get("text") or "").strip()
    edate = str(b.get("effective_date") or "").strip() or time.strftime("%Y%m%d")
    if not _SAFE.match(name):
        return JSONResponse({"error": "材料名称需为 2-48 位合法字符"}, status_code=400)
    if len(text) < 80:
        return JSONResponse({"error": "正文过短（<80 字），疑似不完整文本"}, status_code=400)
    safe_date = re.sub(r"[^0-9-]", "", edate) or time.strftime("%Y%m%d")
    fname = name + "_" + safe_date + ".md"
    fp = config.REPO / "sources" / fname
    if fp.exists():
        return JSONResponse({"error": "同名材料已存在，请走 CLI 更新流程"}, status_code=409)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    header = ("<!-- 管理端录入 " + stamp + "｜录入人 " + u["username"] +
              "｜生效日期 " + edate + "｜待人工核对官方渠道 -->\n\n")
    fp.write_text(header + text + "\n", encoding="utf-8")
    rm = config.REPO / "sources" / "README.md"
    rm.write_text(rm.read_text(encoding="utf-8") +
                  "\n- " + fname + "｜管理端录入 " + stamp[:10] + "｜待核验｜待编译\n", encoding="utf-8")
    return {"ok": True, "path": "sources/" + fname,
            "next": "编译需人工：登记 config.SOURCES 后 python -m app.cli ingest"}
@app.get("/api/materials")
async def list_materials(req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if u["role"] != "admin":
        return JSONResponse({"error": "仅管理员可见"}, status_code=403)
    files = sorted(p.name for p in (config.REPO / "sources").iterdir()
                   if p.is_file() and p.name != "README.md")
    return {"files": files}
# ---------- 问答 WS（需登录）与反馈 ----------
@app.websocket("/ws/ask")
async def ws_ask(ws: WebSocket):
    tok = ws.query_params.get("token") or ""
    user = auth.user_of(tok)
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        while True:
            payload = json.loads(await ws.receive_text())
            q = (payload.get("text") or "").strip()
            if not q:
                continue
            raw_h = payload.get("history") or []
            history = [{"q": str(h.get("q") or "")[:200], "a": str(h.get("a") or "")[:600]}
                       for h in raw_h[-5:] if isinstance(h, dict)][-5:]
            evtq = queue.Queue()
            def _worker(question=q, hist=history, sink=evtq):
                try:
                    from .pipeline import events
                    for ev in events(question, hist):
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
@app.post("/api/feedback")
async def feedback(req: Request):
    user = _who(req) or {"username": "anonymous", "role": "user"}
    b = await req.json()
    q = str(b.get("question") or "").strip()
    v = b.get("verdict")
    if not q or v not in ("up", "down"):
        return JSONResponse({"error": "参数不合法"}, status_code=400)
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M"), "user": user["username"],
           "question": q[:200], "verdict": v, "note": str(b.get("note") or "")[:500],
           "answer": re.sub(r"\s+", " ", str(b.get("answer") or ""))[:3000], "reviewed": False}
    with open(config.REPO / "eval" / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True}
dist = config.REPO / "web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")