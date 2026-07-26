# Browser-Fetch Runbook（用户参与层 / 手动；**不进 CI**）

> 手动测试运行手册（非自动化套件）：browser-fetch 横切件的真实取回演练（design/11 §8 **T-11**）。
> 关联设计：[docs/design/11-browser-fetch.md](../../docs/design/11-browser-fetch.md)（§2 红线 / §7 预算 / §10 AC-BF）。
> 验收关联：**AC-BF.3**（单篇真实取回，对标 AC-4.1）——本环境结构性只能是 runbook（§11 风险①：
> 本机对 CF 前置域 TLS 层阻断，[LIVE 2026-07-24] 实测），离线对应物 = `tests/unit/test_browser_fetch.py` T-1 OK 路径。
> 执行留痕：结果**无论成败如实回填** `docs/testing/records/YYYY-MM-DD-browser-fetch.md`（沿 wiley_runbook 体例）。

## 0. 红线（执行前逐条确认，AC-0.2/AGENTS §6）

1. **只用你自己的合法凭证**：本 runbook 全程不共享账号、不入 git、不落明文临时文件。
2. **遇挑战即停**：命中风控/CAPTCHA 时系统只分类为 CHALLENGE 并 BLOCKED + 域冷却 24h。
   **不要**试图让系统"过验证"——恢复的唯一合法路径是：**你本人在自己的浏览器里**正常访问该站点、
   按站点要求完成验证，随后 `crawler resume --all`。
3. **不批量**：本通道只服务用户显式发起的单篇（`grab --doi ... --browser`）；不要写循环脚本。
4. **robots/ToS**：ssrn 模式 B 的执行**前置**是重取 `papers.ssrn.com/robots.txt` 全文核对 `Disallow` 面
   （design/11 §11 开放问题①，⚠ 至今未核验）——未核验前不要对 SSRN 执行本 runbook。

## 1. 前置状态（当前，2026-07-27）

- 横切件核心（`browserfetch.py` + stage 分支 + config 四槽 + `grab --browser`）已落地（Phase 7 T6）。
- **三消费方 adapter 已接入**（Phase 7 T11 落地）：ssrn 模式 B（`resolve_assets` 产 landing
  引用的 `RENDER_PAGE` 计划）、aea pubs 全文（订阅刊/OA 刊两分支均产 `RENDER_PAGE` 计划）、
  wiley 页面兜底（TDM 无 token 时产 `RENDER_PAGE` 计划，与 TDM 互斥不双发）——本 runbook
  现可覆盖三消费方真实站点（仍受 §5 清账表第 2 行"第二跳导航不过判定器"等已知边界约束）。
- 真实浏览器依赖未装（可选 extra）：`pip install paper-crawler[auth-browser] && playwright install chromium`。
- 在线预算：本演练计入 Phase 7 §3 `T19-bf` 行（三消费方各至多 3 请求，合计 ≤10）——**消费前先查
  `state/budget.json` 账本，消费后即记**。

## 2. 打开通道（三级门，design/11 §7.1 L1）

1. config-home `config.toml`（**不要**写进项目级 `./paper-crawler.toml`）：

   ```toml
   [browserfetch]
   enabled = true
   # daily_cap = 50 / rate_rpm = 10 / jitter_s = [2, 5] 三项建议保持默认（更严可自行收紧）
   ```

2. 核对：`crawler config show` 中 `browserfetch.enabled` 生效来源为 `home`/`env`，值为 `True`。
3. 每次调用仍须显式 `--browser`——三者全开才走本通道；只给 `--browser` 而 config 未开 → 退出码 2（响亮拒绝）。

## 3. 首取演练（AC-BF.3；单篇 ≤1 篇，≤2 次真实请求）

1. 若目标站点需登录：先用既有通道人工首登，`crawler auth login <provider>`（headed，人在回路；
   本通道**只消费** `storage_state`，绝不代你登录）。
2. 取一篇：

   ```sh
   crawler grab --doi <目标 DOI> --venue <venue> --browser
   ```

