"""法条解析：官方 docx -> 条文记录（条文单元 = 向量检索单元，见任务描述.md §5.4）。"""
import re
from functools import lru_cache
from .docxload import docx_text
CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNIT = {"十": 10, "百": 100, "千": 1000}
def cn2num(s: str) -> int:
    total, num = 0, 0
    for ch in s:
        if ch in CN:
            num = CN[ch]
        elif ch in UNIT:
            num = (num or 1) * UNIT[ch]
            total += num
            num = 0
    return total + num
ART_RE = re.compile(r"^第([零〇一二三四五六七八九十百千]+)条[　\s]*(.*)$")
HEAD_RE = re.compile(r"^第([零〇一二三四五六七八九十百千]+)([编章节])[　\s]*(.*)$")
@lru_cache(maxsize=8)
def parse_law(name: str):
    from . import config
    meta = config.SOURCES[name]
    text = docx_text(meta["path"])
    recs, cur = [], None
    part = chap = sec = ""
    for p in text.split("\n"):
        mh = HEAD_RE.match(p)
        ma = ART_RE.match(p)
        if mh and not ma:
            level = mh.group(2)
            label = "第" + mh.group(1) + level + " " + mh.group(3)
            if level == "编": part, chap, sec = label, "", ""
            elif level == "章": chap, sec = label, ""
            else: sec = label
            cur = None
            continue
        if ma:
            cur = {"law": meta["law"], "abbr": meta["abbr"], "no": cn2num(ma.group(1)),
                   "part": part, "chapter": chap, "section": sec,
                   "clauses": ([ma.group(2)] if ma.group(2) else [])}
            recs.append(cur)
            continue
        if cur is not None and p and not p.startswith("第"):
            cur["clauses"].append(p)
    for r in recs:
        r["text"] = "\n".join(r["clauses"])
    return recs