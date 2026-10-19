"""M3 全量评测：端到端四维指标（正确率 / 引用精确率 / 无据拒答率 / 时效零容忍）。
评测判官用同一 OpenAI 兼容通道（qwen-plus），逐题输出 JSON 判定。"""
import json, re, time, glob
from . import config
JUDGE_SYS = ("你是严格的法律 RAG 评测员。根据题目、系统回答、评分要点与给定条文，只输出 JSON："
 '{"kp":[每个要点1或0],"support":{"条文号":1或0——该条能否支撑回答中对它的引用主张},'
 '"repealed":0或1——回答是否把已废止规则当作现行依据（正确指出已废止则记0）,"refusal":0或1——回答是否为"依据不足"类拒答,"mustnot":[被违反的禁用概念——仅当该概念作为法律规则被错误主张时才算，日常语词巧合（如交通中断）不算]}')
def judge(item, answer, top):
    from .llm import chat
    arts = "\n".join(f"第{r['article_no']}条: " + r["text"][:150].replace("\n", " ") for r in top)
    kp = item.get("key_points", [])
    user = (f"题目：{item['question']}\n评分要点：{kp}\n系统回答：\n{answer}\n给定条文：\n{arts}\n"
            "注意：type=no_basis 的题目，正确行为是明确声明依据不足（refusal=1）。")
    out = chat([{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
               temperature=0.0, max_tokens=300)
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else {}
def run_all():
    import yaml
    items = []
    for f in sorted(glob.glob(str(config.REPO / "eval" / "golden" / "*.yaml"))):
        items += yaml.safe_load(open(f, encoding="utf-8"))
    from .search import nav_select, vector_recall, rerank
    from .answer import assemble, generate, verify
    from .qa_graph import node_verify  # noqa (kept for symmetry)
    results = []
    fp = config.REPO / "eval" / "results" / "m3-answers.jsonl"
    fp.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, it in enumerate(items):
        q = it["question"]
        nb = it.get("type") == "no_basis"
        top = []
        try:
            from .query_rewrite import rewrite
            eq = rewrite(q)
            nav = nav_select(eq)
            hits = vector_recall(eq, k=12)
            top = rerank(eq, hits, top=5)
            ans = generate(assemble(q, nav, top))
            rep = verify(ans, top, config.REPO / "wiki" / "articles", nav)
            answer = rep["answer"]
            j = judge(it, answer, top)
        except Exception as e:
            answer, j, rep = "", {}, {"refs_ok": [], "refs_bad": [], "quotes_dropped": 0}
            print(f"[{i+1}/{len(items)}] {it['id']} ERROR {e!r:.80}", flush=True)
            continue
        cited = rep["refs_ok"] + rep["refs_bad"]
        kp = it.get("key_points", [])
        rec = {
            "id": it["id"], "type": it.get("type", "answerable"),
            "correct": (1 if not kp else int(all(v == 1 for v in (j.get("kp") or [0]*len(kp))))) if not nb else None,
            "refusal": int(bool(j.get("refusal")) or "依据不足" in answer),
            "no_ref": int(len(cited) == 0),
            "cited_ok": [n for n in rep["refs_ok"] if j.get("support", {}).get(n, 1) == 1],
            "cited": cited,
            "repealed": int(bool(j.get("repealed"))),
            "quotes_dropped": rep["quotes_dropped"],
            "must_not_hit": [str(x) for x in (j.get("mustnot") or [])],
            "answer": answer,
        }
        with open(fp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        results.append(rec)
        print(f"[{i+1}/{len(items)}] {it['id']} correct={rec['correct']} refusal={rec['refusal']} "
              f"cited={len(cited)} ok={len(rec['cited_ok'])} repealed={rec['repealed']} drop={rec['quotes_dropped']}", flush=True)
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
    lines = [
        f"# M3 评测报告（{time.strftime('%Y-%m-%d %H:%M')}）",
        f"- 题量：{len(rs)}（可答 {len(ab)} / 无据 {len(nbq)}），耗时 {time.time()-t0:.0f}s",
        f"- 回答正确率：{acc:.0%}（出口 >= 85%）",
        f"- 引用精确率：{prec:.0%}（{sum(len(r['cited_ok']) for r in ab)}/{cited_total}，出口 >= 95%）",
        f"- 无据拒答率：{ref:.0%}（出口 >= 90%）",
        f"- 时效违规：{rep} 处（零容忍：>=1 即不通过）",
        f"- must_not 违规：{len(mn)} 题" + (str([m['id'] for m in mn]) if mn else ""),
        f"- 伪引用剔除总数：{sum(r['quotes_dropped'] for r in rs)}（cite_verify 拦截）",
    ]
    txt = "\n".join(lines)
    print("\n" + txt)
    (config.REPO / "eval" / "results" / f"m3-report-{time.strftime('%Y%m%d')}.md").write_text(txt + "\n", encoding="utf-8")
if __name__ == "__main__":
    run_all()