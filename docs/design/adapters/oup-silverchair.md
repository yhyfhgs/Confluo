---
title: Adapter 设计 · OUP（Silverchair 平台）
status: review
owner: fable5
updated: 2026-07-21
---

# Adapter · `oup_silverchair`

## 1. 定位

- **family**: `auth_gated`
- **服务 venue**：QJE、REStud、RFS、Review of Finance、EJ (Economic Journal)、JEEA、J. Financial Econometrics、RAPS、RCFS——**一个 adapter 覆盖 5+ 顶刊**（经济金融密度最高的平台，NFR-1 杠杆最大）
- **capabilities**: `RESOLVE | FETCH`——enumerate 走 crossref（D-005；DOI 前缀 10.1093）。
- 平台族说明：Silverchair 是托管平台（academic.oup.com 是其最大部署）；UChicago/MIT Press 结构近似但独立域，各自单列 adapter，解析器基类共享（见 §7）。

## 2. 站点勘察摘要

来源：[research/site-survey/publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20）：

- 域：`academic.oup.com`；期刊路径 `academic.oup.com/{journal_code}`（qje/restud/rfs/rof/ej…）；
- URL 模式（[LIVE] 实例确认）：期列表 `/qje/issue/140/1`；文章 `/{code}/article/{vol}/{iss}/{page}/{silverchair_id}`（如 `/qje/article/141/3/2205/8662148`；无权时 302 至 `/article-abstract/`）；**PDF `/{code}/article-pdf/{vol}/{iss}/{page}/{file_id}/{name}.pdf`**（如 `/qje/article-pdf/140/2/889/61701561/qjae044.pdf`——file_id 不可构造，须从文章页解析）；
- robots.txt（[LIVE]）：**无任何 AI-bot 专门条目**、无 Crawl-delay；仅禁后台/登录/搜索/下载/引文导出路径（`/Shibboleth.sso/` 印证 SP 部署）；无 TDMRep；
- 反爬（[LIVE]）：Cloudflare 通用质询（403 "Just a moment..."）——匿名程序化访问不可行，登录 session 态为工作前提；
- **官方 API/TDM：无公开 API**；非商业 TDM 含在机构订阅条款内（Data.Mining@oup.com，商业需单独协议；转引 Bodleian/Georgetown 指南）；
- 认证："Sign in through your institution"（SeamlessAccess/Shibboleth/OpenAthens）；部分刊个人订阅与单篇购买；
- 开放内容：abstract 免费；Oxford Open 混合 OA 文章。

## 3. 各阶段实现方案

- **resolve_assets**：DOI → `doi.org/10.1093/...` 跟随重定向到文章落地页 → **解析页内 PDF 链接**（不可构造，含 file id）→ AssetPlan(`url_strategy=direct`+cookie)。entitlement 启发式：落地页为 `article-abstract` 路由且无 PDF 链接 → `no_entitlement`。
- **fetch_asset**：HttpFetcher + cookie jar（storage_state 导出）直取 PDF；被拒（403/跳转）→ BrowserFetcher 同 context 重试一次 → 仍失败按错误分类处置。
- **healthcheck**：探针=账号页（`/my-account` 类，adapter 文档定稿时定 URL）或已知有权 DOI 的落地页含全文节点判定。
- **SI**：Silverchair 附录在文章页 "Supplementary data" 区，解析生成附属 AssetPlan。

## 4. 限速与礼貌

- **串行 1 req/6s + 日配额 200 + 工作时段窗**（design/04 §4 全局纪律）；
- resolve（页面解析）与 fetch（PDF 下载）计入同一 domain 桶——每篇实际 2 请求，配额按请求数记账；
- OUP TDM 政策已勘察（2026-07-20）：无公开 API、无明文速率数字；非商业 TDM 含在机构订阅条款内——无明文即维持全局保守纪律；实现期可选礼貌动作：向 Data.Mining@oup.com 报备用途。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| 落地页 302→signin | `auth_expired` → 整批 BLOCKED |
| article-abstract 路由（无全文） | `no_entitlement` + Unpaywall 兜底 |
| PDF 链接解析 0 命中（改版） | `parse` + canary 标红 |
| 下载物为 HTML | `integrity`(auth_leak) → healthcheck |
| 验证码/异常页 | `challenge` → BLOCKED + 冷却 |

## 6. Fixtures 与测试

- **T1 单元**：文章页 PDF 链接抽取器（全文页/abstract 页/OA 页三态）；entitlement 判定器。
- **T3 fixture**：auth 四件套（登录态全文页脱敏 / 未登录跳转 / abstract-only / 挑战页）。
- **T6 runbook**：真实机构凭证：SSO 首登→QJE 单篇→过期演练（records 留痕）。
- **验收关联**：AC-4.1（QJE DOI `10.1093/qje/...` 即需求 US-9 样例）、AC-4.2/4.3/4.5；AC-3.5（QJE 零爬取枚举依赖 crossref——本 adapter 不做枚举的对照验证）。

## 7. 风险与维护

- **Silverchair 族基类**：PDF 链接解析、entitlement 判定、探针逻辑抽象为 `silverchair_base`，oup/uchicago/mit_press 三 adapter 继承——平台升级一处修（NFR-2 摊薄）；
- OUP 改版节奏较慢但 file id 规则是黑盒：fixture 覆盖多刊样本（qje+rfs 各一）防单刊特化；
- 勘察已并入（2026-07-20）：robots 无 AI 条目、无 TDM API、URL 模式实测确认——设计假设成立，可提交 approved 评审；剩余实现期事项：探针 URL 定稿、TDM 用途邮件报备（可选礼貌动作）。
