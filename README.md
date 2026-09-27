# Paper Crawler — v2 重新开始

> 状态：**v2 调研与设计计划已完成，待评审；尚无实现代码**。最后更新：2026-09-27。
> v1（Phase 0–7 的单用户 CLI 实现与设计文档）已完整归档到分支 `archive/v1`（标签 `v1-final`），见 [docs/archive-v1.md](docs/archive-v1.md)。

## 这是什么

面向研究者的跨学科论文发现平台。它从合法来源持续收割论文，用可解释、可学习的个性化推荐，把"今天值得看的论文"做成一叠有限的卡片，用户靠滑动分拣；用户自己的机构权限只用于本人在用户侧取回全文。

- **来源**：一级来源为出版商、预印本、期刊与会议平台，覆盖数学、物理、化学、生物、心理学、经济、金融、商业管理、计算机与 AI；二级来源为仓库与聚合平台。支持名录共 187 条。
- **检索**：先收割、后联邦；统一查询语法树；主题-来源路由图（TSRG）；多用户 PostgreSQL 平台。
- **推荐**：可解释的价值模型，打分、点赞、收藏与评价，持续学习，三层双向匹配。
- **前端**：类小红书、抖音的极简卡片流，左右滑分拣，每日有限批次。

## 从这里开始

| 你想… | 阅读 |
|---|---|
| 5 分钟了解 v2 计划 | [docs/plan/v2/README.md](docs/plan/v2/README.md) |
| 看交互 demo 与视觉案例 | [docs/plan/v2/demo/paper-feed-demo.html](docs/plan/v2/demo/paper-feed-demo.html)（已发布：<https://claude.ai/artifact/YYZiiZjCVVeTzbESeFxqQr>） |
| 看架构裁决与待决事项 | [docs/plan/v2/00-design-brief.md](docs/plan/v2/00-design-brief.md)（§10–§12） |
| 看调研证据 | [docs/survey/README.md](docs/survey/README.md) → [调研综合](docs/survey/00-survey-synthesis.md) |
| 看支持的来源 | [docs/catalog/source-directory.md](docs/catalog/source-directory.md) |
| 看实施路线图 | [docs/plan/v2/09-roadmap-and-milestones.md](docs/plan/v2/09-roadmap-and-milestones.md) |
| 全部文档清单 | [docs/INDEX.md](docs/INDEX.md) |

## 合规红线（先读）

只经合法来源与用户自有授权凭证获取：遵守 robots.txt 与 ToS，保守限速，使用诚实可识别的 UA；不绕付费墙或 CAPTCHA，不接盗版源，不冒充；Google Scholar 不做自动化源。v2 是多用户平台：受限全文只在用户侧、用本人凭证、由本人显式触发时取回，并私有存放，**绝不在用户之间共享或再分发**。详见 [docs/plan/v2/08-compliance-security-privacy.md](docs/plan/v2/08-compliance-security-privacy.md)。

## v1 在哪里

```bash
git switch archive/v1
```

或者只看某个文件、不切换分支：

```bash
git show archive/v1:docs/design/01-architecture.md
```

也可以另开一个工作树并排对照：

```bash
git worktree add ../paper-crawler-v1 archive/v1
```

## 给 AI/LLM 协作者

请先读 [AGENTS.md](AGENTS.md)。
