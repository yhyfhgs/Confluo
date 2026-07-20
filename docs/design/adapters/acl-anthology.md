---
title: Adapter 设计 · ACL Anthology
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `acl_anthology`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：ACL、EMNLP、NAACL、COLING、EACL（及 Findings/workshop 可按需扩展）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`
- 获取策略阶梯的模范生：**GitHub 官方数据仓库 bulk 优先，网站仅兜底**（design/03 §2 第 1 级）。

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- **bulk：`github.com/acl-org/acl-anthology`** 仓库含全量结构化元数据（XML/YAML，MIT/CC 授权），clone/pull 即得全史；
- 网站 `aclanthology.org`：venue 页 `/venues/acl/`、事件页 `/events/acl-2024/`；
- Anthology ID 两代：新式 `2024.acl-long.123`（2020+）、旧式 `P19-1001`（前缀 P/N/D/E/C/W…）——天然稳定主键（identifier scheme `anthology`）；
- PDF 直链：`https://aclanthology.org/{id}.pdf`；
- 无认证无防护；COLING 主办方 ICCL 非 ACL 学会但同库收录；NAACL/EACL 非每年举办（audit 需区分停办年，AC-8.3 同款语义）。

## 3. 各阶段实现方案

- **discover_timeline**：从本地 bulk 仓库（定期 `git pull`）解析 venue→年度事件清单 → Issue(label=year, 附 volume 划分 long/short/findings)；停办年标注（NAACL 语义）。
- **enumerate_issue**：解析 bulk XML 中该事件的论文条目（title/authors/pages/abstract 若有）；`paper_count_claimed`=条目数。**全程无在线请求**（AC-2.5 的日志证据要求：回填路径无网站抓取记录）。
- **resolve_assets**：`{id}.pdf` 直链构造；attachment（software/dataset/note）按 XML 声明生成附属 AssetPlan。
- **fetch_asset**：HttpFetcher 直取 PDF（此为唯一在线动作）。
- **healthcheck**：GET 站点首页 200 + 本地 bulk 仓库 git pull 成功。

## 4. 限速与礼貌

- PDF 下载 **1 req/2s，并发 1**（NFR-4 默认；元数据零在线请求已是最大礼貌）；
- GitHub clone/pull 遵守 GitHub 常规（无需特殊限速）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| bulk 仓库 schema 变更（解析失败） | `parse`（锁定上一 commit 继续用 + 标红） |
| PDF 404（少数早期条目无 PDF） | `gone`（XML 中本就可判，预先跳过） |
| git pull 网络失败 | `transient` |

## 6. Fixtures 与测试

- **T1 单元**：两代 Anthology ID 解析/构造；volume 划分（long/short/findings/demo）映射。
- **T3 fixture**：bulk XML 片段（一个事件）+ golden 解析输出；含无 PDF 条目样本。
- **T5 canary**：EMNLP 2023 主会 long 论文数已知答案。
- **验收关联**：AC-2.5（回填走 bulk 路径的日志证据）。

## 7. 风险与维护

- 风险最低档：官方仓库即权威源，schema 由社区维护且变更有 PR 历史可追；
- 仓库体积增长：浅克隆（`--depth 1`）+ 定期 pull 策略写入实现配置。
