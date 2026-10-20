"""检索侧命中率评测：与生产链路同口径（查询改写 → 混合召回 → 重排 top-5）。"""
import re
from . import config
def run_retrieval_eval():
    import yaml
    data = yaml.safe_load((config.REPO / "eval" / "golden" / "诉讼时效.yaml").read_text(encoding="utf-8"))
    from .search import vector_recall, rerank
    from .query_rewrite import rewrite
    total = hit = 0
    for item in data:
        expected = {re.search(r"(\d+)", e).group(1) for e in item["expected_articles"]}
        eq = rewrite(item["question"])
        top = rerank(eq, vector_recall(eq), top=5)
        nos = {r["article_no"] for r in top}
        ok = bool(expected & nos)
        total += 1; hit += 1 if ok else 0
        print(f'{item["id"]} {"HIT " if ok else "MISS"} top5={sorted(nos, key=int)} expected={sorted(expected, key=int)}')
    rate = hit / total if total else 0
    print(f'检索命中率: {hit}/{total} = {rate:.0%}（出口条件 >= 80%）')
    return 0 if rate >= 0.8 else 1