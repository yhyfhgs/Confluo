---
title: 配置分层与敏感边界规范
status: implemented
owner: fable5
updated: 2026-07-23
---

# 10 · 配置分层加载 + 敏感边界规范

> 决策依据：**D-025**（config 归集，用户架构令 2026-07-23）+ D-023（两级凭证模型）+ D-014（UA 身份）。
> 归属：**T2 扩容**（"平台地基件：config 分层加载 + HttpClient status_code + canary 凭证注入"）。
> 红线（AGENTS §6.4 / AC-0.3）：敏感凭证物理隔离于仓库为**不变式**——凭证/session 永不入 git。
> 现状基座：[config.py](../../src/paper_crawler/config.py)（`Config.load` 优先级：显式 home > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`）
> + [auth-framework.md §3.4](auth-framework.md)（`[auth.*]` 槽）；本文档把配置规范归集、加显式分层与防误提交护栏。

## 1. 功能说明

回答三个问题，消除 Phase 4 多凭证槽引入后的配置分散/优先级隐晦/敏感边界无护栏：
1. **配置项住哪里**——仓库内 `config/` 规范文件夹（样例+总纲，真实值绝不入）；
2. **多来源怎样合并**——显式四层加载链 + 敏感键防误提交护栏；
3. **怎样自查生效值**——`crawler config show`（脱敏）。

## 2. 仓库内 `config/` 规范文件夹（T2 Files）

```
config/                        # 仓库内，只放规范与样例——真实值绝不入（AC-0.3 不变式）
├── README.md                  # 配置规范总纲：全部配置项分层/优先级/敏感边界（本文档的用户向落地）
├── config.example.toml        # 全键注释样例（含 [auth.*] 全部槽：elsevier/wiley/s2/openalex/openreview + identity/paths/rate/retry/openalex.daily_budget_usd + auth.* 运行时项）
└── profiles.example.toml      # AuthProvider profiles 样例（api_key/cookie_session/sso_flow/ezproxy 四 kind 各一，占位 URL/ref 名，无真实值）
```

- **样例文件纪律**：所有值为占位/样例（如 `api_key = "<your-elsevier-key>"`、`quota_probe` 为样例 DOI）；
  用户复制到 config-home 后填真实值。**样例文件本身不含任何真实凭证**——CI 断言 `config/**` 无凭证形态（AC-0.4 正则）。
- `config.example.toml` 全键覆盖 = 用户单一可信配置清单（消除"哪些键可配"的隐晦）。

## 3. 分层加载链（改造 `Config.load`；纯附加新增项目级非敏感层）

**优先级（高→低，逐键覆盖）**：
```
1. env（PAPER_CRAWLER_* / 各 [auth.*] env 覆盖）        ← 最高（CI/临时会话不落盘凭证）
2. 项目级 ./paper-crawler.toml（**仅非敏感键**）         ← 新增层（本机工作区层：路径/限速/venue 目录等；gitignored 不随仓库分发——可分发的默认配置模板走 config/config.example.toml。复审 n4 取舍明示）
3. config-home config.toml（$PAPER_CRAWLER_HOME 或 ~/.paper-crawler）  ← 家目录，仓库外，可含敏感槽
4. 内置默认（Config dataclass 字段默认值）              ← 兜底
```

- **既有优先级保持**（config.py 现状）：home 解析（显式 home > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`）不变；
  项目级 `./paper-crawler.toml` 为**新增非敏感层**，插在 env 与 config-home 之间，**纯附加不破坏既有家目录 config**。
- **项目级文件定位**：从 `cwd` 起向上查 `paper-crawler.toml`（仓库根惯例），找到即读；缺失静默跳过（可选层）。

### 3.1 敏感键防误提交护栏（拒启动）

**项目级 `./paper-crawler.toml`（可能被 git 跟踪/提交）出现敏感键形态 → `CrawlerError(CONFIG)` 拒启动**：
```
_SENSITIVE_CONFIG_KEY_RE = r"api[-_]?key|apikey|token|insttoken|passwd|password|secret|credential(s)?|cookie|session[-_]?id|authorization|private[-_]?key"
# 规范化子串/正则匹配（大小写不敏感，含 [auth.*] 子表内）；与 obslog 脱敏键单一同源（T2 落地，防两套清单漂移）。
# 不含裸 `key`（误伤 key_ref 类引用名）与 `email`（identity.email 属合法非凭证键）——复审 §4 建议采纳（2026-07-23）。
项目级 toml 解析后遍历（含嵌套表）：任一叶子键名命中 → raise CrawlerError(
    CONFIG, "项目级 ./paper-crawler.toml 含敏感键 <key>；凭证禁入项目文件（易误提交）——"
            "挪至家目录 config.toml（$PAPER_CRAWLER_HOME，仓库外）或环境变量 PAPER_CRAWLER_*")
```
- **护栏范围**：仅项目级层（第 2 层）；家目录 config.toml（第 3 层，仓库外）**允许**敏感槽——那是设计的凭证归处。
- **护栏理由**：项目级文件在仓库工作树内，敏感值极易随 `git add .` 误提交（AC-0.3 违规）；护栏在启动期响亮拦截。
- `.gitignore` 双保险：`paper-crawler.toml`（项目级文件名）**入 gitignore**——即便用户误填敏感键，也不会被跟踪（护栏 + gitignore 双层）。

## 4. `crawler config show` 命令（生效配置自查，脱敏）

```
crawler config show [--home H]
```
- 输出**全部生效配置项 + 每项来源层**（env / project / home / default），表格渲染（`_render_table` 复用）：
  ```
  key                        value              source
  -------------------------  -----------------  -------
  identity.email             y***@gmail.com     home
  auth.elsevier.api_key      ***                env
  auth.wiley.token           (unset)            -
  paths.data_dir             /Users/…/data      home
  rate.scale                 1.0                default
  ```
- **敏感值一律脱敏显示**（obslog `redact` 口径 + 敏感键名整值 `***`）——`config show` 用于确认"配了没/来自哪层"，
  **绝不回显凭证明文**；未配置项显示 `(unset)`。退出码恒 0（只读自查，非对账判据）。
- **实现**：复用 `Config.load` 的分层解析中间态（记录每键 winning 来源层），`config show` 渲染该来源映射。

## 5. 第三方凭证槽归集规范

- **未来第三方凭证（Kaggle 等）一律 `[auth.<name>]` 槽 + 单一 config-home**，不依赖各工具家目录约定
  （如 `~/.kaggle/kaggle.json`、`~/.config/*`）——R0 [LIVE] 发现 `~/.kaggle/` 有非标准 `access_token`（检查单 #16），
  正是"分散在各工具家目录"的反面教材。统一到 config-home `[auth.*]` 消除凭证发现的碎片化。
- 新凭证接入 = ①`config.py` 加 `Config.<name>_*` 字段（沿 line 100–124 样板）②`config.example.toml` 补注释槽
  ③adapter 经既有 `ApiKeyConsumer`/专属 client 注入（凭证隔离红线）——三步定式。

## 6. 敏感边界不变式（规范总纲，写入 config/README.md）

| 边界 | 规则 | 依据 |
|---|---|---|
| 凭证物理位置 | 只存 config-home（仓库外）或 env；**绝不入仓库工作树** | AC-0.3 不变式 |
| 项目级文件 | 仅非敏感键（路径/限速/venue 目录）；敏感键 → 拒启动（§3.1） | D-025 护栏 |
| 日志/报告 | 敏感值一律 obslog `redact`（cookie/token/api_key/insttoken/password/secret/email/…，§auth-framework §5） | AC-0.4 |
| 有状态凭证 | storage_state/cookie jar → AES-GCM `CredentialStore`（0600，keyring 主密钥） | D-023 ②类 |
| git 双保险 | `paper-crawler.toml`/`config.toml`（家目录副本误置）/`*.enc`/`.filekey`/`profiles.toml` 入 .gitignore | 07 §7 |

## 7. 测试与验收

- **单元**：分层加载优先级（env > project > home > default 逐键）用例表；敏感键护栏（项目级含 api_key/token/insttoken/password/secret → CONFIG 拒启动，非敏感键放行）；`config show` 脱敏（敏感值 `***`、来源层正确、`(unset)` 渲染）。
- **集成**：项目级 `./paper-crawler.toml` 非敏感键生效 + 家目录敏感槽生效 + env 覆盖优先级端到端。
- **AC-0 扫描**：`config/**` 样例文件无凭证形态（AC-0.4 正则）；`paper-crawler.toml` 在 .gitignore（AC-0.3）。
- **验收关联**：AC-0.3（凭证不入 git）、AC-0.4（日志/自查无未脱敏凭证）；归 T2 卡 DoD。

## 8. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-23 | 初稿（D-025 用户架构令）：仓库内 config/ 规范文件夹 + 四层加载链 + 敏感键防误提交护栏 + `config show` 脱敏 + 第三方凭证槽归集规范 + 敏感边界不变式；归 T2 扩容 | 用户架构令 2026-07-23 + [D-025](../plan/decision-log.md) |
