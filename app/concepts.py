"""制度页批量编译：qwen-plus 按 SCHEMA.md §1.2 生成正文，代码组装 frontmatter 并做
逐字引用校验——引用对不上官方文本的页面直接退回重生成或拒收（红线 1/3 的机器执行）。"""
import re
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from . import config
from .parser import parse_law
from .llm import chat
TOPICS = [
 {"title":"民事权利能力","slug":"minshi-quanli-nengli","lo":13,"hi":16},
 {"title":"民事行为能力","slug":"minshi-xingwei-nengli","lo":17,"hi":25},
 {"title":"监护","slug":"jianhu","lo":26,"hi":39},
 {"title":"宣告失踪","slug":"shengao-shizong","lo":40,"hi":45},
 {"title":"宣告死亡","slug":"shengao-siwang","lo":46,"hi":53},
 {"title":"个体工商户与农村承包经营户","slug":"gongti-gongshanghu","lo":54,"hi":56},
 {"title":"法人一般规定","slug":"faren-yiban-guiding","lo":57,"hi":75},
 {"title":"营利法人","slug":"yingli-faren","lo":76,"hi":86},
 {"title":"非营利法人","slug":"feiyingli-faren","lo":87,"hi":95},
 {"title":"特别法人","slug":"tebie-faren","lo":96,"hi":101},
 {"title":"非法人组织","slug":"fei-faren-zuzhi","lo":102,"hi":108},
 {"title":"民事权利","slug":"minshi-quanli","lo":109,"hi":115},
 {"title":"民事法律行为与意思表示","slug":"minshi-falv-xingwei-yisi-biaoshi","lo":133,"hi":142},
 {"title":"无效的民事法律行为","slug":"wuxiao-minshi-falv-xingwei","lo":144,"hi":146},
 {"title":"可撤销的民事法律行为","slug":"kexian-minshi-falv-xingwei","lo":147,"hi":152},
 {"title":"附条件与附期限的民事法律行为","slug":"futiaojian-fuqixian","lo":158,"hi":160},
 {"title":"代理","slug":"daili-yiban","lo":161,"hi":166},
 {"title":"无权代理、表见代理与代理终止","slug":"wuquan-daili-zhongzhi","lo":167,"hi":175},
]
SYSTEM = ("你是法律知识库的编译器。只输出 Markdown 制度页正文（从 ## 一句话规则 开始），"
 "硬规则：1) 凡以 > 【原文】 开头的行必须逐字摘录自给定条文文本，不得改写、不得凭记忆补充；"
 "2) 链接只允许 ../articles/民法典第N条.md 且 N 必须在给定条文清单内；"
 "3) 分析归纳放在非引用文字里；给定条文覆盖不到的内容一律写（待核实），不得写成确定表述；"
 "4) 结构顺序：## 一句话规则 / ## 适用条件 / ## 法律效果 / ## 例外与注意事项 / ## 核心依据 / ## 关联制度。"
 "核心依据节每条 = 一行 > 【原文】 引用 + 一行出处说明（——《中华人民共和国民法典》第N条第M款，条文页见 [民法典第N条](../articles/民法典第N条.md)）。")
FEWSHOT = """## 一句话规则
权利人主张权利、义务人同意履行、提起诉讼或申请仲裁等法定事由发生时，已过的时效期间归零，**重新计算**一整期（[民法典第195条](../articles/民法典第195条.md)）。

## 适用条件（法定事由，均可主动制造）
1. 权利人向义务人**提出履行请求**（催收注意留痕）；
2. 义务人**同意履行义务**（部分还款、还款计划、对账确认等）；
3. 权利人**提起诉讼或者申请仲裁**；
4. 与起诉/仲裁**具有同等效力**的其他情形（具体列举载于司法解释，原文未入库，援引前**待核实**）。

## 法律效果
- 事由发生时重新起算；涉诉讼/仲裁程序的，自**程序终结时**起重新计算；
- 可反复发生，无次数限制。

## 例外与注意事项
- 中断事由的证明责任在权利人；
- 与中止的区别：中断多因主观行权行为，中止限于最后六个月内的客观障碍（[第194条](../articles/民法典第194条.md)）。

## 核心依据
> 【原文】 有下列情形之一的，诉讼时效中断，从中断、有关程序终结时起，诉讼时效期间重新计算：
>
> ——《中华人民共和国民法典》第195条，条文页见 [民法典第195条](../articles/民法典第195条.md)

## 关联制度
[诉讼时效中止](诉讼时效中止.md)｜[诉讼时效](诉讼时效.md)"""
def _norm(s): return "".join(s.split())
def _abbr_of(topic):
    from . import config
    return config.SOURCES[topic.get("law", "民法典")]["abbr"]
