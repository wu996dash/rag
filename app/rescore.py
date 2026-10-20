# -*- coding: utf-8 -*-
"""判官重打分：对 R7 存档答案仅重跑 judge（不重跑模型），用于判官校准的 A/B 对比。"""
import argparse, json, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import config
from .eval_full import JUDGE_SYS, load_items
def article_text(name):
    fp = config.REPO / "wiki/articles" / (name + ".md")
    if not fp.exists():
        return ""
    m = re.search(r"## 原文\n(.*?)(?=\n## |\Z)", fp.read_text(encoding="utf-8"), re.S)
    return re.sub(r"^>\s*【原文】\s*", "", m.group(1) if m else "", flags=re.M).strip()
def rescore_one(idx, total, r, items):
    it = items.get(r["id"])
    if not it or r["type"] == "no_basis":
        return None
    from .llm import chat
    arts = "\n\n".join(f"{c} 原文：{article_text(c)[:650]}" for c in r["cited"]) or "（无引用）"
    user = (f"题目：{it['question']}\n评分要点：{it.get('key_points', [])}\n系统回答：\n{r['answer']}\n"
            f"回答引用条文（REF 顺序）：{r['cited']}\n给定条文：\n{arts}")
    out = chat([{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
               temperature=0.0, max_tokens=400)
    m = re.search(r"\{.*\}", out, re.S)
    j = json.loads(m.group(0)) if m else {}
    kp = it.get("key_points", [])
    new_correct = int(bool(kp) and all(v == 1 for v in (j.get("kp") or [0] * len(kp))))
    ok_new = 0
    for n in r["cited"]:
        key = n.split("第")[-1]
        sup = j.get("support", {})
        v = sup.get(key, sup.get(f"第{key}条", sup.get(n, 1)))
        ok_new += 1 if v == 1 else 0
    return {"id": r["id"], "cited": len(r["cited"]), "ok_old": len(r["cited_ok"]), "ok_new": ok_new,
            "correct_old": r["correct"], "correct_new": new_correct, "repealed": int(bool(j.get("repealed")))}
def main():
    import yaml, glob
    items = {}
    for f in sorted(glob.glob(str(config.REPO / "eval/golden/*.yaml"))):
        for it in yaml.safe_load(open(f, encoding="utf-8")):
            items[it["id"]] = it
    src = Path("eval/results/r7-answers-86.jsonl")
    rs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = [x for x in ex.map(lambda x: rescore_one(x[0], len(rs), x[1], items), enumerate(rs, 1)) if x]
    Path("eval/results/r7-rescore-judge-v3.jsonl").write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out), encoding="utf-8")
    cited = sum(o["cited"] for o in out); ok_o = sum(o["ok_old"] for o in out); ok_n = sum(o["ok_new"] for o in out)
    co = sum(o["correct_old"] for o in out); cn = sum(o["correct_new"] for o in out); n = len(out)
    print(f"可答题 {n} | 支撑度: 旧 {ok_o}/{cited}={ok_o/cited:.0%} -> 新 {ok_n}/{cited}={ok_n/cited:.0%}")
    print(f"正确率: 旧 {co}/{n} -> 新 {cn}/{n}")
    flips = [o["id"] for o in out if o["ok_old"] != o["ok_new"]]
    print("支撑度变化题:", flips[:20])
if __name__ == "__main__":
    main()
