"""上下文组装、生成与引用校验（红线 2/3/4 的执行点）。"""
import re
from .llm import chat
SYSTEM = ("你是法律知识库问答引擎。硬规则："
 "1) 只依据【给定条文】与【制度参考页】作答。引用原文的唯一合法形式：从给定条文某一条中连续复制一段文字（含标点，一字不改、不缩写、不拼接跨段），整行写为 > 【原文】 <复制内容>；做不到逐字复制就改用你自己的话分析并在句末标注（民法典第N条），严禁用引号包裹改写句；"
 "2) 不得引用给定材料之外的任何法条编号；材料覆盖不到的内容明确写“依据不足，待核实”；"
 "3) 涉及时效必须标注“现行有效”与施行日期；"
 "4) 正文之后逐行列出引用清单，格式：REF: 民法典第N条——仅列正文分析实际依据且能支撑结论的条文；若判断依据不足，只输出“依据不足，待核实”及一句理由，不得输出任何 REF 行；"
 "5) 最后一行固定输出：本内容仅供参考，不构成正式法律意见；重大事项请咨询执业律师。")
def assemble(question, nav_pages, reranked):
    arts = "\n\n".join(
        f"《中华人民共和国民法典》第{r['article_no']}条（{r['status']}，2021-01-01 施行）：\n{r['text']}"
        for r in reranked)
    nav = "\n\n".join(f"=== 制度参考页：{p['title']} ===\n{p['body'][:1600]}" for p in nav_pages[:3])
    return f"问题：{question}\n\n【给定条文】\n{arts}\n\n【制度参考页（编译产物，可参考归纳框架，不得当作原文）】\n{nav}"
def generate(context):
    return chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": context}], max_tokens=1400)
def _norm(s):
    return "".join(s.split())
def verify(answer, reranked, articles_dir):
    refs = re.findall(r"REF:\s*民法典第(\d+)条", answer)
    joined = _norm("\n".join(r["text"] for r in reranked))
    report = {"refs_ok": [], "refs_bad": [], "quotes_dropped": 0}
    for n in refs:
        in_top = any(r["article_no"] == n for r in reranked)
        has_file = (articles_dir / f"民法典第{n}条.md").exists()
        if in_top and has_file:
            report["refs_ok"].append(n)
        else:
            report["refs_bad"].append(n)
    lines = []
    for line in answer.splitlines():
        m = re.match(r"^>\s*【原文】\s*(.+)$", line)
        if m and _norm(m.group(1)) not in joined:
            report["quotes_dropped"] += 1
            lines.append("> （该引用未通过逐字校验，已剔除——请核对条文页原文）")
            continue
        lines.append(line)
    report["answer"] = "\n".join(lines)
    return report