"""M3+ 并发评测：ThreadPool 并行独立题目；判官走 LLM_MODEL_JUDGE；--only 过滤支持增量评测。"""
import argparse, json, re, time, glob, threading
from concurrent.futures import ThreadPoolExecutor
from . import config
JUDGE_SYS = ("你是严格的法律 RAG 评测员。根据题目、系统回答、评分要点与给定条文，只输出 JSON："
 '{"kp":[每个要点1或0],"support":{"条文号":1或0},'
 '"repealed":0或1,"refusal":0或1,"mustnot":[被违反的禁用概念]}。\n'
 "support 判定规则（务必逐条按此执行）：对回答 REF 列出的每条条文，检查回答中归属于该条文的主张句："
 "(a) 条文内容包含或合理蕴含该主张 -> 判1，包括条文仅承担制度前提/主体范围/义务基础等背景性支撑的情形；"
 "(b) 回答把条文里没有的具体规则、数字、期限安在该条文头上 -> 判0；"
 "(c) 条文号在给定条文中不存在 -> 判0。\n"
 "判例1（判1）：回答称『竞业限制不适用于普通员工（劳动合同法第24条）』，第24条列明人员范围限于高管高技及保密人员 -> 合理蕴含，判1。\n"
 "判例2（判0）：回答称『利息超过LPR四倍部分无效（民法典第680条）』，第680条仅规定不得高利放贷、利率不得违反国家有关规定，未含LPR四倍 -> 具体标准不在该条，判0。\n"
 "kp 规则：评分要点含括号备选说明时满足任一备选即判1；语义等价表述判1；回答先给正确结论再展开的不扣分。"
 "refusal：回答明确声明依据不足/待核实且未将无依据内容写成确定结论 -> 1。"
 "repealed：把已废止规则当作现行依据才判1；正确指出已废止则0。"
 "mustnot：仅当禁用概念被作为法律规则错误主张才计入；日常语词巧合（如『交通中断』）不计。")

