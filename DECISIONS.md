# DECISIONS.md — 技术选型决策记录

选型于 2026-10-19 在 Plan 模式逐项确认，共 7 项（D1–D7）。任务描述.md §6 与 CLAUDE.md 工程规范引用这些编号。推翻任何一条须在此新增编号条目并写明理由，不要静默改选。

## D1 主力 LLM 通道 —— OpenAI 兼容 API，默认通义 Qwen-Plus

- **定案**：DashScope OpenAI 兼容端点，`LLM_MODEL=qwen-plus`；base_url/model 全走环境变量，换供应商不改代码。
- 备选项：DeepSeek-V3（中文好、成本低，用户改选 Qwen-Plus）；Claude API（长文编译质量最好，但价格高且国内直连需代理）；本地 Ollama（本机未安装，8GB 显存只能跑 7~8B 量化模型，编译质量明显下降）。

## D2 Embedding —— BGE-M3 本地推理

- **定案**：FlagEmbedding，1024 维稠密向量，cuda fp16；OOM 自动降级 CPU（`EMBED_DEVICE`）。
- 放弃：API Embedding（DashScope/OpenAI）——按量付费，且中文法律检索效果不如 BGE-M3。

## D3 向量库 —— 用户自有 Milvus 服务器（127.0.0.1:19531）

- **定案**：pymilvus `MilvusClient` 连接本机已运行的 Milvus；gRPC 端口 19531 已实测可达。collection `legal_articles`：pk(int64 auto) + law_name/article_no/status/effective_date/source_path（varchar 标量）+ text（varchar）+ embedding（FLOAT_VECTOR 1024, COSINE, HNSW M=16/efConstruction=200）；首次入库自动建 collection；稀疏向量列预留不启用。
- 改选过程：BGE-M3+Qdrant 嵌入式（最初推荐；被用户已有 Milvus 实例取代）；Milvus Lite 嵌入式（放弃：已有服务器版，无需重复）；FAISS（放弃：增删要重建索引，维护回路易踩坑）。

## D4 检索链路 —— 稠密 top-20 + 本地重排 top-5

- **定案**：bge-reranker-v2-m3 本地 GPU 重排；直接对应"引用精确率 >= 95%"验收指标。
- 放弃：纯稠密 top-k——相近条文（普通时效 vs 最长保护期）易混排，引用校验失败率升高。
- 推迟：dense+sparse 混合检索 + RRF——schema 要多存稀疏列，留到 M4 之后按评测结果决定（M4 出口条件挂钩）。

## D5 编排框架 —— LangGraph

- **定案**：两个图：`ingest_graph`（parse → compile → link → embed&index）、`qa_graph`（nav_index ∥ vector_search → rerank → assemble → generate → cite_verify）；v1 不接 checkpointer。节点约定见 CLAUDE.md"LangGraph 图节点约定"。
- 改选过程：自研轻量 Python（最初推荐，链路最透明；用户指定 LangGraph）。放弃：LlamaIndex——wiki 编译、传导更新等定制逻辑与框架抽象相冲突。

## D6 首域与语料来源 —— 民法典总则编 + 手动入库

- **定案**：v1 首个专题域为民法典总则编（诉讼时效制度组起步），验收指标以该域黄金问题集为准；文本从国家法律法规数据库 / 最高法官网手动下载入 sources/ 并登记来源。
- v1 不做：爬虫、OCR、裁判文书网抓取。

## D7 工程基线 —— Python 3.12 + uv + ruff + pytest + argparse

- **环境契约**（见 .env.example）：`LLM_BASE_URL` / `LLM_MODEL` / `MILVUS_URI` / `EMBED_DEVICE` / `EMBED_MODEL_PATH` / `RERANKER_PATH`；密钥优先 `LLM_API_KEY`，回落系统变量 `DASHSCOPE_API_KEY`（2026-10-19 实测 qwen-plus 200）。
- 本机事实：Python 3.12.4、Node 24、RTX 4060 8GB、无 Docker（Milvus 已在跑，不需要）、19531 端口连通已验证；`DASHSCOPE_API_KEY`（User 作用域）与 `DEEPSEEK_API_KEY` 均已在系统环境变量。
- 模型权重复用本机已有下载（勿重复拉取）：`E:\edurag\Itcast_qa_system\rag_qa\models\bge-m3`（pytorch_model.bin 2.2GB）与同目录 `bge-reranker-v2-m3`（safetensors 2.2GB）；两者可同时驻留 8GB 显存。
## D8 查询理解与检索修正层（M4，G-038 实证驱动）—— 2026-10-19

