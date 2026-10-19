"""ingest_graph（LangGraph，D5）：parse -> compile -> embed&index。
节点为纯函数式：副作用集中在 compile 的写页与 embed 的写 Milvus。"""
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
class IngestState(TypedDict, total=False):
    law: str; lo: int; hi: int
    article_count: int
    pages: dict
    embedded: int
    notes: List[str]
def node_parse(st: IngestState) -> IngestState:
    from .parser import parse_law
    recs = [r for r in parse_law(st["law"]) if st["lo"] <= r["no"] <= st["hi"]]
    return {"article_count": len(recs)}
def node_compile(st: IngestState) -> IngestState:
    from .pages import render
    return {"pages": render(st["law"], st["lo"], st["hi"])}
def node_embed(st: IngestState) -> IngestState:
    from .vectors import upsert_articles
    return {"embedded": upsert_articles(st["law"], st["lo"], st["hi"])}
def build(with_embed=True):
    g = StateGraph(IngestState)
    g.add_node("parse", node_parse)
    g.add_node("compile", node_compile)
    g.set_entry_point("parse")
    g.add_edge("parse", "compile")
    if with_embed:
        g.add_node("embed_index", node_embed)
        g.add_edge("compile", "embed_index")
        g.add_edge("embed_index", END)
    else:
        g.add_edge("compile", END)
    return g.compile()