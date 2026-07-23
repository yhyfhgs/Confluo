# Wiley TDM Runbook（用户参与层 / 手动）

> 手动测试运行手册（非自动化套件）：Wiley TDM token 自助获取 → 首取演练 → token 失效演练。
> 关联设计：[docs/design/adapters/wiley.md](../../docs/design/adapters/wiley.md)（§3/§6/§7）。
> 关联勘察：[docs/research/site-survey/publisher-platforms-p4-recheck.md §3](../../docs/research/site-survey/publisher-platforms-p4-recheck.md)（R0 [LIVE 2026-07-23] token 自助 + 订阅约束归档）。
> 验收关联：AC-4.1（JF/ECMA 单篇，token 到位）、AC-4.3（403 no_entitlement 降级）、AC-4.4（日配额）。
> 红线：只用用户自有合法凭证；TDM 条款要求下载物仅本地挖掘、不再分发（与本系统红线天然一致，AC-0.1）。

## 0. 前置状态（当前）

- config/env **无 Wiley token**（`crawler config show` 中 `auth.wiley.token` 为 default/未配置）。
- 离线 DoD 已 PASS：resolve/fetch 逻辑 + 双窗口限速 + 错误映射三态单测（`tests/unit/test_wiley_*.py`）+ 契约链（`tests/contract/`）。
- 在线冒烟 `tests/online/test_wiley_smoke.py` 与本 runbook **门控在 token 存在性之后**（无 token 即 skip，不阻塞验收，D-024）。

## 1. TDM token 自助获取（R0 [LIVE 2026-07-23] 归档：可自助，无邮件审批）

1. 用**你自己的** Wiley Online Library 个人账号登录 <https://onlinelibrary.wiley.com>（无账号先注册个人账号）。
2. 进入账号的 Text and Data Mining（TDM）设置页，接受 **click-through TDM license**。
3. 即得 **Client API Token（UUID 形态）**——无需人工邮件审批（R0 归档口径）。
4. **entitlement 约束（务必知悉）**：token 只证明"你是合法 TDM 客户端"；能否取回**某篇**全文仍受**机构订阅域**约束——
   无机构订阅的个人账号即使持 token，对非订阅内容仍 **403 `no_entitlement`**（R0 [LIVE]）。UK 用户另受 CDSM-2014 计算分析例外覆盖。

## 2. 配置 token（凭证红线：值绝不入 git / 日志 / 报告）

二选一（**不要**写进项目级 `./paper-crawler.toml`——敏感键护栏会拒启动）：

- **环境变量**（推荐，CI/临时会话不落盘）：`export PAPER_CRAWLER_WILEY_TDM_TOKEN=<你的 UUID>`
- **家目录 config**（仓库外）：`$PAPER_CRAWLER_HOME/config.toml` 加

  ```toml
  [auth.wiley]
  token = "<你的 UUID>"
  ```

核对：`crawler config show` 应显示 `auth.wiley.token` 生效来源为 `env` 或 `home`，**值已脱敏**（不回显明文）。

## 3. 首取演练（AC-4.1；单篇 ≤1 真实请求）

1. **选一个已知可取回的 DOI**。理想选**开放获取**的 Wiley 文章（只需 token 连通、不依赖机构订阅），
   或你确有订阅权限的 JF（`10.1111/jofi.*`）/ Econometrica（`10.3982/ECTA*`）单篇。
   > **注（D-028，2026-07-24）**：`10.3982` 前缀已归 Econometric Society（`econsoc` adapter），wiley 侧不再持该前缀路由；此处 Econometrica 例仍技术有效——因 Wiley 继续托管其**过刊段**（约 2010–迁移点，`doi.wiley.com`）——但当前新刊已迁自营 `econometricsociety.org`、经 wiley 不可取，请选一篇确认落在过刊段的 ECTA DOI（或改用 JF 例更省心）。
2. 把该 DOI 核准进两处 [PENDING token-verify] 占位（当前为同源占位 `10.1111/jofi.13123`）：
   - `src/paper_crawler/adapters/wiley/adapter.py` 的 `_HEALTHCHECK_DOI`
   - `tests/online/test_wiley_smoke.py` 的 `_SMOKE_DOI`（默认引用前者）
3. 跑在线冒烟：

   ```sh
   uv run pytest tests/online/test_wiley_smoke.py -m online -v
   ```

4. 核对输出 `SMOKE_CAPTURE` 行：`ok=True`、`is_pdf=b'%PDF-'`。
   - 若 **403 no_entitlement**：该 DOI 你无订阅权限（AC-4.3 的预期降级信号）——换一个 OA / 有权 DOI 重试。
   - 若 **401 auth_expired**：token 无效/失效——回到 §1 重取。
5. **审计实际 429 触发行为**（wiley.md §7 首取必做）：连续多篇取回观察是否触发 429 及其 `Retry-After`，
   据以校准双窗口稳态限速（当前起步保守 `rpm=5/burst=3`，观测后按 wiley.md 纪律放宽）。

## 4. token 失效演练（错误映射自证）

1. 临时把 `PAPER_CRAWLER_WILEY_TDM_TOKEN` 改为一个无效 UUID，重跑 §3.3。
2. 期望：`fetch_asset` 抛 `CrawlerError(error_class=auth_expired, status_code=401)` → runner BLOCKED(auth)。
3. 恢复真实 token。

## 5. 重录真实 fixture（token 到位后）

`tests/fixtures/wiley/` 四件套当前为合成/[DOCS]（`01_tdm_article_success.pdf.bin` + 401/403/429 三态封套）。
token 到位后用真实响应**截断脱敏**（去 token、留形态）重录，并更新 `tests/helpers/wiley_fixtures.py` 文件头出处等级为 [LIVE]。

## 6. 归档

执行结果（通过 / 403 降级 / 429 观测 / skip）按既有惯例归档到 `docs/testing/records/`。