- **定案**：问答链路前置 `query_rewrite` 节点（qwen-plus 把叙事提问扩展为法学术语串，改写查询同时用于召回、导航与重排）；制度页建向量索引 `legal_concepts` 做语义导航；引用合法源 = 重排 top-5 ∪ 导航制度页【原文】块（制度页逐字性已由 lint 链保证）。
- 背景：M3 唯一真实失败 G-038——叙事问题与抽象法条存在词汇墙，纯稠密与纯稀疏均失效；修复后该题回答完整正确、REF 全过核验。

## D9 时效权威位置 —— wiki frontmatter（检索 post-gate 过滤），Milvus status 仅快照

- **定案**：废止/恢复以条文页 `status` 为唯一权威，向量层召回后按 wiki 状态过滤（`include_abolished=True` 可显式查废止层）；Milvus 标量更新受最终一致性延迟影响，不作为过滤保证。
- 放弃：仅靠 Milvus 标量 filter（实测 pymilvus 3.0 + Milvus 2.4.4 强一致读仍存在写后延迟，一拍滞后）。

## D10 待办确认

- ~~GPU 版 torch 未装成~~ **已解决（2026-10-20）**：本机原装有 CUDA 13.3 工具包（nvcc 可用，驱动 610.47）；经 reg-rag 项目的官方索引 download.pytorch.org/whl/cu132 + 其 .uv-cache 缓存复用，13 秒装上 torch 2.14.1+cu132。GPU 实测：rerank 12 对 0.20s（CPU 5-7s）、两模同驻显存 4.55GB、embed 缓存命中 0ms。附带修复：numpy 钉 <2（共享 base 的 scipy/sklearn）、嵌入与重排权重显式 .to(device)。
## D11 P0 性能包（2026-10-20）—— 不改质量口径的延迟治理

- **定案**：① 查询嵌入进程内缓存（profile 实测 vector_search 0.0s，同一文本三次前向变一次）；② 重排文档截断 800→400 字（rerank 20-40s→~5s，法条长度所受影响为零）；③ ask/chat 流式输出（首 token ~2s，体感大幅改善）；④ 常驻 chat 会话消除每问 ~20s 模型冷加载；⑤ ask --profile 节点级计时进入 CLI。
- **试错记录**：候选池 12→8 曾导致 SOL-003 回归 MISS（第195条跌出召回池）——回滚保持 k=12；结论：**召回池是质量红线，延迟优化只能动"每对成本"（截断/加速），不能动"池子大小"**，除非重新跑 58 题全量回归证明无损。
- **验证**：检索命中率 5/5 恢复（eval_runner 已升级为生产链路同口径：改写+混合+post-gate）；SOL 复测回答引用逐字校验 2/2 通过。

## D12 评测吞吐（2026-10-20）—— 并行化 + 限流治理

- 定案：评测引擎 ThreadPool 并行（workers=3，GPU 前向加锁串行）+ 进程内模型预热 + 429 指数退避（retries=5）+ 失败题二轮重排队 + `--only` 增量过滤。全量 65 题 957s → 324s（2.9x）。
- 教训：判官模型曾尝试降级 qwen-turbo（快 3-5x），实测该账号 turbo 独立限速直接 429，判官保持 qwen-plus，模型名走 LLM_MODEL_JUDGE 可配置。
- 附带修复：REF 校验支持法律全称→简称映射（修 J-004 假阴性）。


## D13 服务化架构（M8，2026-10-20）—— FastAPI + Vue3 + WebSocket 单端口

- **定案**：后端 FastAPI（uvicorn），`/ws/ask` 事件协议（stage/token/verify/final/done），同步 GPU/推理生成器经 queue+asyncio.to_thread 桥接到异步 WS；前端 Vue3+Vite+marked，构建产物由 FastAPI StaticFiles 同端口托管（开发期 vite proxy）。默认端口 8100（本机 8000 已被其他程序占用，不动它）。
- 理由：qa_graph 本地部分 GPU 化后 <2.5s，体感延迟集中在 LLM 生成——流式事件协议把阶段耗时与 token 全部前置可见，引用校验结果做成可点击原文核对，是法律场景信任建设的一部分。


## D14 指标分层与判官校准（A 专项，2026-10-20）

