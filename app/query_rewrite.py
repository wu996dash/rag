"""查询理解层（M4）：口语叙事 -> 法律概念检索串。G-038 类失败的结构性修复。

降级语义（2026-10-22 加固）：
改写失败时回退原问句是**可用性兜底**，不能等同于成功——它会让召回质量显著下降
（实测同一问题改写失效时 top-12 混入大量“中断”条文，正确条文从第 1 名跌到第 2 名）。
因此：
  1. 失败必写 WARNING 日志，带异常原因，便于按日志排查；
  2. **失败结果不进 lru_cache**——原实现会把回退值缓存住，导致 key 一时失效后
     整个进程生命周期内都退回原句；现在按“成功才缓存”拆分。
"""
import re
from functools import lru_cache
from .llm import chat
from .log import get

log = get("rewrite")

SYS = ("你是法律检索查询扩展器，不回答法律问题本身。把用户的口语化提问改写为检索友好的法学术语查询串："
"输出恰好一行，格式：EXPANDED: <10到30字的术语串，含可能对应的核心制度概念，逗号分隔>。"
"若同一事实可能同时触发刑事与民事责任（如醉驾、伤害、诈骗），术语串必须同时包含两部门法核心词；重要：只有当前问题确实是对上文的追问或含指代时才参考对话上文；寒暄、致谢、闲聊或与上文无关的独立提问，"
"必须原样输出（EXPANDED: 原问题），严禁把上文主题词带进来。")

_CHAT = re.compile(r"^(你好|您好|哈喽|嗨|hi|hello|hey|在吗|在么|在不在|谢谢|多谢|感谢|再见|拜拜|辛苦了|好的|收到|嗯+|哦+|ok|行吧?)[!！。、~\s]*$", re.I)


@lru_cache(maxsize=512)
def _rw_ok(question: str, ctx_key: str) -> str:
    """只缓存**成功**的改写结果；失败路径由 rewrite() 直接返回原句且不入缓存。"""
    q = question if not ctx_key else f"（对话上文：{ctx_key}）\n当前追问：{question}"
    out = chat([{"role": "system", "content": SYS}, {"role": "user", "content": q}],
               temperature=0.0, max_tokens=80, timeout=60)
    m = re.search(r"EXPANDED[:：]\s*(.+)", out)
    q2 = (m.group(1) if m else question).strip().rstrip("。")
    if not m:
        log.warning("改写输出不符合 EXPANDED 格式，回退原问句：%r", out[:120])
    return q2 if q2 else question


def rewrite(question: str, history=None) -> str:
    if _CHAT.match(question.strip()):          # 寒暄直连，不进改写
        return question.strip()
    ctx = "；".join(str(h.get("q", ""))[:40] for h in (history or [])[-3:] if h.get("q"))
    try:
        return _rw_ok(question, ctx)
    except Exception as e:
        # 降级可用但必须留痕：这是质量下降信号，不是正常路径
        log.warning("查询改写失败，回退原问句（召回质量将下降）：%r", e)
        return question
