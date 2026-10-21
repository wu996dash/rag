"""FastAPI 服务：认证(MySQL) + 流式问答(WS) + 会话记忆 + 管理员材料录入 + 反馈。
启动：python -m uvicorn app.api:app --host 127.0.0.1 --port 8100"""
import asyncio, json, queue, re, threading, time
from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from . import config, auth, log
L = log.get("api")
app = FastAPI(title="viki_rag API")
def _who(req: Request):
    h = req.headers.get("authorization") or ""
    tok = h[7:] if h.startswith("Bearer ") else (req.query_params.get("token") or "")
    return auth.user_of(tok)
@app.on_event("startup")
def _warm():
    auth.init_db()
    auth.create_default_admin()
    L.info("服务启动｜Milvus=%s｜MySQL=%s@%s｜日志=logs/app.log", config.MILVUS_URI, config.MYSQL_USER, config.MYSQL_HOST)
    def _go():
        from .m3encode import _load
        from .search import _reranker
        _load(); _reranker()
    threading.Thread(target=_go, daemon=True).start()
# ---------- 账号 ----------
@app.post("/api/auth/register")
async def register(req: Request):
    b = await req.json()
    r = auth.register(b.get("username"), b.get("password"))
    (L.warning if "error" in r else L.info)("注册%s user=%s%s", "拒绝" if "error" in r else "成功", b.get("username"), "" if "error" not in r else "｜" + r["error"])
    return JSONResponse(r)
