"""条文页批量生成（SCHEMA.md §1.1）。既有页面跳过——人工参照页永远优先。"""
from datetime import date
from . import config
from .parser import parse_law
OUT = config.REPO / "wiki" / "articles"
M0_ENRICHED = {"民法典第188条.md", "民法典第192条.md", "民法典第194条.md", "民法典第195条.md", "民法典第196条.md"}
LIMITATION_LINKED = {188: "[诉讼时效中断](../concepts/诉讼时效中断.md)｜[普通诉讼时效期间](../concepts/普通诉讼时效期间.md)｜[诉讼时效](../concepts/诉讼时效.md)",
                     192: "[诉讼时效届满的效力](../concepts/诉讼时效届满的效力.md)｜[诉讼时效](../concepts/诉讼时效.md)",
                     194: "[诉讼时效中止](../concepts/诉讼时效中止.md)",
                     195: "[诉讼时效中断](../concepts/诉讼时效中断.md)",
                     196: "[诉讼时效](../concepts/诉讼时效.md)"}
def render(name: str, lo: int, hi: int):
    meta = config.SOURCES[name]
    recs = [r for r in parse_law(name) if lo <= r["no"] <= hi]
    made, skipped = 0, 0
    OUT.mkdir(parents=True, exist_ok=True)
    for r in recs:
        fn = f'{meta["abbr"]}第{r["no"]}条.md'
        path = OUT / fn
        if path.exists():
            skipped += 1
            continue
        today = date.today().isoformat()
        org = "\n".join(f'> 【原文】 {c}' for c in r["clauses"])
        _dft = "（关联制度页待编译）\n- [入口导航](../index.md)"
        linked = LIMITATION_LINKED.get(r["no"], _dft) if meta["abbr"] == "民法典" else _dft
        body = f'''---
id: article/{meta["slug"]}-{r["no"]}
type: article
title: {meta["abbr"]}第{r["no"]}条（{" ".join(x for x in (r["part"], r["chapter"]) if x)}）
law: {meta["law"]}
article_no: "{r["no"]}"
effective_date: {meta["effective"]}
status: {meta["status"]}
sources:
  - {meta["path"]}
updated_at: {today}
---

## 原文

{org}

## 款项拆解

（M1 自动编译骨架：款项结构化拆解待按 SCHEMA.md §1.1 精编，参照标准见 民法典第188条.md）

## 关联制度页

{linked}

## 时效说明

自 {meta["effective"]} 施行以来未修订。归属：{r["part"]} {r["chapter"]} {r["section"]}。
'''
        path.write_text(body, encoding="utf-8")
        made += 1
    return {"made": made, "skipped": skipped}