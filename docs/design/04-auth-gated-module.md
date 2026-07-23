---
title: Auth-Gated 获取模块
status: implemented
owner: fable5
updated: 2026-07-23
---

# 04 · Auth-Gated 获取模块

> 覆盖"需登录 session / 校园 SSO 等认证状态"的闭源出版社：Elsevier ScienceDirect、Wiley、OUP(Silverchair)、UChicago Press、INFORMS、IEEE Xplore、SIAM、AEA、Cambridge、Springer、MIT Press、JSTOR、PM Research。
> 注（D-013）：ACM DL 自 2026-01 起全面开放获取，已移入 open_access 族；本模块保留其登录能力仅作异常兜底。
> 决策依据：D-003、D-006。session 生命周期细节在 [07-auth-session.md](07-auth-session.md)；逐平台细节在 [adapters/](adapters/)。

## 1. 功能说明

在**用户自有合法访问权限**内，自动化完成闭源内容的 resolve/fetch：
- 输入：已由聚合源（Crossref 等）enumerate 出的 DOI 清单（D-005——本模块很少自己做 discover/enumerate）；
- 输出：PDF/SI 资产落盘 + entitlement 信息回写；
- 全程受 AuthProvider 管理的 session 保护，session 异常时**停止而非对抗**。

## 2. 三种访问形态（机构访问的现实拓扑）

| 形态 | 机制 | 对系统的含义 |
|---|---|---|
| A. 校园网 IP 直连 | 出版社按来源 IP 放行 | 最简单：无需登录，fetcher 直接工作；需检测"是否在校园网"（探测已知受限 URL） |
| B. EZProxy | URL 重写为 `https://www-sciencedirect-com.<proxy.univ.edu>/...`，一次登录得 proxy cookie | `EZProxyProvider` 做 URL 重写 + cookie 维持；重写规则每机构一份配置 |
| C. Shibboleth / OpenAthens SSO | 出版社页 → 选机构 → IdP 登录（常含 MFA）→ SAML 回跳种 cookie | 首次登录人工完成（有头浏览器），storage_state 持久化复用；无法全自动（MFA），设计即接受（R2） |

同一用户可配置多个 `AuthProfile`（如"校内直连"+"校外 EZProxy"），VenueSpec 的 `provider_hint` 只指平台，实际用哪个 profile 由运行时配置（`config.toml` 的 `active_profile`）决定。

## 3. 获取策略阶梯（auth_gated 版）

1. **官方 API + 机构 token**（最优先）：
   - Elsevier：ScienceDirect Article Retrieval API（APIKey + 机构 token，PDF/XML 全文）——能用 API 绝不爬页面；
   - Wiley：TDM API（Bearer token 下载 PDF）；
   - 其余出版社多无个人可用全文 API → 走 2/3。
2. **HTTP + session cookie**：Silverchair/UChicago/INFORMS 等站的 PDF 直链在 session 有效时可 httpx 直取（携带 storage_state 导出的 cookie jar）；
3. **浏览器上下文内下载**：PDF 链接需 JS 生成、或站点校验 referer/一次性 token（IEEE Xplore 的 `stamp.jsp`、ACM `doi/pdf` 跳转）→ Playwright context 内点击/`expect_download` 落盘。

adapter 文档必须声明其平台走哪一档及理由（勘察证据）。

## 4. 下载流水线细节

```
DOI → [entitlement 预检] → AssetPlan → [session 健康门] → 下载 → [文件验证] → 落盘+回写
```

- **entitlement 预检**：能查则查（Elsevier API 有 entitlement 端点；页面型平台用"PDF 链接是否含 login 跳转"启发式）。无权限 → Asset 标 `no_entitlement`，不重试、不计失败率，转 Unpaywall 找 OA 副本（与 open_access 模块共享该 fallback）。
- **session 健康门**：批量下载每 N=20 篇或每 15 分钟强制 healthcheck 一次；失败即暂停整批 → BLOCKED（防止半批 401 刷爆日志与触发风控）。
- **文件验证**：magic bytes 必须 `%PDF`；大小 < 10KB 视为疑似拦截页（常见：HTML 的"请登录"页存成 .pdf）→ 判 FAILED(kind=auth_leak) 并触发 healthcheck。
- **限速纪律**：闭源平台默认**串行 + 1 req/6s + 单日单平台上限（默认 200 篇，可配）**。这比技术极限慢得多——机构批量下载异常会触发出版社对**整个学校**的封禁，宁慢勿封。各 adapter 可依据出版社明文的 TDM 政策放宽并注明出处。