@app.post("/api/auth/login")
async def login(req: Request):
    b = await req.json()
    r = auth.login(b.get("username"), b.get("password"))
    (L.warning if "error" in r else L.info)("登录%s user=%s%s", "失败" if "error" in r else "成功", b.get("username"), "" if "error" not in r else "｜" + r["error"])
    return JSONResponse(r)
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
@app.delete("/api/sessions/{cid}")
async def delete_session(cid: str, req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    n = auth.delete_session(u["username"], cid)
    L.info("删除对话 user=%s id=%s ok=%s", u["username"], cid, n > 0)
    return {"ok": n > 0}

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
# ---------- 管理员：法律材料文件上传 ----------
_ALLOWED_EXT = {".docx", ".md", ".txt"}
_MAX_BYTES = 20 * 1024 * 1024
def _dedup(dirpath, fname):
    from pathlib import Path as _P
    import os as _os
    base, ext = _os.path.splitext(fname)
    cand, n = _P(dirpath) / fname, 2
    while cand.exists():
        cand = _P(dirpath) / f"{base}-{n}{ext}"; n += 1
    return cand
@app.post("/api/materials")
async def add_material(req: Request, file=File(...), effective_date: str = Form("")):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if u["role"] != "admin":
        L.warning("材料上传被拒 user=%s（非管理员）", u["username"])
        return JSONResponse({"error": "仅管理员可录入法律材料"}, status_code=403)
    raw_name = (file.filename or "").replace("\\", "/").split("/")[-1]
    safe = re.sub(r"[^\w\u4e00-\u9fff.\-（）() ]", "", raw_name).strip()
    import os
    base, ext = os.path.splitext(safe)
    ext = ext.lower()
    if not base or ext not in _ALLOWED_EXT:
        return JSONResponse({"error": "仅支持 .docx / .md / .txt 文件"}, status_code=400)
    data = await file.read()
    if len(data) > _MAX_BYTES:
        return JSONResponse({"error": "文件超过 20MB"}, status_code=400)
    if ext == ".docx" and data[:2] != b"PK":
        return JSONResponse({"error": "docx 文件损坏或非 zip 容器"}, status_code=400)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    header = ("<!-- 拖拽上传 " + stamp + "｜上传人 " + u["username"] +
              "｜生效日期 " + (effective_date or "未登记") + "｜待人工核对官方渠道 -->\n\n")
    if ext in (".md", ".txt"):
        try:
            body_text = data.decode("utf-8")
        except UnicodeDecodeError:
            body_text = data.decode("gbk", "ignore")
        if len(re.sub(r"\s", "", body_text)) < 80:
            return JSONResponse({"error": "正文过短（<80 字），请确认是完整文本"}, status_code=400)
        data = (header + body_text).encode("utf-8")
    fp = _dedup(config.REPO / "sources", safe if ext == ".docx" else (base + ext))
    fp.write_bytes(data)
    rel = "sources/" + fp.name
    n_art = 0
    try:
        from .docxload import docx_text
        text = docx_text(rel) if ext == ".docx" else fp.read_text(encoding="utf-8")
        n_art = len(re.findall(r"第[零〇一二三四五六七八九十百千]+条", text))
    except Exception as e:
        L.warning("材料解析统计失败 %s: %r", rel, e)
    rm = config.REPO / "sources" / "README.md"
    rm.write_text(rm.read_text(encoding="utf-8") +
                  "\n- " + fp.name + "｜管理端上传 " + stamp[:10] + "｜待核验｜待编译\n", encoding="utf-8")
    L.info("材料上传 admin=%s file=%s 大小=%dKB 检出条文标记=%d（待核验待编译）",
           u["username"], fp.name, len(data) // 1024, n_art)
    return {"ok": True, "path": rel, "kb": round(len(data) / 1024), "articles": n_art,
            "next": "核验后登记 config.SOURCES 再 python -m app.cli ingest 编译"}
@app.get("/api/materials")
async def list_materials(req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if u["role"] != "admin":
        return JSONResponse({"error": "仅管理员可见"}, status_code=403)
    known = {v["path"].split("/")[-1] for v in config.SOURCES.values()}
    files = [{"name": p.name, "compiled": p.name in known,
              "abbr": next((k for k, v in config.SOURCES.items() if v["path"].endswith(p.name)), "")}
             for p in sorted((config.REPO / "sources").iterdir())
             if p.is_file() and p.name != "README.md"]
    return {"files": files}
# ---------- 管理端：编译入库 ----------
@app.post("/api/compile")
async def compile_start(req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if u["role"] != "admin":
        return JSONResponse({"error": "仅管理员可编译入库"}, status_code=403)
    b = await req.json()
    path = str(b.get("path") or "")
    abbr = str(b.get("abbr") or "").strip()
    if not path.startswith("sources/") or not abbr or len(abbr) > 16:
        return JSONResponse({"error": "参数不合法（path 需 sources/ 下，简称 1-16 字）"}, status_code=400)
    if not (config.REPO / path).exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    from . import compile as comp
    tid = comp.start(path, abbr, str(b.get("effective_date") or "").strip())
    L.info("编译任务启动 admin=%s path=%s abbr=%s task=%s", u["username"], path, abbr, tid)
    return {"task": tid}
@app.get("/api/compile/{tid}")
async def compile_status(tid: str, req: Request):
    u = _who(req)
    if not u:
        return JSONResponse({"error": "未登录"}, status_code=401)
    from . import compile as comp
    st = comp.status(tid)
    return st or {"state": "unknown"}

# ---------- 问答 WS（需登录）与反馈 ----------
@app.websocket("/ws/ask")
async def ws_ask(ws: WebSocket):
    tok = ws.query_params.get("token") or ""
    user = auth.user_of(tok)
    if not user:
        L.warning("WS 拒绝：无效或缺失 token")
        await ws.close(code=4401)
        return
    await ws.accept()
    import uuid
    rid = uuid.uuid4().hex[:8]
    L.info("WS 连接 user=%s rid=%s", user["username"], rid)
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
            L.info("[%s] 提问 user=%s q=%s", rid, user["username"], q[:50])
            def _worker(question=q, hist=history, sink=evtq):
                try:
                    from .pipeline import events
                    for ev in events(question, hist, rid):
                        sink.put(ev)
                except Exception as e:
                    L.exception("[%s] 流水线异常", rid)
                    sink.put({"type": "error", "msg": repr(e)})
                finally:
                    sink.put(None)
            threading.Thread(target=_worker, daemon=True).start()
            while True:
                ev = await asyncio.to_thread(evtq.get)
                if ev is None:
                    break
                if ev.get("type") == "verify":
                    L.info("[%s] 校验 ok=%d bad=%d 剔除=%d", rid, len(ev["refs_ok"]), len(ev["refs_bad"]), ev["dropped"])
                elif ev.get("type") == "done":
                    L.info("[%s] 完成 elapsed=%sms", rid, ev.get("elapsed_ms"))
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
    L.info("反馈 user=%s verdict=%s q=%s", user["username"], v, q[:40])
    return {"ok": True}
dist = config.REPO / "web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")