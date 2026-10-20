"""查询理解层（M4）：口语叙事 -> 法律概念检索串。G-038 类失败的结构性修复。"""
import re
from functools import lru_cache
from .llm import chat
SYS = ("你是法律检索查询扩展器，不回答法律问题本身。把用户的口语化提问改写为检索友好的法学术语查询串："
"输出恰好一行，格式：EXPANDED: <10到30字的术语串，含可能对应的核心制度概念，逗号分隔>")
@lru_cache(maxsize=512)
def _rw(question: str, ctx_key: str) -> str:
    q = question if not ctx_key else f"（对话上文：{ctx_key}）\n当前追问：{question}"
    try:
        out = chat([{"role": "system", "content": SYS}, {"role": "user", "content": q}],
                   temperature=0.0, max_tokens=80, timeout=60)
        m = re.search(r"EXPANDED[:：]\s*(.+)", out)
        q = (m.group(1) if m else question).strip().rstrip("。")
        return q if q else question
    except Exception:
        return question

def rewrite(question: str, history=None) -> str:
    ctx = "；".join(str(h.get("q", ""))[:40] for h in (history or [])[-3:] if h.get("q"))
    return _rw(question, ctx)