"""维护回路（G4/M4）：效力变更传导——条文页 status、受影响制度页提示、Milvus 过滤位三步联动。"""
import re
from datetime import date
from . import config
def supersede(article_no: int, note: str, status: str = "已废止", replaced_by: str = ""):
    ap = config.REPO / "wiki" / "articles" / f"民法典第{article_no}条.md"
    txt = ap.read_text(encoding="utf-8")
    txt = re.sub(r"^status: .*$", "status: " + status, txt, flags=re.M)
    txt = txt.replace("## 时效说明\n",
        "## 时效说明\n\n**" + status + "（" + date.today().isoformat() + " 登记）**：" + note +
        ((" 替代依据：" + replaced_by + "。") if replaced_by else "") + "\n")
    ap.write_text(txt, encoding="utf-8")
    marked = []
    for cp in (config.REPO / "wiki" / "concepts").glob("*.md"):
        t = cp.read_text(encoding="utf-8")
        if f"民法典第{article_no}条" in t and "⚠️ 时效提示" not in t:
            t = t.rstrip() + ("\n\n## ⚠️ 时效提示\n\n本页引用的《民法典》第" + str(article_no) +
                "条已" + status + "（" + note + "）。本页结论需按替代依据重新编译，属维护待办。\n")
            cp.write_text(t, encoding="utf-8")
            marked.append(cp.name)
    from .vectors import set_status
    try:
        ok = set_status(config.SOURCES["民法典"]["id_base"], article_no, status)
    except Exception:
        ok = False
    return {"article": ap.name, "concepts_marked": marked, "milvus_snapshot_updated": ok, "authority": "wiki frontmatter（检索侧 post-gate 过滤）"}
def reinstate_demo(article_no: int):
    """演示回滚：git 还原页面 + Milvus 恢复现行有效（仅限维护流程演练）。"""
    import subprocess
    subprocess.run(["git", "checkout", "--", f"wiki/articles/民法典第{article_no}条.md"],
                   cwd=config.REPO, check=True)
    for cp in (config.REPO / "wiki" / "concepts").glob("*.md"):
        t = cp.read_text(encoding="utf-8")
        if "⚠️ 时效提示" in t:
            t = re.sub(r"\n## ⚠️ 时效提示\n.*?(?=\Z)", "\n", t, flags=re.S)
            cp.write_text(t, encoding="utf-8")
    from .vectors import set_status
    return set_status(config.SOURCES["民法典"]["id_base"], article_no, "现行有效")