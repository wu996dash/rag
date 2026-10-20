"""qa_graph（LangGraph，D5）：nav_index -> vector_search -> rerank -> assemble -> generate -> cite_verify。
导航与检索为先后两跳（assemble 处汇合），状态为 TypedDict，无 checkpointer。"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
class QAState(TypedDict, total=False):
    question: str
    expanded: str
    stream: bool
    nav: list
    hits: list
    top: list
    context: str
    answer: str
    report: dict
def node_rewrite(st):
    from .query_rewrite import rewrite
    return {"expanded": rewrite(st["question"])}
def node_nav(st):
    from .search import nav_select
    return {"nav": nav_select(st.get("expanded") or st["question"])}
def node_vsearch(st):
    from .search import vector_recall
    return {"hits": vector_recall(st.get("expanded") or st["question"])}
def node_rerank(st):
    from .search import rerank
    # 重排查询用语义桥接后的法学术语串（叙事题实测与法条文本词汇墙同解）
    return {"top": rerank(st.get("expanded") or st["question"], st["hits"])}
def node_assemble(st):
    from .answer import assemble
    return {"context": assemble(st["question"], st["nav"], st["top"])}
def node_generate(st):
    if st.get("stream"):
        from .llm import chat_stream
        from .answer import _messages
        parts = []
        for d in chat_stream(_messages(st["context"])):
            parts.append(d)
            print(d, end="", flush=True)
        print()
        return {"answer": "".join(parts)}
    from .answer import generate
    return {"answer": generate(st["context"])}
def node_verify(st):
    from .answer import verify
    from . import config
    return {"report": verify(st["answer"], st["top"], config.REPO / "wiki" / "articles", st.get("nav"))}
def build():
    g = StateGraph(QAState)
    for name, fn in [("query_rewrite", node_rewrite), ("nav_index", node_nav), ("vector_search", node_vsearch),
                     ("rerank", node_rerank), ("assemble", node_assemble),
                     ("generate", node_generate), ("cite_verify", node_verify)]:
        g.add_node(name, fn)
    g.set_entry_point("query_rewrite")
    g.add_edge("query_rewrite", "nav_index")
    g.add_edge("nav_index", "vector_search")
    g.add_edge("vector_search", "rerank")
    g.add_edge("rerank", "assemble")
    g.add_edge("assemble", "generate")
    g.add_edge("generate", "cite_verify")
    g.add_edge("cite_verify", END)
    return g.compile()