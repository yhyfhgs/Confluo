---
title: Adapter 设计 · Elsevier ScienceDirect
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `elsevier_sd`

## 1. 定位

- **family**: `auth_gated`（推荐档：**官方 API**——auth_gated 三档阶梯的第 1 档，design/04 §3）
- **服务 venue**：JFE、JAcctEcon、JBF、JFI、JFM、JCorpFin、JEmpFin（金融）；JME、JET、JinTEco、JPubEco、JDevEco、JoE 计量（经济）；EJOR（OR）；AIJ、Pattern Recognition、Neural Networks、Neurocomputing（AI）——Elsevier 一个 adapter 覆盖 15+ 刊（NFR-1 杠杆）
- **capabilities**: `RESOLVE | FETCH`——enumerate 一律 crossref（D-005）。

## 2. 站点勘察摘要

来源：[research/site-survey/publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20）：

- **反爬（[LIVE]）**：Cloudflare 深度集成（403 + `cf-mitigated: challenge` 定制验证页）；robots.txt 默认全禁（`*`→`Disallow: /`），AI 治理三类——训练类全禁 30+ UA、AI 检索类多数禁（**含 claude-code**）、仅 OAI-SearchBot/Claude-SearchBot 放行；全站 TDMRep 头（`tdm-reservation: 1`，非欧盟科研例外需 obtainConsent）——**页面爬取路线在合规与工程上双重不可行 → API 是唯一正道**；
- **官方 API（设计基座，配额官方数字 [LIVE]）**：dev.elsevier.com——`Article Retrieval API`（`GET api.elsevier.com/content/article/doi/{doi}` 或 `/pii/{pii}`，全文 XML；覆盖 Subscribed+OA+Complimentary）：**每周 50,000 次、10 req/s，Text Mining 专用 key 不限量**；`ScienceDirect Search API v2`：每周 20,000、2 req/s；配额 7 天重置，`X-RateLimit-*` 头，超限 429 + `X-ELS-Status: QUOTA_EXCEEDED`。申请条件：机构订阅关联研究者免费（非商业）+ insttoken/校园 IP 激活；
- PII 概念：ScienceDirect 内部文章 id（`S0304405X…`）；RSS：`rss.sciencedirect.com/publication/science/{issn数字}`（EJOR [LIVE] 已证实）；
- 认证形态：API key（首选）/ 机构 SSO 页面态（兜底）。

## 3. 各阶段实现方案

- **resolve_assets**：DOI → ①`entitlement` API 预检（design/04 §4 的"能查则查"最佳案例）→ ②有权：AssetPlan(`url_strategy=api_call`, target=Article Retrieval, format=pdf 优先/XML 备选)；无权：`no_entitlement` + Unpaywall 兜底。SI（附录）：Article API 的 attachment 清单 ⚠ 字段名实现期核验。
- **fetch_asset**：APIKeyProvider 注入 `X-ELS-APIKey`（+`X-ELS-Insttoken` 若配置）→ httpx GET → PDF/XML 落盘校验。XML（全文标记版）作为 `asset kind=source` 可选同存（extract 阶段免 OCR 之利）。
- **healthcheck**：API quota/entitlement 探测端点连通 + 已知 DOI entitlement=true 比对。
- **页面兜底路径（默认关闭）**：仅当 API 对某刊不可用时，BrowserFetcher + 机构 SSO session 走文章页——须人工开启开关并记录理由（robots 敏感站，D-014 姿态：API 是出版社明示的合规通道，页面自动化仅限自有权限内最小量兜底）。

## 4. 限速与礼貌

- API：**按官方配额执行**（[LIVE]：Article API 10 req/s / 50k 每周；本系统自限 2 req/s + 读 `X-RateLimit-*` 头动态退避——留余量给交互式使用）；
- 页面兜底：1 req/6s 串行 + 日配额 50（比通用闭源档更紧——该站 robots 姿态严格）；
- 身份：API key 本身即身份声明；UA 照常（D-014）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| API 401/403（key 失效/insttoken 错） | `auth_expired` → BLOCKED 提示重配 key |
| entitlement=false | `no_entitlement`（不重试；OA 兜底） |
| API 429/quota exceeded | `rate_limited`（读 X-RateLimit-Reset；当日熔断） |
| API 404（DOI 未收录/太新） | `gone`→延迟重试队列（新文收录延迟属常态，24h 后一次） |
| XML/PDF 内容为空壳 | `integrity` |

## 6. Fixtures 与测试

- **T1 单元**：DOI/PII 规范化；entitlement 响应判定；配额头解析。
- **T3 fixture**：①Article API 全文响应（截断样本，脱敏 key）②entitlement true/false 两样本 ③429 响应。
- **T6 runbook**：真实 key：entitlement 预检→取 1 篇 JFE→配额头审计（records 留痕）。
- **验收关联**：**AC-4.1**（JFE 单篇即本 adapter 场景）、AC-4.3（no_entitlement 降级）、AC-4.4。

## 7. 风险与维护

- API key 申请与机构关联是 Phase 4 前置外部依赖（计划依赖项；申请周期 1–2 周预留）；
- Elsevier API 条款演变（TDM 政策收紧趋势）：每次大版本前复读条款；配额变化经 healthcheck 探测自动发现；
- 本 adapter 是"API 优先原则"的样板——API 现状已勘察确认（2026-07-20：配额/申请条件/端点齐备），设计假设成立；剩余待办仅为实现期 key 申请与 PDF 格式实测（Article API 的 PDF vs XML 可得性按刊差异）。
