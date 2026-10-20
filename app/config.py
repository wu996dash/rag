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
    "劳动合同法": {
        "path": "sources/中华人民共和国劳动合同法_20121228.docx",
        "law": "中华人民共和国劳动合同法",
        "abbr": "劳动合同法",
        "slug": "laodong-hetongfa",
        "id_base": 3000000,
        "passed": "2007-06-29",
        "effective": "2008-01-01",
        "revised": "2012-12-28",
        "status": "现行有效",
    },
    "劳动法": {
        "path": "sources/中华人民共和国劳动法_20181229.docx",
        "law": "中华人民共和国劳动法",
        "abbr": "劳动法",
        "slug": "laodong-fa",
        "id_base": 4000000,
        "effective": "1995-01-01",
        "status": "现行有效",
    },
    "调解仲裁法": {
        "path": "sources/中华人民共和国劳动争议调解仲裁法_20071229.docx",
        "law": "中华人民共和国劳动争议调解仲裁法",
        "abbr": "调解仲裁法",
        "slug": "tiaojie-zhongcai-fa",
        "id_base": 5000000,
        "effective": "2008-05-01",
        "status": "现行有效",
    },
    "劳动争议解释一": {
        "path": "sources/最高人民法院关于审理劳动争议案件适用法律问题的解释（一）_20201229.docx",
        "law": "最高人民法院关于审理劳动争议案件适用法律问题的解释（一）",
        "abbr": "劳动争议解释一",
        "slug": "laodong-zhengyi-jieshi-1",
        "id_base": 6000000,
        "effective": "2021-01-01",
        "status": "现行有效",
    },
    "劳动争议解释二": {
        "path": "sources/最高人民法院关于审理劳动争议案件适用法律问题的解释（二）_20250731.docx",
        "law": "最高人民法院关于审理劳动争议案件适用法律问题的解释（二）",
        "abbr": "劳动争议解释二",
        "slug": "laodong-zhengyi-jieshi-2",
        "id_base": 7000000,
        "effective": "2025-09-01",
        "status": "现行有效",
    },
    "工伤保险条例": {
        "path": "sources/工伤保险条例_20101220.docx",
        "law": "工伤保险条例",
        "abbr": "工伤保险条例",
        "slug": "gongshang-baoxian-tiaoli",
        "id_base": 8000000,
        "effective": "2004-01-01",
        "status": "现行有效",
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