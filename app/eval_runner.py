"""M2 检索侧评测：黄金问题集 rerank top-5 条文命中率（出口条件 >= 80%）。"""
import re
from . import config
def run_retrieval_eval():
    import yaml
    data = yaml.safe_load((config.REPO / "eval" / "golden" / "诉讼时效.yaml").read_text(encoding="utf-8"))
    from .search import vector_recall, rerank
    total = hit = 0
    for item in data:
        expected = {re.search(r"(\d+)", e).group(1) for e in item["expected_articles"]}
        top = rerank(item["question"], vector_recall(item["question"], k=20), top=5)
        nos = {r["article_no"] for r in top}
        ok = bool(expected & nos)
        total += 1; hit += 1 if ok else 0
        print(f'{item["id"]} {"HIT " if ok else "MISS"} top5={sorted(nos, key=int)} expected={sorted(expected, key=int)}')
        for p in item.get("must_not", []):
            for r in top:
                if str(p) in r["text"]:
                    print(f'    !! must_not 出现在候选: {item["id"]} 第{r["article_no"]}条 :: {p}')
    rate = hit / total if total else 0
    print(f'检索命中率: {hit}/{total} = {rate:.0%}（出口条件 >= 80%）')
    return 0 if rate >= 0.8 else 1