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
LLM_API_KEY = env("LLM_API_KEY") or env("DASHSCOPE_API_KEY")  # 回落规则（红线：不落文件）
MILVUS_URI = env("MILVUS_URI", "http://127.0.0.1:19531")
EMBED_DEVICE = env("EMBED_DEVICE", "cpu")
EMBED_MODEL_PATH = env("EMBED_MODEL_PATH")
MILVUS_COLLECTION = "legal_articles"
# 官方文本登记册（sources/README 的机器可读镜像；新法入库须同步）
SOURCES = {
    "民法典": {
        "path": "sources/中华人民共和国民法典_20200528.docx",
        "law": "中华人民共和国民法典",
        "abbr": "民法典",
        "slug": "minfadian",
        "passed": "2020-05-28",
        "effective": "2021-01-01",
        "status": "现行有效",
        "total_articles": 1260,
    },
}