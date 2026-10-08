# Confluo

原名 Paper Crawler，现归属 [Orbit Labs](https://github.com/Orbit-Labs-AI)。项目仓库：[Orbit-Labs-AI/Confluo](https://github.com/Orbit-Labs-AI/Confluo)。

面向研究者的跨学科论文发现平台。它从合法来源持续收割论文，用可解释、可学习的个性化推荐，把"今天值得看的论文"做成一叠有限的卡片，由用户滑动分拣。用户自己的机构权限只用于本人在用户侧取回全文。

> **现状（2026-09-27）**：v2 设计已完成，等你评审；还没有实现代码。

## 从这里读

1. [v2 方案总览](docs/plan/v2/README.md)：一篇看完整个方案和需要你拍板的事。
2. 按兴趣读分篇：[需求](docs/plan/v2/01-vision-and-requirements.md)、[架构](docs/plan/v2/02-architecture.md)、[来源](docs/plan/v2/03-sources-and-corpus-pipeline.md)、[检索](docs/plan/v2/04-retrieval-and-routing.md)、[数据](docs/plan/v2/05-data-platform.md)、[推荐](docs/plan/v2/06-recommendation-and-matching.md)、[前端](docs/plan/v2/07-frontend-interaction.md)、[合规](docs/plan/v2/08-compliance-security-privacy.md)、[路线图](docs/plan/v2/09-roadmap-and-milestones.md)。
3. [交互 demo](docs/plan/v2/demo/paper-feed-demo.html)，也可以在线打开：<https://claude.ai/artifact/YYZiiZjCVVeTzbESeFxqQr>。
4. 查阅用：[来源分层与收集现状](docs/catalog/source-taxonomy.md)、[支持名录](docs/catalog/source-directory.md)、[venue 名录](docs/catalog/venues/README.md)、[评级体系](docs/catalog/venue-rankings.md)、[调研结论](https://github.com/Orbit-Labs-AI/team-hub/blob/main/%E9%A1%B9%E7%9B%AE/Confluo/02-%E7%A0%94%E7%A9%B6/v2%E8%B0%83%E7%A0%94%E7%BB%93%E8%AE%BA.md)（TeamHub）、[ADR 登记](docs/plan/decision-log.md)、[术语表](docs/GLOSSARY.md)。

全部文档清单见 [docs/INDEX.md](docs/INDEX.md)。

## 合规红线

只经合法来源和用户自有的授权凭证获取论文：遵守 robots.txt 与 ToS，保守限速，使用诚实可识别的 UA；不绕付费墙或 CAPTCHA，不接盗版源，不冒充他人；Google Scholar 不做自动化来源。受限全文只在用户侧、用本人凭证、由本人显式触发时取回，私有存放，**绝不在用户之间共享或再分发**。详见[合规](docs/plan/v2/08-compliance-security-privacy.md)。

## 分支与归档

| 位置 | 内容 |
|---|---|
| `main` | 当前文档（本分支） |
| 标签 `v2-drafts` | v2 设计阶段的完整长稿：调研全文、设计长稿、ADR 全文、过程记录 |
| 分支 `archive/v1`（标签 `v1-final`） | v1 单用户 CLI 的完整实现与文档 |

读取方法见[归档说明](docs/archive.md)，例如：

```bash
git show v2-drafts:docs/plan/v2/04-retrieval-and-routing.md
```

## 给 AI 协作者

先读 [AGENTS.md](AGENTS.md)。
