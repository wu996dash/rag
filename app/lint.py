"""wiki-lint：SCHEMA.md §5 机检清单脚本化。退出码非 0 = 存在违规。"""
import re, sys
from pathlib import Path
from . import config
from .docxload import docx_text
REQ = ["id:", "type:", "title:", "status:", "sources:", "updated_at:"]
ART_REQ = ["law:", "article_no:", "effective_date:"]
STATUS = {"现行有效", "已废止", "尚未生效"}
def _norm(s):
    return "".join(s.split())
def run():
    wiki = config.REPO / "wiki"
    fails = []
    src_norm_cache = {}
    pages = [p for p in wiki.rglob("*.md") if p.name != "README.md"]
    for p in pages:
        txt = p.read_text(encoding="utf-8")
        if not txt.startswith("---"):
            fails.append(f"{p.name}: 无 frontmatter"); continue
        fm = txt.split("---", 2)[1]
        for k in REQ + (ART_REQ if p.parent.name == "articles" else []):
            if k not in fm:
                fails.append(f"{p.name}: 缺字段 {k}")
        m = re.search(r"^status:\s*(\S+)\s*$", fm, re.M)
        if m and m.group(1) not in STATUS:
            fails.append(f"{p.name}: status 非法 {m.group(1)}")
        for sp in re.findall(r"^\s*-\s+(sources/\S+|.+\.docx)$", fm, re.M):
            if not (config.REPO / sp).exists():
                fails.append(f"{p.name}: sources 路径不存在 {sp}")
        for rel in re.findall(r"\]\(([^)#:]+?\.md)\)", txt):
            if not (p.parent / rel).exists():
                fails.append(f"{p.name}: 断链 {rel}")
        for q in re.findall(r"^> 【原文】 (.+)$", txt, re.M):
            sps = re.findall(r"^\s*-\s+(sources/\S+|.+\.docx)$", fm, re.M)
            ok = False
            for sp in sps:
                if sp not in src_norm_cache:
                    try:
                        src_norm_cache[sp] = _norm(docx_text(sp)) if sp.endswith(".docx") else _norm(Path(sp).read_text(encoding="utf-8"))
                    except Exception:
                        src_norm_cache[sp] = ""
                ok = ok or all(_norm(seg) in src_norm_cache[sp] for seg in q.split("……") if _norm(seg))
            if not ok:
                fails.append(f"{p.name}: 【原文】与 sources 不一致 :: {q[:24]}")
    idx = (wiki / "index.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\((?:\.\./)?(?:articles/|concepts/)?([^)]+\.md)\)", idx)) | \
             set(re.findall(r"\]\(([^)]+\.md)\)", idx))
    for p in (wiki / "concepts").glob("*.md"):
        if p.name == "README.md":
            continue
        inlink = any(p.name in q.read_text(encoding="utf-8")
                     for q in pages if q != p)
        if not inlink:
            fails.append(f"孤儿页: {p.name}")
    print(f"检查 {len(pages)} 页")
    if fails:
        print("FAIL", len(fails)); [print(" -", f) for f in fails[:40]]
        return 1
    print("PASS：全部机检项通过"); return 0
if __name__ == "__main__":
    sys.exit(run())