3. **判定与回填**（逐项如实记）：
   - 退出码：0=资产落盘 / 1=业务失败（含 BLOCKED）/ 2=用法·配置错；
   - `data/pdf/<venue>/<year>/<paper>.pdf` 是否落盘，`%PDF` 魔数 + 大小（<10KB 高度可疑=拦截页）；
   - `crawler verify`：DB↔文件 sha256 对账一致；
   - obslog（`logs/crawler-YYYYMMDD.jsonl`）筛 `"channel": "browser"`：`verdict` / `quota_used` /
     `quota_cap` / `rate_wait_ms` / `elapsed_ms` 各一条；URL 已脱敏；
   - `fetch_log`：**恰好一行**（成败均计，§7.2 口径）。

## 4. 挑战路径演练（AC-BF.1 的真实侧；**预期结果就是"停手"**）

对已知住 Cloudflare 的域执行一次（例如 `pubs.aeaweb.org`）：预期 `Challenged` → 任务 BLOCKED →
`<config-home>/state/cooldown/<域>.json` 写入（24h）→ 再次执行同域被 BLOCKED 而**不发请求**。

- **成功判据不是"取到了"**，而是：① 零重试（obslog 只有一条 browser 事件）；② 冷却文件已写；
  ③ 报告 blocked 明细里有可读的人工动作提示。
- 冷却期内若要重试：`crawler cooldown clear <域>`（T3 卡落地后）或手删该 JSON 文件——但**请先确认
  站点判罚确已结束**，否则继续敲门只会加重判罚。

## 5. 清账节（T6 审查登记的已知边界；执行本 runbook 前必读）

| # | 边界 | 对本 runbook 的影响 | 闭合归属 |
|---|---|---|---|
| 1 | ~~open_access 消费方无凭证注入面~~ **已闭合**（T11 controller 前置裁决）：`storage_state` 只来自 runner 的 auth 健康门，该门对 `family != "auth_gated"` 早返回 ⇒ ssrn/aea（`open_access` family）恒以干净上下文启动——**这是设计，非缺陷**：browser-fetch 对二者的语义=公开内容的浏览器渲染取回（非"需要登录"）；Cloudflare 拦截由既有 S-c 头级判定 + 域级冷却处置 | ssrn 模式 B、aea gold OA（jel/jep）可正常演练（干净上下文即预期姿态）；aea 订阅刊（aer/aeri/aej_\*）遇 CF/付费墙页按 challenge/no_entitlement 既有链处置——非阻塞性缺口，如实记录即可 | **已闭合**——见 design/11 controller 裁决 + `browserfetch.py` 模块 docstring 清账 #1 + `pipeline/stages.py::_browser_storage_state` docstring |
| 2 | 下载触发的第二次导航不再过判定器（与设计伪码同形） | 若站点在第二跳才发质询，本次归 **`TRANSIENT`**（下载未发生）而非 challenge——**不是绕过**，但**会进重试表**（4 次 / 2·8·30s），即对刚发过质询的域再敲三次。请在记录里如实区分，并留意 obslog 里同域连续 TRANSIENT | T11 按站点实况复核（是否把第二跳也喂判定器）——**本卡评估结论**：建议改判 CHALLENGE 而非留 TRANSIENT，提案见 T11 卡报告，本卡不改行为 |
| 3 | AC-BF.4② 的"相邻请求间隔"在 obslog 里只有 `rate_wait_ms` 汇总，无请求时刻序列 | 限速合规需靠 `RateLimiter` 桶配置 + 人工计时佐证，日志不能单独作为时序证据 | T18（AC-BF 转正时定审计载体） |
| 4 | 直调 `fetch_one` 时冷却读侧只认**域**键，不读旧 `<adapter_id>.json` 兼容键 | 经 `crawler grab` 走时由 runner 的 pre-stage 冷却门先拦，不受影响 | T3（抽 `pipeline/cooldown.py` 后改委派） |

## 6. 开放问题回填（design/11 §11，本 runbook 是其唯一取证途径）

| # | 待测 | 回填位置 |
|---|---|---|
| ② | `pubs.aeaweb.org` / `onlinelibrary.wiley.com` 浏览器上下文实际可达性（换非阻断网络） | design/11 §11 表 |
| ③ | UA 形态：当前实现发 `X-Paper-Crawler: PaperCrawler/<ver> (…)` 附加头 + **不改写 UA**；站点是否接受 | 同上 |
| ⑤ | ssrn `Delivery.cfm` token 有效期与"同上下文"的确切边界（同 context 跨页？同 page？） | 同上 |
| ⑥ | 每篇冷启开销与质询频次影响（案 A 代价的量化；若显著 → §3.6 演进缝） | 同上 |