_print_lock = threading.Lock()
def judge(item, answer, top):
    from .llm import chat
    arts = "\n".join(f"{r.get('law','')[-6:]}第{r['article_no']}条: " + r["text"][:650].replace("\n", " ") for r in top)
    user = (f"题目：{item['question']}\n评分要点：{item.get('key_points', [])}\n系统回答：\n{answer}\n给定条文：\n{arts}\n"
            "注意：type=no_basis 的题目，正确行为是明确声明依据不足（refusal=1）。")
    out = chat([{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
               temperature=0.0, max_tokens=300, model=config.LLM_MODEL_JUDGE)
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}
def load_items(only=None):
    import yaml
    items = []
    for f in sorted(glob.glob(str(config.REPO / "eval" / "golden" / "*.yaml"))):
        for it in yaml.safe_load(open(f, encoding="utf-8")):
            it["_file"] = f.split("\\")[-1]
            items.append(it)
    if only:
        pats = [p.strip() for p in only.split(",") if p.strip()]
        items = [it for it in items if any(p.upper() in it["id"].upper() or p in it["_file"] for p in pats)]
    return items
def run_one(idx, total, it, retry=False):
    from .search import nav_select, vector_recall, rerank
    from .answer import assemble, generate, verify
    from .query_rewrite import rewrite
    q = it["question"]
    try:
        eq = rewrite(q)
        nav = nav_select(eq)
        hits = vector_recall(eq)
        top = rerank(eq, hits, top=5)
        ans = generate(assemble(q, nav, top))
        rep = verify(ans, top, config.REPO / "wiki" / "articles", nav)
        answer = rep["answer"]
        j = judge(it, answer, top)
    except Exception as e:
        with _print_lock:
            print(f"[{idx}/{total}] {it['id']} ERROR {e!r:.100}", flush=True)
        return None
    cited = rep["refs_ok"] + rep["refs_bad"]
    kp = it.get("key_points", [])
    nb = it.get("type") == "no_basis"
    rec = {"id": it["id"], "type": it.get("type", "answerable"),
           "correct": (int(bool(kp) and all(v == 1 for v in (j.get("kp") or [0] * len(kp)))) if not nb else None),
           "refusal": int(bool(j.get("refusal")) or "依据不足" in answer),
           "no_ref": int(len(cited) == 0),
           "cited_ok": [n for n in rep["refs_ok"] if j.get("support", {}).get(n.split("第")[-1].rstrip("条"), j.get("support", {}).get(n, 1)) == 1],
           "cited": cited, "repealed": int(bool(j.get("repealed"))),
           "quotes_dropped": rep["quotes_dropped"],
           "must_not_hit": [str(x) for x in (j.get("mustnot") or [])],
           "answer": answer}
    with _print_lock:
        print(f"[{idx}/{total}] {it['id']} correct={rec['correct']} refusal={rec['refusal']} "
              f"cited={len(cited)} ok={len(rec['cited_ok'])} repealed={rec['repealed']} drop={rec['quotes_dropped']}", flush=True)
    return rec
def _prewarm():
    from .m3encode import _load as _load_m3
    from .search import _reranker
    _load_m3(); _reranker()
    print("[prewarm] 双模型已驻留 GPU", flush=True)
def run_all(limit=999, only=None, workers=3):
    items = load_items(only)[:limit]
    _prewarm()
    t0 = time.time()
    pending = list(enumerate(items, 1))
    results, failed = [], []
    for rnd in (1, 2):
        if not pending:
            break
        with ThreadPoolExecutor(max_workers=workers) as ex:
            pairs = list(ex.map(lambda x: run_one(x[0], len(items), x[1], retry=(rnd > 1)), pending))
        results += [r for r in pairs if r]
        pending = [(i, it) for (i, it), r in zip(pending, pairs) if r is None]
        if pending and rnd == 1:
            print(f"[retry] {len(pending)} 题首轮失败（限流/网络），降速重跑", flush=True)
            time.sleep(20)
    failed = [it["id"] for _, it in pending]
    if failed:
        print("!! 仍未完成:", failed)
    _summary(results, t0)
def _summary(rs, t0):
    ab = [r for r in rs if r["type"] != "no_basis"]
    nbq = [r for r in rs if r["type"] == "no_basis"]
    acc = sum(r["correct"] for r in ab) / max(1, len(ab))
    cited_total = sum(len(r["cited"]) for r in ab)
    prec = sum(len(r["cited_ok"]) for r in ab) / max(1, cited_total)
    ref = sum(1 for r in nbq if r["refusal"] == 1 and r["no_ref"] == 1) / max(1, len(nbq))
    rep = sum(r["repealed"] for r in rs)
    mn = [r for r in rs if r["must_not_hit"]]
    lines = [f"# 评测报告（{time.strftime('%Y-%m-%d %H:%M')}）",
             f"- 题量：{len(rs)}（可答 {len(ab)} / 无据 {len(nbq)}），耗时 {time.time()-t0:.0f}s，判官 {config.LLM_MODEL_JUDGE}",
             f"- 回答正确率：{acc:.0%}（出口 >= 85%）",
             f"- 引用精确率：{prec:.0%}（{sum(len(r['cited_ok']) for r in ab)}/{cited_total}，出口 >= 95%）",
             f"- 无据拒答率：{ref:.0%}（出口 >= 90%）",
             f"- 时效违规：{rep} 处（零容忍：>=1 即不通过）",
             f"- must_not 违规：{len(mn)} 题" + (str([m['id'] for m in mn]) if mn else ""),
             f"- 伪引用剔除总数：{sum(r['quotes_dropped'] for r in rs)}"]
    txt = "\n".join(lines)
    print("\n" + txt)
    tag = time.strftime("%Y%m%d-%H%M")
    (config.REPO / "eval" / "results" / f"report-{tag}.md").write_text(txt + "\n", encoding="utf-8")
    with open(config.REPO / "eval" / "results" / f"answers-{tag}.jsonl", "w", encoding="utf-8") as fh:
        for r in rs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=999)
    ap.add_argument("--only", default=None, help="题目id前缀或文件名关键字，逗号分隔")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    run_all(limit=a.limit, only=a.only, workers=a.workers)
