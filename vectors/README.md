# vectors/ 向量层配置与缓存

- 本目录只放 Milvus 连接配置（*.yaml）与本地模型/embedding 缓存；向量数据本体存于 Milvus 服务器（MILVUS_URI，见 .env），不在本仓库；
- *.yaml 连接配置可提交；缓存与权重一律被 .gitignore 排除；
- collection legal_articles 由入库代码首次运行时自动创建（DECISIONS.md D3），禁止手工 DDL。
