"""CLI：python -m app.cli <cmd>（argparse，D7）。"""
import argparse, sys
from . import config
def main():
    ap = argparse.ArgumentParser(prog="viki_rag")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ping"); p.add_argument("--milvus", action="store_true")
    p = sub.add_parser("ingest"); p.add_argument("--law", default="民法典")
    p.add_argument("--lo", type=int, required=True); p.add_argument("--hi", type=int, required=True)
    p.add_argument("--no-embed", action="store_true")
    p = sub.add_parser("search"); p.add_argument("q"); p.add_argument("-k", type=int, default=5)
    sub.add_parser("lint")
    p = sub.add_parser("concepts"); p.add_argument("--limit", type=int, default=99)
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
    elif a.cmd == "concepts":
        from .concepts import generate_all
        generate_all(limit=a.limit)
if __name__ == "__main__":
    main()