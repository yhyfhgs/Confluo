# Elsevier ScienceDirect 真实 key runbook（AC-4.1 / AC-4.3 / AC-4.4 · T7b 执行）

> **归属**：T7b 用户参与层（真实 key 到位后执行；BLOCKER-1 解除后）。**不进 CI**——本文件是
> 人工操作检查单，执行结果留痕 `docs/testing/records/`（D-019 惯例）。
> **预算**：真实 key 窗 ≤40 req（elsevier-sd.md §7 / plan §3 分项；**独立于** committed 在线
> 冒烟 ≤5 req，B-m9，勿混）。
> **红线**（AGENTS §6）：只用用户自有合法 Elsevier API key（机构订阅关联、非商业）；下载内容
> 仅本地个人科研；key 绝不落 git/日志（obslog redact 覆盖 `x-els-apikey`/`insttoken`）。
> **设计蓝本**：docs/design/adapters/elsevier-sd.md §6（AC-4.1 载体全链）+ §5（错误映射）。

## 0. 前置：凭证配置（凭证隔离，绝不入 URL/git）

- [ ] 家目录 `~/.paper-crawler/config.toml`（仓库外，不入 git）新增：
      ```toml
      [auth.elsevier]
      api_key = "<真实 Elsevier API key>"
      # insttoken = "<可选 insttoken；校外访问/机构关联时需要>"
      ```
      **或** 环境变量 `PAPER_CRAWLER_ELSEVIER_API_KEY`(+`PAPER_CRAWLER_ELSEVIER_INSTTOKEN`)。
- [ ] `crawler config show` 核对：`auth.elsevier.api_key` 生效值显示 `***`（脱敏正确），
      来源层（env/home）符合预期。**绝不**在任何输出/截图里出现明文 key。

## 1. `crawler auth login elsevier`（api_key 分支；AC-4.1 步骤 1）

> **依赖 T5 AuthManager**（`auth login` CLI 装配）——T5 落地后执行。本 adapter 侧的判据：
> APIKey 配置校验 + 配额/连通探测（quota_probe = 已知有权 JFE DOI 的 entitlement 探测）。

- [ ] `crawler auth login elsevier` → 退出码：`0` 成功（key 存在 + 探测连通 + entitlement 探测）；
      `2` key 缺失（AuthRequired 提示配置路径）；`1` 探测失败（网络/401/403）。
- [ ] 写/更新 `SessionHandle(provider_id="elsevier", backend=BEARER_TOKEN)`。
- [ ] `crawler canary --adapter elsevier_sd`：有 key → healthcheck 转 entitlement 探测（不再 SKIP）；
      核对 `[PENDING golden] observed entitled=…`——**捕获真实 entitled 真值**（见 §4 UPDATE_GOLDEN）。

## 2. `crawler grab --doi <JFE DOI>`（AC-4.1 步骤 2 · 单篇魔数校验）

- [ ] 取一篇**已订阅** JFE DOI（锚点：`10.1016/j.jfineco.2011.03.021`，或当期任一有权篇）。
- [ ] `crawler grab --doi 10.1016/j.jfineco.2011.03.021`：
      resolve（entitlement 预检 → 有权 → AssetPlan `url_strategy=api_call`）→ fetch（`X-ELS-APIKey`
      专属 client GET Article API → PDF）→ `%PDF` 魔数校验 → 落盘 `data/pdf/jfe/<year>/<ulid>.pdf`。
- [ ] **AC-4.1 判据**：`file data/pdf/jfe/.../*.pdf` 报 `PDF document`；首 4 字节 `%PDF`；bytes>0。
- [ ] 记录 resolve→fetch 的 obslog（domain=api.elsevier.com；无明文 key/insttoken 泄漏）。

## 3. AC-4.3：no_entitlement 降级（无订阅 DOI）

- [ ] 取一篇**未订阅** Elsevier DOI（或用无 JFE 订阅的 key 对 JFE DOI）。
- [ ] `crawler grab --doi <无权 DOI>`：resolve 的 entitlement 预检返 `entitled:false` →
      adapter 标 `no_entitlement`（不产平台 AssetPlan）→ **不计 failed**（auth-framework §8.5）→
      转 unpaywall OA-fallback（§8.1）。**判据**：run report `no_entitlement` 计数 +1、`failed` 不增。
      （⚠ pipeline 侧 OA-fallback/不计 failed 接线归 auth-framework §8——若 T7b 时尚未接线，记录
      现状 error_class=no_entitlement 已正确产出，pipeline 整合另评，见 T3 报告 concerns。）

## 4. AC-4.4：日配额 + 配额头审计（`X-RateLimit-*` / `X-ELS-Status`）

- [ ] **配额头审计**（committed 冒烟不可达——冻结 `HttpClient.get_bytes` 不暴露响应头）：用原生
      `curl -sD - -H "X-ELS-APIKey: $KEY" "https://api.elsevier.com/content/article/entitlement/doi/<DOI>"`
      抓 `X-RateLimit-Limit`/`X-RateLimit-Remaining`/`X-RateLimit-Reset` 真值——**核验 elsevier-sd.md §2
      "⚠ 待核验：X-RateLimit-* 真值"**，记录到 records。
- [ ] `Config.auth_daily_cap`（默认 200）对账：连续 grab 至日上限 → 熔断（RATE_LIMITED）。
- [ ] **认证态 429 演练**（谨慎，勿真耗配额）：若触发 429，核对 `X-ELS-Status: QUOTA_EXCEEDED` 真值
      形态——**比对 fixture `04_quota_429_exceeded.http`**（⚠[DOCS] 合成），UPDATE_GOLDEN 转正。
      **注意**（B-M2）：adapter 对任意 429 一律保守当日熔断，`X-ELS-Status` 仅作观测、不改处置——
      本步是**核验 fixture 真值**，非改行为分流。

## 5. key 失效演练（AC-4.1 反例 · auth_expired）

- [ ] 临时用一个错误/失效 key（或改 1 字符）→ `crawler grab --doi <DOI>` → 期望 401/403 →
      **重分类 `auth_expired`**（elsevier API 403 = key/insttoken 失效，非"有权探否"）→ 整批
      BLOCKED(auth)，提示 `crawler auth login elsevier`。
- [ ] 恢复正确 key，`crawler resume --all` 恢复。

## 6. UPDATE_GOLDEN 清单（BLOCKER-1 解除后一次性核验 · elsevier-sd.md §2 ⚠ 待核验项）

- [ ] `parse.py` entitlement 字段名/类型（`entitled` bool？`document-entitlement` 结构？）→
      核验后修正 `parse.parse_entitlement` + fixtures `01_entitlement_true.http`/`02_entitlement_false.http`。
- [ ] `adapter._HEALTHCHECK_EXPECT_ENTITLED`：`None`（PENDING）→ 真实 entitled 真值（该 key 对锚点 DOI）。
- [ ] `04_quota_429_exceeded.http`：合成 → 真实认证态 429 头/body（若演练触发）。
- [ ] `05_article_fulltext_truncated_xml.http`：核验 PDF vs XML 逐刊可得性（`elsevier_want_xml_source`
      quirk 是否可用于该刊）。
- [ ] 全部核验结果 + 每个 fixture 出处等级升级（⚠[DOCS]→[LIVE]）归档 `docs/testing/records/`。

## 执行记录（每次执行追加）

| 日期 | 执行者 | key 来源 | 结果（PASS/降级/漂移） | records 链接 |
|---|---|---|---|---|
| YYYY-MM-DD | | env/home | | docs/testing/records/... |
