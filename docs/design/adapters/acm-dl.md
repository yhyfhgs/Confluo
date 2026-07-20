---
title: Adapter 设计 · ACM Digital Library
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `acm_dl`

## 1. 定位

- **family**: `open_access`（**D-013**：ACM 自 2026-01-01 全面开放获取；auth 能力保留作异常兜底开关）
- **服务 venue**：KDD、WWW/TheWebConf、WSDM、CIKM、SIGIR、RecSys、STOC、SOSP、EC(sigecom)、SIGMOD/PACMMOD
- **capabilities**: `RESOLVE | FETCH`（+受限 ENUMERATE 兜底）——**枚举主干走 DBLP**（D-005：会议=DBLP conf XML），本 adapter 主要承担全文。

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- **2026-01 起全面 OA**（官方公告 acm.org/articles/bulletins/2026/january/acm-open-access）：dl.acm.org 全部会议论文集免费全文；
- URL：整卷 `doi/proceedings/10.1145/{id}`；单篇 `doi/10.1145/{a}.{b}`；PDF `doi/pdf/10.1145/{a}.{b}`（有跳转链）；聚合页 `/conference/{acr}/proceedings`；
- 结构性变化点：KDD 2024 起一年两卷（V.1/V.2 双截止）；SIGMOD 2023 起转 PACMMOD 期刊滚动出版（`/journal/pacmmod/sigmod`）——**新旧两套入口**；WWW 历届最稳入口 archives.iw3c2.org；EC 2014 前名 Electronic Commerce（DBLP key `conf/sigecom` 统一）；
- 反爬现状 ⚠ 部分未核验：OA 新政后匿名 PDF 下载的速率容忍度未知；历史上 dl.acm.org 有 bot 检测（Cloudflare 类）——设计按"存在温和防护"假设。

## 3. 各阶段实现方案

- **discover_timeline / enumerate**：**不由本 adapter 承担**——VenueSpec 声明 `metadata_source: dblp`（卷清单+每届论文+DOI 经 `ee` 字段）；本 adapter 仅提供 proceedings 聚合页解析作对账兜底（paper_count 交叉核对）。
- **resolve_assets**：DOI → `doi/pdf/10.1145/{a}.{b}`（`url_strategy=direct`，跟随跳转）；SI 在 `doi/suppl/...` ⚠ 实现期核验路径。
- **fetch_asset**：HttpFetcher 直取；若遇 bot 挑战特征 → 该批转 BrowserFetcher 重试一次，仍挑战则 BLOCKED（不对抗，D-006/D-014）。
- **healthcheck**：GET 一篇已知 OA DOI 的 pdf HEAD（跟随跳转终点 content-type=application/pdf）。

## 4. 限速与礼貌

- 默认 **1 req/4s，并发 1，日配额 300**（OA 化不等于欢迎批量抓取；robots/速率政策 ⚠ 实现期核验后调整并注明出处）；
- 大批量历史回填分日执行（backfill 低优先级队列天然支持）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| PDF 跳转到登录/挑战页（HTML 伪装） | `integrity`（魔数校验兜底）→ 触发 challenge 判定 |
| 429/暂时封禁 | `rate_limited`（3 连 → 域冷却 1h） |
| DOI 404（DBLP ee 陈旧） | `gone`（记录并回 DBLP 侧修正清单） |
| Cloudflare 挑战 | `challenge` → BLOCKED + 冷却 |

## 6. Fixtures 与测试

- **T1 单元**：DOI→pdf URL 构造；PACMMOD/proceedings 双入口路由（SIGMOD 年代边界 2023）。
- **T3 fixture**：①proceedings 聚合页 ②单篇落地页 ③挑战页特征样本。
- **T5 canary**：KDD 2026 某已知 DOI 匿名下载成功（AC-2.6 的常态化哨兵）。
- **验收关联**：**AC-2.6**（无认证配置下 `pull kdd --year 2026` 成功）；AC-5.4（SODA 不在本 adapter——路由正确性）。

## 7. 风险与维护

- OA 新政执行细节（历史卷是否全开放、速率容忍）待实现期实测——本文档限速值保守起步；
- KDD 双卷/PACMMOD 期刊化这类**结构性改版是 ACM 系主要漂移源**：quirks 按 venue 记录入口形态，canary 覆盖新旧各一；
- 兜底 auth 开关：若某老卷意外仍付费墙，VenueSpec 可临时改 `auth.level: institutional` 走用户订阅（能力保留，默认关闭）。
