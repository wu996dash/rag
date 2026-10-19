# CLAUDE.md — viki_rag Agent 工作契约

本文件是所有 AI agent（Claude Code、Codex 等）在本仓库工作的持久契约。新会话先读本文件，再读 任务描述.md。三者分工：CLAUDE.md 管"怎么干活"，任务描述.md 管"做什么、做到什么程度"，sources/ 里的法律原文管"事实是什么"；技术选型为什么这么定，见 DECISIONS.md（D1–D7），不要重新翻案。

## 项目一句话

法律领域的编译型知识库：viki（LLM Wiki 知识编译范式）把法条、司法解释、案例编译成互链的 Markdown 知识页网络，RAG 向量检索保证每条引用可溯源到条文原文，三通道混合检索回答法律问题。

## 目录契约

| 路径 | 角色 | agent 权限 |
|---|---|---|
| sources/ | 法律原文与元数据 | 只读。原文任何修改都必须走重新入库流程，禁止直接编辑 |
| SCHEMA.md | 编译契约（页面模板、引用格式、时效规则） | 读 + 可维护；修改必须在提交信息里说明改了哪条规则 |
| wiki/ | AI 编译出的知识页 | 读 + 写；只通过入库/维护流程改动，禁止无来源地新增内容 |
| vectors/ | Milvus 连接配置与本地模型/embedding 缓存 | 连接配置可进 git；模型权重与向量缓存不进 git、不逐个审查（向量数据本体在 Milvus） |
| eval/ | 黄金问题集与评测脚本 | 读；新增评测题必须在题目旁注明来源与依据条文 |
| app/ | 流水线代码（M1 起创建） | 正常开发 |

## 绝对红线（违反任何一条 = 本次任务失败）

1. **禁止编造法条与案例**：一切条文引用必须能在 sources/ 定位到原文。找不到出处就写"待核实"，或者不写；
2. **时效标注**：引用条文必须带效力状态（现行有效 / 已废止 / 尚未生效）与生效日期。新法入库时，被替代的旧条文必须同步标注"已废止/被替代"；
3. **条文内容禁止转述**：制度页的"核心依据"字段必须逐字引用原文；回答用户时不得用模型复述冒充条文原文；
4. **免责声明**：面向用户的输出必须包含"本内容仅供参考，不构成正式法律意见"；
5. **保密**：.env 与 API key 不进仓库；不摄取、不编译任何未脱敏的真实当事人材料。

## Wiki 页面规范

- 每页以 YAML frontmatter 开头，必填：id、type（concept|article|claim|case|index）、title、status、sources（来源文件列表）、updated_at。条文页另加 law、article_no、effective_date；案例页另加 case_no、court、judgment_year；
- 链接：只用标准 Markdown 相对链接，不用 [[wikilink]]。每个制度页至少链接一个条文页和 index.md；被链接页要能反向找到来源页（frontmatter 的 sources 承担反向索引）；
- 命名：条文页如 wiki/articles/民法典第188条.md；制度/案由/案例页用规范法律名称；id 用稳定英文 slug（如 concept/su-song-shi-xiao），改名时保留旧 id 为别名；
- 一个事实只写一处：条文原文与时效信息以条文页为准，制度页引用而不复制。

## 工程规范（选型依据见 DECISIONS.md D1–D7）

