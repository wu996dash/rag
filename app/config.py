"""全局配置：只从环境变量读取（CLAUDE.md 工程规范 D1/D2/D3/D7）。"""
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass
REPO = Path(__file__).resolve().parents[1]
def env(name, default=None):
    v = os.getenv(name)
    return v if v else default
LLM_BASE_URL = env("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = env("LLM_MODEL", "qwen-plus")
LLM_MODEL_JUDGE = env("LLM_MODEL_JUDGE", "qwen-plus")  # turbo 在本账号配额独立限速(实测429)，判官保持 plus；如需换模型走 LLM_MODEL_JUDGE
LLM_API_KEY = env("LLM_API_KEY") or env("DASHSCOPE_API_KEY")  # 回落规则（红线：不落文件）
MILVUS_URI = env("MILVUS_URI", "http://127.0.0.1:19531")
EMBED_DEVICE = env("EMBED_DEVICE", "cpu")
EMBED_MODEL_PATH = env("EMBED_MODEL_PATH")
RERANKER_PATH = env("RERANKER_PATH")
MILVUS_COLLECTION = "legal_articles"
# 官方文本登记册（sources/README 的机器可读镜像；新法入库须同步）
SOURCES = {
    "民法典": {
        "path": "sources/中华人民共和国民法典_20200528.docx",
        "law": "中华人民共和国民法典",
        "abbr": "民法典",
        "slug": "minfadian", "id_base": 1000000,
        "passed": "2020-05-28",
        "effective": "2021-01-01",
        "status": "现行有效",
        "total_articles": 1260,
    },
    "诉讼时效规定": {
        "path": "sources/诉讼时效规定_20201223.md",
        "law": "最高人民法院关于审理民事案件适用诉讼时效制度若干问题的规定",
        "abbr": "诉讼时效规定",
        "slug": "susong-shixiao-guiding",
        "id_base": 2000000,
        "effective": "2020-12-23",
        "status": "现行有效",
    },
}