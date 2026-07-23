# OUP (Silverchair) 真实 SSO 取回 Runbook

> **用户参与层**（D-018）：真实机构 SSO 首登含 MFA，无法自动化（D-006 R2 已接受）；
> 本 runbook 是**人工执行**的取证式手册，**不进 CI**（记录留痕 `docs/testing/records/`）。
> 关联 adapter：`src/paper_crawler/adapters/oup_silverchair/`（Phase 4 T4）。
> 设计依据：[oup-silverchair.md](../../docs/design/adapters/oup-silverchair.md) §3/§7。
> **红线（AGENTS §6 / AC-0.2 / AC-4.6）**：只用你**自有合法**机构凭证；命中 Cloudflare
> 挑战即 **BLOCKED、绝不对抗/绕过/破解**；下载物仅本地个人科研用，不再分发。

## 0. 依赖状态（执行前先确认）

T4 已落地：adapter（RESOLVE|FETCH）+ 四类判定器 + 零在线匿名冒烟 + QJE fulltext_source
收敛。**真实取回还依赖后续任务合并**：
- **T1b**：`CredentialStore`（AES-GCM + keyring）+ `crawler auth login` CLI + cookie 供给
  真实现（本 adapter 的 `set_cookie_supplier` seam 的生产端）。
- **T7/pipeline**：resolve/fetch 阶段的 session 装配（把 `SessionHandle` 传进 adapter）。

在上述合并前，下列步骤中标 `[待 T1b]` / `[待 pipeline]` 的命令尚不可用——此 runbook 先把
**目标流程与验收锚点**定死，auth 栈合并后即可照单执行。可选依赖：`uv sync --extra auth`
（凭证库）、`uv sync --extra auth-browser`（headed 首登 playwright）。

## 1. SSO 首登（headed 浏览器，含 MFA） `[待 T1b]`

```
crawler auth login oup@campus      # 或 oup@shib（Shibboleth/OpenAthens）
```
- 弹 headed 浏览器 → "Sign in through your institution"（SeamlessAccess/Shibboleth）→ 完成
  机构账号 + MFA。
- 成功后导出 storage_state cookie jar，加密写入 `CredentialStore`（**凭证/cookie 绝不入 git**，
  .gitignore 已覆盖；`SessionHandle.payload_ref` 只存条目名，不内联密文）。
- 记录：登录成功时刻、`provider_id`（oup@campus / oup@shib）、backend=`httpx_cookies`。

## 2. healthcheck（探针账号页） `[待 pipeline session]`

```
crawler canary --adapter oup_silverchair
```
- **无 session 时**（当前 T4 现状）：`healthcheck()` → `NotImplementedError` → canary **SKIP**
  （非不健康，退出码不受影响）。这是预期，不是缺陷。
- **有 session 时**（auth 栈合并后）：探针 `GET /my-account` → `ChallengeDetector.classify`：
  - OK（含账号标识 `Sign out`/`My Account`）→ **healthy**；
  - 302→signin → **EXPIRED**（unhealthy）；challenge 特征 → **CHALLENGED**（unhealthy）。
- **⚠ 探针 URL 校验（design §3.3 controller 亲读②）**：`/my-account` 是**设计假设**（R0 无
  凭证未实测）。首登后**亲验该路径**返回登录态账号页；若真实路径不同，经 profile 的
  `probe_url` 覆盖，并回填 design §3.3 / `adapter._PROBE_URL`。

## 3. 单篇 QJE 取回（US-9 样例 DOI） `[待 pipeline]`

```
crawler pull --venue qje --limit 1     # 元数据枚举走 crossref；全文取回走 oup_silverchair
```
- 取一篇 `10.1093/qje/…` DOI：resolve（doi.org→落地页→解析 `citation_pdf_url`）→ fetch
  （article-pdf 直取）→ 落盘。
- **验收**：产物首字节 `%PDF` 魔数通过；`file_id` 确实来自页面解析（非构造）。若下载物为
  HTML（`%PDF` 校验失败）→ `integrity(auth_leak)` → 触发 healthcheck 判拦截页伪装（design §3.2）。
- 关联 **AC-4.1**（QJE DOI = US-9 样例）；**AC-3.5**（元数据枚举依赖 crossref、零爬取——与全文
  取回两条路职责分离对照验证）。

## 4. 过期演练（删 cookie → 重登） `[待 T1b]`

```
crawler auth invalidate oup@campus     # 取证式彻底删除 payload（AC-4.5）
crawler canary --adapter oup_silverchair   # 期望 EXPIRED / SKIP
crawler auth login oup@campus          # 重登恢复
```
- 验证 `invalidate` 后 `CredentialStore` 内该条目 payload **确已删除**（AC-4.5 取证式）。
- 删 cookie 后再取回单篇 → 期望落 `auth_expired`（302→signin → `AuthRequired` → 整批
  BLOCKED(auth)，提示 `crawler auth login oup@campus`），**非**静默失败。

## 5. 登出取证 `[待 T1b]`

```
crawler auth logout oup@campus
```
- 确认后续 resolve/fetch 无 session → `AuthRequired`；`CredentialStore` 无残留 payload。

## 6. Fixture 真样本回填（诚实现实兑现）

四件套中 ③`03_no_entitlement_abstract` / ④`04_fulltext_logged_in` 当前为 **⚠[SYNTHETIC]
合成占位**。首登后**采真实脱敏样本替换**：
- 抓一篇**有权限**全文页 → 脱敏后替换 ④（保留 `citation_pdf_url` meta + article-pdf 锚点 +
  账号标识结构）。
- 抓一篇**无权限** article-abstract 页 → 脱敏后替换 ③。
- **脱敏清单（入库前逐项核）**：删除全部 cookie/token/storage_state、个人姓名/机构标识/邮箱、
  session 参数（returnUrl 等）、任何可回指个人的值。文件头出处等级由 `⚠[SYNTHETIC]` 升为
  `[LIVE-DESENSITIZED]`，注明采集日期。
- 替换后重跑 `tests/unit/test_oup_silverchair_adapter.py::test_four_fixture_detector_replay`
  确认判定不回归；如真实登录态 DOM 标记超出 `_ACCOUNT_IDENTITY_SIGNATURES` 三串覆盖，按
  challenge.py"只增不改语义"补充特征并注明依据。

## 7. 验收关联汇总

| 步骤 | AC | 说明 |
|---|---|---|
| §3 单篇取回 | AC-4.1 | QJE DOI `10.1093/qje/…`（US-9 样例） |
| §2/§4 判定 | AC-4.2/4.3 | mock IdP 层（auth-framework §9）+ session 生命周期 |
| §2 challenge | AC-4.6 | 挑战判定 = BLOCKED、不对抗 |
| §4 删除 | AC-4.5 | 取证式彻底删除 payload |
| §3 对照 | AC-3.5 | QJE 元数据枚举依赖 crossref（与全文取回职责分离） |
