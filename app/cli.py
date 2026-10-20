"""CLI：python -m app.cli <cmd>（argparse，D7）。ask 一次性提问；chat 常驻会话（模型只加载一次，P0）。"""
import argparse, sys, time
def _run(question, stream=True, profile=False):
    from .qa_graph import build
    g = build()
    if not profile:
        return g.invoke({"question": question, "stream": stream})
    merged, last, t0 = {}, time.time(), time.time()
    for chunk in g.stream({"question": question, "stream": stream}):
        node = next(iter(chunk))
        now = time.time()
        print(f"  [profile] {node}: {now - last:.1f}s", file=sys.stderr)
        last = now
        for k, v in chunk[node].items():
            merged[k] = v
    print(f"  [profile] 合计: {time.time() - t0:.1f}s（不含本进程模型加载）", file=sys.stderr)
    return merged
def _emit(st, streamed=True):
    rep = st.get("report") or {}
    if not streamed and rep.get("answer"):
        print(rep["answer"])
    print("\n--- 引用核对 ---")
    for n in rep.get("refs_ok", []):
        print(f"  [OK] 民法典第{n}条 -> wiki/articles/民法典第{n}条.md")
    for n in rep.get("refs_bad", []):
        print(f"  [未通过] 民法典第{n}条（不在合法引用集内，可能越权）")
    if rep.get("quotes_dropped"):
        print(f"  [剔除] {rep['quotes_dropped']} 条未通过逐字校验的引用")
def main():
    ap = argparse.ArgumentParser(prog="viki_rag")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    p = sub.add_parser("ingest"); p.add_argument("--law", default="民法典")
    p.add_argument("--lo", type=int, required=True); p.add_argument("--hi", type=int, required=True)
    p.add_argument("--no-embed", action="store_true")
    p = sub.add_parser("search"); p.add_argument("q"); p.add_argument("-k", type=int, default=5)
    sub.add_parser("lint")
    p = sub.add_parser("concepts"); p.add_argument("--limit", type=int, default=99)
    p = sub.add_parser("ask"); p.add_argument("q"); p.add_argument("--profile", action="store_true")
    p.add_argument("--no-stream", action="store_true")
    p = sub.add_parser("chat"); p.add_argument("--profile", action="store_true")
    sub.add_parser("eval")
    a = ap.parse_args()
    if a.cmd == "ping":
        from .vectors import client
        print("collections:", client().list_collections())
    elif a.cmd == "ingest":
        from .ingest_graph import build
        st = build(with_embed=not a.no_embed).invoke({"law": a.law, "lo": a.lo, "hi": a.hi})
        print({"article_count": st.get("article_count"), "pages": st.get("pages"), "embedded": st.get("embedded")})
    elif a.cmd == "search":
        from .vectors import search
        for h in search(a.q, a.k):
            print(f'[{h["distance"]:.3f}] {h["entity"]["law"]} 第{h["entity"]["article_no"]}条 :: ' + h["entity"]["text"][:60].replace("\n", " "))
    elif a.cmd == "lint":
        from .lint import run
        sys.exit(run())
    elif a.cmd == "ask":
        _emit(_run(a.q, stream=not a.no_stream, profile=a.profile), streamed=not a.no_stream)
    elif a.cmd == "chat":
        print("viki_rag 会话模式：模型只加载一次；输入问题回车即答，exit/空行退出。")
        try:
            while True:
                q = input("\n问> ").strip()
                if not q or q.lower() in ("exit", "quit"):
                    break
                t = time.time()
                _emit(_run(q, stream=True, profile=a.profile), streamed=True)
                print(f"（本題 {time.time() - t:.1f}s）")
        except (EOFError, KeyboardInterrupt):
            pass
    elif a.cmd == "eval":
        from .eval_runner import run_retrieval_eval
        sys.exit(run_retrieval_eval())
    elif a.cmd == "concepts":
        from .concepts import generate_all
        generate_all(limit=a.limit)
if __name__ == "__main__":
    main()