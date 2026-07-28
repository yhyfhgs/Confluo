# config/ — 配置规范总纲

> 本目录**只放规范与样例**——真实凭证/配置值**绝不入**（AC-0.3 不变式；CI 断言 `config/**`
> 无凭证形态）。完整设计见 [docs/design/10-config-layout.md](../docs/design/10-config-layout.md)（D-025）。

## 文件

| 文件 | 用途 |
|---|---|
| `config.example.toml` | config-home `config.toml` 全键注释模板（identity/paths/rate/retry/openalex + `[auth.*]` 全部凭证槽）。复制到 config-home 后填真实值。 |
| `profiles.example.toml` | AuthProvider profiles 样例（api_key / cookie_session / sso_flow / ezproxy 四 kind 各一，占位 URL/ref，无密钥明文）。复制到 `<config-home>/auth/profiles.toml`。 |

## 此前"查不到就当不存在"的两个键（R2c 补齐登记）

两个键此前完全未登记于 `config/`/`docs/design/10-config-layout.md` 任何一处，但性质不同——
一个**已收编**进 `_FIELD_SPECS`（`config show` 看得见），另一个**是真游离**（`config show`
恒看不见，只有专用脚本读）。分列如下，避免混为一谈：

**① 已收编（env 绑定进 `_FIELD_SPECS`，`crawler config show` 可见）**

| 键 | 收编方式 | 说明 |
|---|---|---|
| env `PAPER_CRAWLER_CONTACT_EMAIL` | `[identity].email`（`Config.identity_email`）的 `_FieldSpec` 已绑定同名 env（R2c） | `config show` 里以 `identity.email` 一行呈现（来源列 `env`，值部分脱敏）——**同时**，全部真实 adapter 未经 CLI 注入（`set_email`/`bind_http_client`）时的私有兜底也直读这同一个 env 名（如 arxiv/unpaywall/oup_silverchair 等）。二者共用同一个 env 名，配置本 env 即等价配 `[identity].email`，不必两处各配一份；此前的缺口只是"该 env 未接入 `_FIELD_SPECS`"，并非"该 env 本身游离于配置系统"。 |

**② 真游离（不进 `Config`/`_FIELD_SPECS`，`crawler config show` 恒不显示）**

| 键 | 消费方 | 说明 |
|---|---|---|
| `[auth.openreview]` 的 `username`/`password` | `scripts/refresh_openreview_token.py`（自动续期 `token` 的运维脚本，直读同一份 config.toml，见 `config.example.toml` 该节注释） | **不进** `Config`/`_FIELD_SPECS`，`crawler config show` 恒不显示、脚本自身也从不打印其值。真正被主程序消费、决定 OpenReview 鉴权是否可用的是同表的 `token`（`_FIELD_SPECS` 键，`config show` 可见且脱敏）——`username`/`password` 只是 `token` 的续期原料，不是主程序的输入。 |

## 全配置地图（本机实况；D-032 归集后）

| 位置 | 内容 | git |
|---|---|---|
| `<repo>/.paper-crawler/` | **真实 config-home**：`config.toml`（凭证+本机配置，0600）、`catalog.sqlite`、`data/`、`logs/`、`reports/` | 整目录忽略（`.gitignore` 锚定 `/.paper-crawler/`，check-ignore 守卫测试断言） |
| `<repo>/config/` | 规范+样例（本目录，无真实值；CI 断言无凭证形态） | 追踪 |
| `<repo>/venues/`、`<repo>/subscriptions/` | 业务声明配置（VenueSpec YAML / 订阅 preset） | 追踪 |
| `<repo>/paper-crawler.toml` | 可选项目级非敏感层（缺省未创建；含敏感键则拒启动） | 忽略 |
| `~/.zshenv` | `export PAPER_CRAWLER_HOME="$HOME/Projects/Paper Crawler/.paper-crawler"`（env 主指向，覆盖交互/非交互 zsh） | 仓库外 |
| `~/Library/LaunchAgents/com.papercrawler.openreview-token.plist` | launchd 安装产物（源=`scripts/refresh_openreview_token.py --install-launchd`；`--home` 显式携带，不依赖 shell env） | 仓库外（launchd 硬约束位置） |
| `~/.kaggle/access_token` | 外部 kaggle CLI 自有凭证——**登记不搬**（D-032 §5；Kaggle 回填排期时按 D-025 §5 收值入 `[auth.kaggle]` 槽） | 仓库外 |

- **操作红线（D-032）**：禁止裸 `git clean -fdx`——必须带 `-e .paper-crawler`（`clean -x` 无视 ignore 规则，会连凭证与数据库一并删除）。
- **env 缺失语义**：未设 `PAPER_CRAWLER_HOME` 的环境（裸 `sh -c`、他机 clone 等）回落 `~/.paper-crawler`（空目录）——用 `crawler config show` 首行（home + source）自查实际指向。

## 配置住哪里 · 分层加载优先级（高→低，逐键覆盖）

```
1. env（PAPER_CRAWLER_* / [auth.*] env 覆盖）        ← 最高（CI/临时会话不落盘凭证）
2. 项目级 ./paper-crawler.toml（仅非敏感键）          ← 本机工作区层（路径/限速/venue 目录；.gitignore）
3. config-home config.toml（$PAPER_CRAWLER_HOME 或 ~/.paper-crawler）  ← git 外（本机=仓库根 .paper-crawler/，D-032），可含敏感槽
4. 内置默认（Config dataclass 字段默认值）            ← 兜底
```

- config-home 解析：显式 `--home` > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`。
- 项目级文件：自 `cwd` 起向上查 `paper-crawler.toml`，首个命中即读；缺失静默跳过。
- **自查生效值 + 来源层**：`crawler config show`（敏感值脱敏；未配置显示 `(unset)`）。

## 敏感边界不变式（写入即冻结）

| 边界 | 规则 | 依据 |
|---|---|---|
| 凭证物理位置 | 只存 config-home（git 追踪范围外；D-032 起本机=仓库根 `.paper-crawler/`，整目录强制 ignore）或 env；**绝不入 git 追踪范围** | AC-0.3 + D-032 |
| 项目级文件 | 仅非敏感键（路径/限速/venue 目录）；敏感键形态 → 启动护栏 `CrawlerError(CONFIG)` 拒启动 | D-025 护栏 |
| 日志/报告 | 敏感值一律 obslog `redact`（cookie/token/api_key/insttoken/password/secret/email/…） | AC-0.4 |
| 有状态凭证 | storage_state / cookie jar → AES-GCM `CredentialStore`（0600，keyring 主密钥） | D-023 ②类 |
| git 双保险 | `/.paper-crawler/`（整目录锚定，D-032）+ `paper-crawler.toml` / `*.enc` / `.filekey` / `profiles.toml` / `auth/state/` 入 `.gitignore` | 07 §7 + D-032 |

- **护栏正则与 obslog 脱敏键单一同源**（`src/paper_crawler/sensitive.py`），防两套清单漂移。
  项目级护栏不含裸 `key`（误伤 `key_ref` 引用名）与 `email`（`identity.email` 属合法非凭证键）。

## 新第三方凭证接入定式（D-025 §5）

未来第三方凭证（Kaggle 等）一律 `[auth.<name>]` 槽 + 单一 config-home，不依赖各工具家目录约定
（如 `~/.kaggle/kaggle.json`）。三步：①`config.py` 加 `Config.<name>_*` 字段（沿既有样板）
②`config.example.toml` 补注释槽 ③adapter 经既有 `ApiKeyConsumer`/专属 client 注入（凭证隔离红线）。
