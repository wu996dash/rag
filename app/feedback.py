"""反馈闭环：列出 👎、生成评测题草稿（人工复核后进 golden）。"""
import json
from pathlib import Path
from . import config

def load():
    fp = config.REPO / "eval/feedback.jsonl"
    if not fp.exists():
        return []
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]

def pending():
    return [r for r in load() if r.get("verdict") == "down" and not r.get("reviewed")]

def draft():
    out = []
    for i, r in enumerate(pending(), 1):
        note = ("  # 用户备注: " + r["note"]) if r.get("note") else ""
        out.append(f"- id: FB-{i:03d}\n  question: {r['question']}\n  type: answerable\n"
                   f"  expected_articles: []  # TODO 人工补\n  key_points: []      # TODO 人工补\n{note}")
    return "\n".join(out) or "（暂无待处理 👎）"

def mark_reviewed():
    rows = load()
    fp = config.REPO / "eval/feedback.jsonl"
    for r in rows:
        if r.get("verdict") == "down":
            r["reviewed"] = True
    fp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return len([r for r in rows if r.get("reviewed")])