## 5. 风控与合规行为规范

- 检测到 CAPTCHA / 异常验证页 / "unusual activity" 提示 → 立即 BLOCKED + 停止该平台全部队列 + 冷却（默认 24h）+ 在报告中显著提示；
- 不做 UA 伪装成浏览器的 httpx 裸抓闭源 PDF（要么真浏览器上下文要么官方 API）；
- 不并行多 session 同平台；不深夜高频（调度器对 auth_gated 平台默认工作时段 8:00–23:00 本地时间，可配）；
- 每次批量任务留存完整 FetchLog（时间、URL、字节数）备查——这是"个人合理使用"的自证材料。

## 6. 各平台一页纸速览

（勘察细节与最终限速值在各 adapter 文档定稿）

| 平台 | 服务 venue（例） | 推荐档 | 已知要点 |
|---|---|---|---|
| elsevier_sd | JFE、JME、JET、JBF、EJOR | API | 开发者门户申请 key；机构 token 配合；XML 全文可选 |
| wiley | JF、ECMA、RAND | API(TDM)→cookie | TDM token 申请；ECMA 注意学会关系 |
| oup_silverchair | QJE、RFS、REStud、RF、EJ | cookie | Silverchair 平台族共性强，一 adapter 多刊 |
| uchicago | JPE、JOLE | cookie | 同为 Silverchair 系但域独立，单列 |
| informs | MS、OR、MSOM、IJOC | cookie | Atypon 平台；PDF 直链规整 |
| ieee_xplore | ICASSP、ICRA、IROS、ICDM、FOCS、IEEE 刊 | browser | `stamp.jsp` 出 PDF；conhome ID 逐年随机需定位；有官方元数据 API（非全文） |
| siam | SODA | cookie | epubs.siam.org；不受 ACM OA 新政覆盖 |
| aea | AER、AEJ 系 | cookie | 会员登录；JEP/部分内容免费 |
| cambridge | JFQA、ET | cookie | Cambridge Core 结构规整 |
| springer | MathProg、F&S | cookie | link.springer.com PDF 直链 |
| mit_press | REStat | cookie | Silverchair 系 |
| jstor | 历史过刊 | browser | 逐页限制严格，仅兜底，低配额 |
| pm_research | JPM | browser | 小平台，谨慎限速 |

## 7. 失败模式与处理

| 模式 | 判定 | 处理 |
|---|---|---|
| session 过期 | healthcheck 失败 / 302→login | 整批暂停 → 尝试静默续期（见 design/07）→ 失败则 BLOCKED 提示 `crawler auth login <provider>` |
| 无 entitlement | 预检失败 / 403 且 session 健康 | `no_entitlement`，转 OA fallback，不重试 |
| 风控挑战 | CAPTCHA/异常页特征库命中 | BLOCKED + 平台冷却 24h + 报告 |
| 拦截页伪装 PDF | 文件验证失败 | FAILED(auth_leak) + healthcheck |
| 平台改版 | 解析 0 命中 | FAILED(parse) + canary 标红 |

## 8. 测试与验收

- **离线**：各平台"已登录页/未登录跳转页/无权限页/风控页"四类 HTML fixture 的判定器回归；文件验证器单测（真 PDF 头/HTML 伪装/截断文件）。
- **半自动**（需真实凭证，手动触发）：`tests/manual/` 脚本清单——login→healthcheck→下载 1 篇→过期模拟（删 cookie）→重登，每平台一份 runbook，结果记入 testing/records。
- **验收**（AC-4.x 摘录）：
  - AC-4.1 首次 `auth login elsevier` 后，指定 1 篇 JFE DOI 成功获得合法 PDF；
  - AC-4.2 人为使 session 失效后批量任务在 ≤20 篇内检出并 BLOCKED，无连续 401 轰炸（日志证据）；
  - AC-4.3 对无订阅的期刊 DOI，系统正确标记 `no_entitlement` 并给出 Unpaywall 副本（若存在）；
  - AC-4.4 任一平台单日下载不超过配置上限（对账 FetchLog）。
