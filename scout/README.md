# Confluo Scout

本地单用户的 AI 会议论文检索服务：爬取 OpenReview、CVF、ECVA、ACL Anthology、PMLR、AAAI、IJCAI 的论文元数据、摘要、审稿分与录用等级，用 EmbeddingGemma 2 建向量库，用多跳收敛检索（HopLoop）和 Gemini Decisions API 排序，网页在 <http://127.0.0.1:8770>。

设计文档：[总览与架构](../docs/plan/scout/README.md)、[来源与爬虫](../docs/plan/scout/sources.md)、[检索与排序](../docs/plan/scout/retrieval.md)。

## 启动

前提：Colima（或其他 Docker 运行时）在运行，`docker context` 指向它；模型已在 `../.confluo/scout/models/embeddinggemma-2`。

```bash
make up      # 构建镜像并启动 scout 与 qdrant
make logs    # 看日志
make down    # 停止（数据保留）
```

开机自启：`brew services start colima`，容器带 `restart: unless-stopped`。

## 数据与凭证

- 数据目录 `../.confluo/scout/`（Git 忽略）：`db/scout.sqlite`（元数据、审稿分、FTS5）、`abstracts/`（每届次一代 zstd 分片）、`qdrant/snapshots/`、`models/`、`cache/http/`、`logs/`。qdrant 的工作数据在 Docker 命名卷 `confluo-scout_qdrant-storage`，空卷启动时从最新快照恢复。
- 凭证读 `../.confluo/config.toml`（只读挂载）：
  - `[auth.openreview]` 的 `username`、`password`：OpenReview 匿名访问已被挑战页拦截，Scout 用你本人的账号，token 只在内存里。
  - `[auth.gemini] api_key`：Gemini Decisions API（`gemini-decision-1`）。没有 key 时检索用本地评分，界面会标明。
  - `[scout] contact`：可选，写进爬虫 UA 的联系邮箱。

## 开发

```bash
make dev-qdrant   # qdrant 端口开到 127.0.0.1:6333
make dev-api      # 宿主机上跑 API（MPS），不启后台任务
make dev-web      # Vite 开发服务器，/api 代理到 8771
make check        # ruff、pytest、前端类型检查与构建
```

宿主机与容器不要同时写同一个 SQLite：`make embed-host` 会先停掉容器里的 scout，再用宿主机 GPU 批量向量化，完成后重启。

## 命令行

`scout editions`、`scout crawl <edition> [--reset] [--max-batches N]`、`scout embed`、`scout concepts`、`scout search "<查询>" [--mode exact] [--json]`、`scout discover`、`scout serve`。容器里用 `docker compose exec scout scout ...`，宿主机里在 `server/` 下用 `uv run scout ...`。

## 排障

- `CONFLUO_HOME` 指向不存在的目录时，Scout 退回仓库的 `.confluo/` 并在日志里警告。
- 某个来源报 `blocked`：挑战页或登录失败，主机冷却 24 小时，不会换 UA 重试；`drift`：页面结构变了，本次结果不入库，旧数据保留。
- 抓取进度和每个届次的状态在网页的“来源”页，也可以 `curl 127.0.0.1:8770/api/jobs`。