- Python 3.12，依赖用 uv 管理（uv sync / uv run pytest），代码风格 ruff；
- LLM 调用一律走 `app/llm.py` 统一入口（OpenAI 兼容协议，默认通义 Qwen-Plus），端点/模型只从环境变量读取：`LLM_BASE_URL` / `LLM_MODEL`；密钥优先读 `LLM_API_KEY`，未设置则回落系统环境变量 `DASHSCOPE_API_KEY`（本机已有且实测可用，2026-10-19）；不把密钥复制进 .env 或仓库；不硬编码供应商 URL，不散写 HTTP 请求；
- Embedding 用本地 BGE-M3（FlagEmbedding，1024 维），重排用 bge-reranker-v2-m3；两套权重本机已有（路径在 `.env` 的 `EMBED_MODEL_PATH` / `RERANKER_PATH`），禁止代码触发重复下载；运行设备走 `EMBED_DEVICE`，显存 OOM 时自动降级 CPU 并打日志；
- 向量库只用 Milvus：连接串 `MILVUS_URI`（默认 `http://127.0.0.1:19531`，本机已运行实例）；collection `legal_articles` 的 schema 以 任务描述.md §6 为准，首次入库由代码自动创建，禁止手工 DDL，禁止引入 Qdrant/FAISS 等其他向量库；
- CLI 用 argparse，子命令 `ingest|ask|lint`，入口 `python -m app.cli`；
- 测试：编译、检索、引用校验的核心逻辑必须有 pytest 用例（图节点按下方约定写成纯函数，直接构造 state 断言）；修改 wiki/ 后必须先跑 wiki-lint（断链、孤儿页、frontmatter 缺字段、wiki 与 sources 内容不一致）再提交；eval/ 新增题目必须注明来源与依据条文并跑全量评测确认无回归；
- 提交信息：动宾短语，简洁；一个流程环节一个提交；
- 语言：文档与用户可见文案用中文，代码标识符用英文。

## LangGraph 图节点约定

- 状态用 TypedDict（ingest 与 qa 各一个）；v1 不接 checkpointer，单轮执行；
- 节点尽量写成纯函数：输入 state，输出需更新的 state 字段；副作用只允许集中在三类节点——wiki 编译节点（写 wiki/）、`embed&index`（写 Milvus）、`generate`（对外输出回答）；
- `qa_graph` 的 `nav_index` 与 `vector_search` 为并行分支，`rerank` 节点汇合；检索固定策略：稠密 top-20 → 重排 top-5，稀疏混合检索须先满足 M4 评测条件再开（D4）；
- `cite_verify` 将回答中每条引用与 sources/ 原文逐条比对，对不上的引用降级为"依据不足"，不得输出。

## 工作方式

1. **入库编译** = 读 SCHEMA.md → 读一段 sources 原文 → 新建或更新受影响的 wiki 页（合并进已有页面，而不是另起一页堆重复内容）→ 补链接与 index 条目 → 条文原文切块进向量层；
2. **改动前先读**：编辑任何 wiki 页面前先读全页，保留原有链接关系；页面冲突时 sources 原文优先于任何 wiki 页；
3. **决策记录**：遇到新的架构取舍，先查 DECISIONS.md 是否已有结论；推翻既有决策须新增编号条目并写明理由；重要决定记入 DECISIONS.md；
4. **不确定就问，但先查**：法律概念拿不准时，先查 sources/ 与已有页面，仍无把握则在页面标注"待核实"并继续，不要卡住整个流水线。

## 当前状态（2026-10-19）

M4 已完成（2026-10-19）：查询改写+稠密稀疏混合召回+制度页向量导航（D8，G-038 修复）、时效权威 post-gate（D9）、supersede/reinstate 传导演练通过；增量入库 585-598 与特殊诉讼时效期间页；回归前 38 题全对（m4-regression-partial-37of58.jsonl）。环境资源已核验（2026-10-19）：`DASHSCOPE_API_KEY` 实测 qwen-plus 返回 200；bge-m3 与 bge-reranker-v2-m3 权重完整（`E:\edurag\Itcast_qa_system\rag_qa\models\`）；Milvus 127.0.0.1:19531 TCP 连通。下一步是 M5——收尾验收：跑完 58 题全量回归（含 G-038/NB/SOL 批次）、产出 v1 验收报告、README 快速开始（已有）、清理口径；后续扩展方向：GPU 加速（D10）、司法解释与案例入库、合同编/侵权编扩编、案由页。

目录结构或规则发生变化时，在同一个提交里更新本文件与 任务描述.md；选型变化必须先更新 DECISIONS.md。