- **定案**：引用质量拆两层——①**引用精确率（硬，阻塞验收，出口≥95%）**：REF 指向真实条文页 + 【原文】逐字一致 + 在合法引用集内，由 cite_verify 机械判定（当前 100%），不依赖判官；②**支撑度（软，监控指标，<90% 报警）**：判官 v3（判例规则：背景性支撑判1、具体数字/期限张冠李戴判0），单次波动 ±5-8%（R8=89%、rescore=95%），只作趋势监控。
- 方法论：判官改动一律先经 `app/rescore.py` 对同一答案集 A/B 重打分（几分钟），人工抽验归属句为最终仲裁（v3 抽验 3 题 6 句全部翻案正确），通过后才全量落地。
- 口径修订：任务描述 §2 引用精确率按硬口径执行，支撑度不进验收；G-039 归口=召回波动（R8 已答对），长期观察。


## D15 质量闭环两件套（C，2026-10-20）—— 反馈回流 + 夜间值守

- **定案**：① Web 回答级 👍/👎（👎强制进人工复核队列，`feedback --draft` 半自动生成评测题，人工补 expected 后进 golden——反馈不直接改知识，只变成考卷）；② 每日 21:00 cron automation 跑全量评测，按 D14 硬指标报警、软指标静默归档，正常不打扰。
- 边界：反馈数据 eval/feedback.jsonl 为运行时数据不进版本库；夜间任务依赖本机开机，缺跑不补（如需可靠值守再议云端）。


## D16 账号体系与用户数据落库（2026-10-20）

- **定案**：登录/注册 + 双角色（user/admin）+ 会话记忆（每人 LRU 5 条）；users/tokens/conversations 三表存本机 MySQL 8.0.12（127.0.0.1:3306），启动自动建库建表；应用使用**专用最小权限账号** viki_rag（仅授权 viki_rag 库），root 只在初始化用一次；密码 sha256+per-user salt+pepper。
- 管理员专属接口 /api/materials：录入即登记（sources/README 自动追加"待核验待编译"），**不做自动编译**（保持人工核验闸门）；普通用户 403。
- WS /ws/ask 强制 token 鉴权（4401）。验收：10 项断言全过（登录/隔离/LRU 6→5/403/录入落盘/WS 拒绝）。

## D17 向量层事故记录与统一主键（2026-10-20）

- **事故**：一次数据一致性审计脚本自身存在方案混用 bug（新主键 no×10 与旧主键 no 跨条号重叠），误删 1535 行合法向量。**wiki/sources 零损失，向量层按设计可重建**——115 秒全量重建 2493 行，逐法页/向量对齐。
- **定案**：全库统一新主键 `id_base + no×10 + subn`（附条占 1-9），旧方案行全部清除；任何审计/清理脚本必须先通过"逐法 行数==页数"断言，禁止基于推测定性删除。
- **教训**：删除操作前必须 dry-run 打印样本人工核对；本次若先打印"待删的民法典 1134 行"即可发现异常。

## D18 运行环境迁移到 Docker（2026-11-02）—— 端口改口 + torch 导入顺序

- **背景**：原环境是"phpstudy 原生 MySQL 3306 + 本机原生 Milvus 19531"。2026-11-02 起基础设施改由 Docker 承载：Milvus（standalone + etcd + minio + redis）映射 **19530**，MySQL 8.0.43 映射 **13306**；原 phpstudy MySQL 与 19531 端的 Milvus 均已不存在。
- **定案**：`.env` 改 `MILVUS_URI=http://127.0.0.1:19530`、`MYSQL_PORT=13306`（D3/D16 的端口描述随之失效，选型本身不变：仍是 Milvus + MySQL 专用最小权限账号）。Docker MySQL 中重建 `viki_rag` 库与 `viki_rag` 账号（`GRANT ALL ON viki_rag.*`，不用 root），`auth.init_db()` 启动自动建表。
- **向量层按 D17 重建**：新 Milvus 实例无 `legal_articles` / `legal_concepts`，但 wiki/ 与 sources/ 完好。按现有 sources 重新 parse+embed（2493 条，87s）+ 制度页导航（98 页，9s），逐法行数==页数核对通过。
- **事故与修复：torch 的 WinError 1114**。现象：`from pymilvus import MilvusClient` 之后再 `import torch` 必崩（`c10.dll` 初始化失败），单独 import torch 正常。根因：pyarrow 包内自带 `msvcp140.dll`，pymilvus→pandas→pyarrow 先加载后，Windows 把这份运行库解析给了 torch。**定案**：`app/__init__.py` 里先 `import torch` 再让其它模块加载，一行排序覆盖 CLI/API/脚本全部入口；不删 pyarrow（pymilvus 需要）。
- **注**：`get_collection_stats()` 在本版 pymilvus+Milvus 组合下恒返回 `row_count=0`，核对行数一律用 `query(filter="", output_fields=["count(*)"])`，勿据 stats 判断空库。