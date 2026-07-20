# Paper Crawler — 可插拔式学术论文获取系统

> 状态：**设计阶段（Phase 0）** · 本仓库当前只包含设计文档与规划文本，尚无实现代码。
> 最后更新：2026-07-20

## 这是什么

一个面向个人科研使用的、可插拔式的学术论文获取系统。目标是：

1. **双模块获取**
   - **Open-Access 模块**：直接抓取开放资源——arXiv、SSRN（公开部分）、OpenReview、PMLR、CVF Open Access、ACL Anthology、NeurIPS Proceedings、AAAI OJS、NBER 等；
   - **Auth-Gated 模块**：通过用户自有的合法凭证（个人订阅 / 校园 IP / EZProxy / Shibboleth SSO）访问闭源出版社——Elsevier ScienceDirect、Wiley、OUP(Silverchair)、UChicago Press、INFORMS、IEEE Xplore、ACM DL、Cambridge、Springer、JSTOR 等。
2. **Venue 级能力**：获取会议/期刊的出版时间轴、期数（届数）历史、每期论文清单；支持"指定期刊指定卷期指定文章"的精确下载与全文抓取。
3. **完整 Pipeline**：discover → enumerate → resolve → fetch → extract → ingest 六阶段，幂等、可断点续爬、可观测。
4. **精确订阅**：对预印本平台（arXiv/SSRN）支持自定义 Topic/Tag 的精确搜索订阅，覆盖 CS/AI、Econ、Finance，防止内容过载。

## 合规红线（先读）

本系统**只**在用户自有访问权限内自动化获取行为：不绕过付费墙、不破解 CAPTCHA、不集成盗版源、遵守各站 rate limit 与 ToS，下载内容仅限本地个人科研使用，不做再分发。详见 [00-requirements.md](docs/design/00-requirements.md) 的"非目标与合规"。

## 仓库导航

| 目录 | 内容 |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | **全文档索引与状态表（从这里开始）** |
| [docs/plan/](docs/plan/) | 开发计划、进度、决策记录（ADR） |
| [docs/design/](docs/design/) | 需求、架构、模块、pipeline、数据模型等设计文档 |
| [docs/design/adapters/](docs/design/adapters/) | 每个站点/平台的专属爬虫设计 |
| [docs/catalog/](docs/catalog/) | 期刊、会议、出版社、预印本平台清单（venue registry 的文档形态） |
| [docs/testing/](docs/testing/) | 测试计划、验收标准、测试记录 |
| [docs/process/](docs/process/) | git 流程、文档/代码状态流程、文档规范 |
| [docs/research/](docs/research/) | 调研资料（类似开源项目、站点勘察记录） |
| [docs/diagrams/](docs/diagrams/) | 架构、pipeline、数据模型等 SVG 图 |
| [docs/logs/](docs/logs/) | 工作日志（按 session） |
| [docs/reports/](docs/reports/) | 阶段性报告 |

## 推荐阅读顺序

1. [docs/design/00-requirements.md](docs/design/00-requirements.md) — 需求与边界
2. [docs/design/01-architecture.md](docs/design/01-architecture.md) — 总体架构（配 [架构图](docs/diagrams/01-architecture.svg)）
3. [docs/design/02-plugin-framework.md](docs/design/02-plugin-framework.md) — 可插拔框架（Platform Adapter × Venue Spec 两层）
4. [docs/design/05-pipeline.md](docs/design/05-pipeline.md) — 六阶段 pipeline
5. [docs/design/06-data-model.md](docs/design/06-data-model.md) — 数据模型与入库
6. 其余按需查阅 [docs/INDEX.md](docs/INDEX.md)

## 给 AI/LLM 协作者

请先读 [AGENTS.md](AGENTS.md)——它定义了在本仓库工作的所有规范（文档状态机、front matter、INDEX 同步、日志要求、禁止事项）。
