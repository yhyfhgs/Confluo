# AGENTS.md — AI/LLM 协作者工作规范

> 适用对象：所有在本仓库工作的 AI 助手（Claude Code、其他 LLM agent）及其 subagent。
> 人类维护者同样建议遵循。最后更新：2026-07-20。

## 0. 一句话定位

本仓库是"Paper Crawler"论文获取系统的**设计与知识库**（docs-as-code）。当前处于设计阶段：产出是文档与图，不是代码。进入实现阶段后，代码与文档同库演进。

## 1. 开始任何工作之前

1. 读 [README.md](README.md) 了解项目定位。
2. 读 [docs/INDEX.md](docs/INDEX.md) —— 它是全部文档的索引与状态表，**是唯一可信的文档清单**。
3. 读 [docs/plan/progress.md](docs/plan/progress.md) 了解当前进度与下一步。
4. 若你的任务涉及某个设计域，先读该域文档的 front matter 确认状态（见 §3）。
5. 重大方向性问题先查 [docs/plan/decision-log.md](docs/plan/decision-log.md)：已有决策不要擅自推翻；确需推翻，新增一条 ADR 标注 supersedes 并说明理由。

## 2. 目录职责（放东西之前先看这里）

| 路径 | 放什么 | 不放什么 |
|---|---|---|
| `docs/plan/` | 计划、进度、决策记录 | 设计细节 |
| `docs/design/` | 系统/模块设计文档 | 站点调研原始资料 |
| `docs/design/adapters/` | 每个平台/站点的爬虫设计 | venue 清单（去 catalog） |
| `docs/catalog/` | venue/出版社/平台清单 | 爬取策略细节（去 adapters） |
| `docs/testing/` | 测试计划、验收标准、测试记录 | — |
| `docs/process/` | git/状态/文档流程规范 | — |
| `docs/research/` | 调研原始资料、外部项目笔记 | 我们自己的设计结论（提炼后写入 design） |
| `docs/diagrams/` | SVG 源文件 | 位图；文档内嵌 base64 |
| `docs/logs/` | 每个工作 session 的日志 | — |
| `docs/reports/` | 阶段性汇总报告 | 日常流水（去 logs） |
| （未来）`src/`、`tests/`、`venues/` | 代码、测试、venue 配置 | 现阶段不建 |

## 3. 文档状态机与 front matter（必须遵守）

每个 `docs/**/*.md`（除 INDEX/logs/reports）头部必须有 YAML front matter：

```yaml
---
title: 文档标题
status: draft | review | approved | implemented | deprecated
owner: fable5   # 主要作者/责任者
updated: 2026-07-20
---
```

状态流转规则见 [docs/process/status-workflow.md](docs/process/status-workflow.md)。要点：

- 新文档一律 `draft`。
- `approved` 的文档改动实质内容必须：降回 `review`，或在 decision-log 记录变更理由。
- 实现代码只能依据 `approved`（或更高）状态的设计文档开工。
- 废弃文档不删除，改 `deprecated` 并在顶部注明替代文档。

## 4. 改动文档时的义务（checklist）

- [ ] 更新该文档 front matter 的 `updated` 日期。
- [ ] 若新增/删除/改名文档：同步更新 [docs/INDEX.md](docs/INDEX.md)。
- [ ] 若新增 FR/AC：同步维护 [acceptance-criteria.md](docs/testing/acceptance-criteria.md) 末尾的 FR→AC 覆盖映射表（D-016）。
- [ ] 若引入新的全库术语：在 [docs/GLOSSARY.md](docs/GLOSSARY.md) 增补单点定义。
- [ ] 若做出新的架构级决策：追加到 [docs/plan/decision-log.md](docs/plan/decision-log.md)（ADR 格式，编号递增）。
- [ ] 当日工作在 `docs/logs/YYYY-MM-DD-session-NNN.md` 留痕（做了什么、改了哪些文件、遗留问题）。
- [ ] 里程碑完成时在 `docs/reports/` 写阶段报告，并更新 [docs/plan/progress.md](docs/plan/progress.md)。
- [ ] 提交遵循 [docs/process/git-workflow.md](docs/process/git-workflow.md)（conventional commits，scope 约定）。

## 5. 写设计文档的质量标准

- 每个功能设计必须含五要素：**功能说明、实现方案、测试方法、测试类型、验收标准**（或明确链接到 testing/ 下对应章节）。
- URL 模式、API endpoint、rate limit 等事实性内容必须标注来源与核验日期；未核验的写 `⚠ 未核验`。
- 伪代码用于表达接口与算法意图，不追求可运行；接口定义处标注"设计伪代码"。
- 中文行文，技术术语/代码标识符保留英文。文件名用 kebab-case 英文。

## 6. 爬虫域的硬性红线（设计与未来实现都受约束）

1. 不设计/实现绕过付费墙、破解 CAPTCHA、伪造机构身份的功能；认证一律使用用户自有合法凭证。
2. 不集成盗版源（Sci-Hub 等）。
3. 默认遵守 robots.txt 与站点 ToS；rate limit 保守（见各 adapter 文档）；UA 表明身份。
4. 凭证、session state、cookie、下载的 PDF 一律不入 git（见 .gitignore 与 [docs/design/07-auth-session.md](docs/design/07-auth-session.md)）。
5. 下载内容仅限本地个人科研使用；任何"再分发"功能不予设计。

## 7. Subagent 使用规范

- 检索/调研类简单任务可派 subagent（如 Sonnet 档）执行；**架构决策、设计取舍、文档定稿必须由主 agent（高能力档，当前为 Fable 5）完成**。
- 派发 subagent 时必须给出：明确的输出结构、覆盖清单、"不要写文件，文本返回"或明确的落盘路径。
- Subagent 返回的事实必须经主 agent 提炼、去重、标注置信度后才可写入 design/catalog；原始返回归档到 `docs/research/`。

## 8. 常见任务的入口

| 你要做什么 | 从哪里开始 |
|---|---|
| 新增一个期刊/会议 | [docs/catalog/README.md](docs/catalog/README.md) 的 venue 登记流程 |
| 新增一个平台 adapter 设计 | [docs/design/adapters/README.md](docs/design/adapters/README.md) 模板 |
| 修改 pipeline 行为 | [docs/design/05-pipeline.md](docs/design/05-pipeline.md) + ADR |
| 修改数据模型 | [docs/design/06-data-model.md](docs/design/06-data-model.md) + ADR + 迁移说明 |
| 记录测试 | [docs/testing/](docs/testing/) 的 records 子目录 |
| 了解为什么某事如此设计 | [docs/plan/decision-log.md](docs/plan/decision-log.md) |
