# viki_rag · 法律知识库

**viki（LLM Wiki 知识编译）+ RAG 向量检索**的混合架构法律问答系统：入库时把法条"编译"成互链、带效力状态的结构化知识页（编译器），检索时以条文级向量保证每条引用可溯源到原文（证据链）。选型决策见 DECISIONS.md，任务依据见 任务描述.md，Agent 契约见 CLAUDE.md。

## 当前规模（2026-10-19）

- 语料：《民法典》官方全文（国家法律法规数据库导出 docx），已编译**总则编 204 + 买卖合同节选 14 = 218 条文页、25 制度页**
- 向量：Milvus `legal_articles`（稠密+稀疏双通道）+ `legal_concepts`（制度页导航）
- 评测：M3 全量 58 题 正确率 96% / 引用精确率 98% / 无据拒答 100% / 时效违规 0；M4 改造后回归 38/38 无退化

## 快速开始

```powershell
# 1) 环境（重依赖继承 anaconda base 的 torch/transformers）
uv venv --python 3.12 --system-site-packages .venv
uv pip install --python .venv pymilvus langgraph python-dotenv pyyaml

# 2) 配置：复制 .env.example 为 .env；密钥用系统环境变量 DASHSCOPE_API_KEY（代码自动回落）
# 前置条件：本机 Milvus 于 127.0.0.1:19531；BGE-M3 与 bge-reranker 权重路径见 .env

# 3) 自检
.\.venv\Scripts\python.exe -m app.cli ping     # Milvus 连通
.\.venv\Scripts\python.exe -m app.cli lint     # 全库机检（断链/逐字/时效/frontmatter）
```

## 日常命令

```powershell
python -m app.cli ask "对方答应还钱后诉讼时效怎么算？"   # 问答（流式输出+引用核对）
python -m app.cli chat                                  # 常驻会话（推荐演示用，模型只加载一次）
python -m app.cli eval                                   # 检索侧命中率
python -m app.eval_full                                  # 全量四维评测（65题约6分钟，3并发）
python -m app.eval_full --only 时效,J --workers 3        # 增量评测：按题目id/文件名过滤
python -m app.cli ingest --lo 1 --hi 204                 # 增量入库（幂等）
```

## 架构一图流

```
sources/官方docx ─ingest_graph→ wiki条文页+制度页+index ─双通道嵌入→ Milvus
问题 → 查询改写 → [制度页导航 ∥ 稠密+稀疏RRF召回top12] → 重排top5 → 组装 → qwen-plus生成 → cite_verify逐字校验 → 答案+可点开引用
时效权威 = wiki frontmatter status（检索 post-gate 过滤；废止需走 supersede 传导）
```

> 本内容仅供参考，不构成正式法律意见；重大事项请咨询执业律师。
## 性能（2026-10-20 P0 后实测）

- **GPU 已启用（2026-10-20）**：torch cu132 + RTX 4060，rerank 0.2s/题、双模显存 4.5GB
- chat 常驻会话热态单题 ~10s（大头变为 qwen-plus 生成 8-12s，流式首字 ~2s）；冷启动一次 ~25s


## Web 界面（M8，FastAPI + Vue + WebSocket）

```powershell
serve.cmd            # 或 .venv\Scripts\python.exe -m uvicorn app.api:app --port 8100
# 浏览器打开 http://127.0.0.1:8100
```
- 流式问答：改写/导航/召回/重排各阶段耗时实时可见，答案逐 token 输出，引用校验结果（OK/未通过/剔除）以标签呈现，点击即开对应条文页原文
- 接口：`WS /ws/ask`（事件协议 stage|token|final|verify|done|error）、`GET /api/stats`、`GET /api/page?path=wiki/...md`
- 前端开发模式：`cd web && npm run dev`（vite 代理到 8100）；生产构建 `npm run build` 后由 FastAPI 静态托管，单端口部署
