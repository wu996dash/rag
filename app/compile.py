"""管理端编译任务：把 sources/ 材料 → 法律登记 → 条文页 → 向量库（后台线程+轮询）。"""
import json, re, threading, time, uuid
from pathlib import Path
from . import config, log
L = log.get("compile")
TASKS = {}
_lock = threading.Lock()
def _next_base():
    return max([v.get("id_base", 0) for v in config.SOURCES.values()] or [0]) + 1_000_000
def _save_laws():
    (config.REPO / "data").mkdir(exist_ok=True)
    (config.REPO / "data" / "laws.json").write_text(
        json.dumps(config.SOURCES, ensure_ascii=False, indent=1), encoding="utf-8")
def status(tid):
    return TASKS.get(tid)
def start(relpath, abbr, effective_date=""):
    tid = uuid.uuid4().hex[:8]
    TASKS[tid] = {"state": "queued", "msg": "排队中"}
    threading.Thread(target=_run, args=(tid, relpath, abbr, effective_date), daemon=True).start()
    return tid
def _run(tid, relpath, abbr, effective_date):
    t = TASKS[tid]
    added = False
    try:
        title = re.sub(r"_\d{6,8}$", "", Path(relpath).name.rsplit(".", 1)[0])
        for v in config.SOURCES.values():
            if v["path"] == relpath:
                raise ValueError("该材料已登记编译过")
        name = abbr
        if name in config.SOURCES:
            raise ValueError("简称已存在：" + name)
        meta = {"path": relpath, "law": title, "abbr": abbr,
                "slug": "law-%d" % (int(time.time()) % 100000),
                "id_base": _next_base(), "effective": effective_date or "未登记",
                "status": "现行有效"}
        t.update(state="running", msg="解析条文…")
        config.SOURCES[name] = meta
        added = True
        from .parser import parse_law
        recs = parse_law(name)
        if not recs:
            raise ValueError("未识别到任何『第X条』，请确认是法条文本")
        hi = max(r["no"] for r in recs)
        t["msg"] = "检出 %d 条，生成条文页…" % len(recs)
        from .pages import render
        pr = render(name, 1, hi)
        t["msg"] = "GPU 嵌入向量…"
        from .vectors import upsert_articles
        rows = upsert_articles(name, 1, hi)
        _save_laws()
        rm = config.REPO / "sources" / "README.md"
        rm.write_text(rm.read_text(encoding="utf-8") +
                      "\n- " + Path(relpath).name + "｜管理端编译 " + time.strftime("%Y-%m-%d") +
                      "｜" + abbr + " " + str(len(recs)) + " 条已入向量库\n", encoding="utf-8")
        from .docxload import docx_text
        docx_text.cache_clear()
        t.update(state="done", msg="完成", articles=len(recs), pages=pr["made"], rows=rows)
        L.info("编译入库 law=%s(%s) 条文=%d 页=%d 向量=%d", name, title, len(recs), pr["made"], rows)
    except Exception as e:
        if added:
            config.SOURCES.pop(abbr, None)
        t.update(state="error", msg=repr(e))
        L.error("编译失败 %s: %r", abbr, e)