def _arts(topic):
    if "ranges" in topic:
        out = []
        for ln, lo, hi in topic["ranges"]:
            out += [r for r in parse_law(ln) if lo <= r["no"] <= hi]
        return out
    rs = [r for r in parse_law(topic.get("law", "民法典")) if topic["lo"] <= r["no"] <= topic["hi"]]
    return rs
def _build_user(topic):
    rs = _arts(topic)
    txt = "\n\n".join(f"【第{r['no']}条】\n{r['text']}" for r in rs)
    from . import config as _c
    if "ranges" in topic:
        laws = [ln for ln, _, _ in topic["ranges"]]
        ms = [_c.SOURCES[ln] for ln in laws]
        intro = f"主题制度：《{topic['title']}》（涉及 {'、'.join(m['law'] for m in ms)}）\n\n【当前法律】本题可引用 {len(ms)} 部法律：{'、'.join(m['abbr'] for m in ms)}；"
        rules = f"链接格式 ../articles/<法名简称>第N条.md，禁止出现这之外的法名。\n\n"
        return (intro + rules + f"参照样板页正文（学结构与纪律，不要抄内容与其法名）：\n{FEWSHOT}\n\n给定条文（唯一可引用来源）：\n{txt}")
    m = _c.SOURCES[topic.get("law", "民法典")]
    return (f"主题制度：《{topic['title']}》（{m['law']} 第{topic['lo']}—{topic['hi']}条）\n\n"
            f"【当前法律】本题唯一可引用/可链接的法律是《{m['law']}》，简称{m['abbr']}；"
            f"一切引用与链接必须写成 ../articles/{m['abbr']}第N条.md，出现其他法名（如民法典）一律判违规。\n\n"
            f"参照样板页正文（学结构与纪律，不要抄内容与其法名）：\n{FEWSHOT}\n\n"
            f"给定条文（唯一可引用来源）：\n{txt}")
def _sanitize(body):
    """链接目标不存在 -> 降级为纯文本（SCHEMA §4.3 的机器执行：不得凭空新增页面）。"""
    def repl(m):
        label, target = m.group(1), m.group(2)
        tp = (config.REPO / "wiki" / "concepts" / target)
        if tp.exists() or target.startswith("../articles/") and (config.REPO / "wiki" / target.replace("../", "")).exists():
            return m.group(0)
        return f"{label}（制度页未建，已登记待入库）"
    return re.sub(r"\[([^\]]+)\]\((?!https?:)([^)]+?\.md)\)", repl, body)
def _validate(body, topic):
    arts = _arts(topic)
    allow = {r["no"] for r in arts}
    allow_stems = {f'{r["abbr"]}第{r["no"]}条' for r in arts}
    src = _norm("\n".join(f'{r["abbr"]}第{r["no"]}条 {r["text"]}' for r in arts))
    for q in re.findall(r"^> 【原文】 (.+)$", body, re.M):
        segs = [s for s in _norm(q).split("……") if s]
        if not all(s in src for s in segs):
            return f"引用与条文不符: {q[:30]}"
    for stem in re.findall(r"\]\(\.\./articles/([^)]+?)\.md\)", body):
        if stem not in allow_stems:
            return f"越权链接条文: {stem}"
    if "## 核心依据" not in body:
        return "缺 核心依据 节"
    return None
def generate_one(topic):
    title = topic["title"]
    path = config.REPO / "wiki" / "concepts" / f"{title}.md"
    if path.exists():
        return (title, "skip")
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _build_user(topic)}]
    for attempt in (1, 2):
        try:
            body = chat(msgs).strip()
            body = _sanitize(re.sub(r"^```(markdown)?", "", body).strip("` \n"))
            err = _validate(body, topic)
            if err is None:
                fm = (f"---\nid: concept/{topic['slug']}\ntype: concept\ntitle: {title}\n"
                      f"status: 现行有效\nsources:\n" + "".join(f"  - {r['source_path']}\n" for r in [ {"source_path": config.SOURCES[ln]["path"]} for ln,_,_ in topic.get("ranges", [(topic.get("law","民法典"),0,0)])]) + "updated_at: "
                      f"updated_at: {date.today().isoformat()}\n---\n\n")
                path.write_text(fm + body + "\n", encoding="utf-8")
                return (title, "ok")
            msgs.append({"role": "assistant", "content": body})
            msgs.append({"role": "user", "content": f"校验失败：{err}。只修正该问题后重新输出正文；注意链接与REF中的法名必须用当前法律简称。"})
        except Exception as e:
            return (title, f"error {e!r:.60}")
    return (title, "rejected(校验两次失败)")
def generate_all(limit=99):
    todo = TOPICS[:limit]
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(generate_one, todo))
    ok = sum(1 for _, s in results if s == "ok")
    print(f"制度页生成：ok={ok} / {len(results)}")
    for t, s in results:
        if s != "ok":
            print("  ", t, "->", s)
    return results