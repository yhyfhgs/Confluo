# config/ — 配置规范总纲

> 本目录**只放规范与样例**——真实凭证/配置值**绝不入**（AC-0.3 不变式；CI 断言 `config/**`
> 无凭证形态）。完整设计见 [docs/design/10-config-layout.md](../docs/design/10-config-layout.md)（D-025）。

## 文件

| 文件 | 用途 |
|---|---|
| `config.example.toml` | config-home `config.toml` 全键注释模板（identity/paths/rate/retry/openalex + `[auth.*]` 全部凭证槽）。复制到 config-home 后填真实值。 |
| `profiles.example.toml` | AuthProvider profiles 样例（api_key / cookie_session / sso_flow / ezproxy 四 kind 各一，占位 URL/ref，无密钥明文）。复制到 `<config-home>/auth/profiles.toml`。 |

## 配置住哪里 · 分层加载优先级（高→低，逐键覆盖）

```
1. env（PAPER_CRAWLER_* / [auth.*] env 覆盖）        ← 最高（CI/临时会话不落盘凭证）
2. 项目级 ./paper-crawler.toml（仅非敏感键）          ← 本机工作区层（路径/限速/venue 目录；.gitignore）
3. config-home config.toml（$PAPER_CRAWLER_HOME 或 ~/.paper-crawler）  ← 家目录，仓库外，可含敏感槽
4. 内置默认（Config dataclass 字段默认值）            ← 兜底
```

- config-home 解析：显式 `--home` > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`。
- 项目级文件：自 `cwd` 起向上查 `paper-crawler.toml`，首个命中即读；缺失静默跳过。
- **自查生效值 + 来源层**：`crawler config show`（敏感值脱敏；未配置显示 `(unset)`）。

## 敏感边界不变式（写入即冻结）

| 边界 | 规则 | 依据 |
|---|---|---|
| 凭证物理位置 | 只存 config-home（仓库外）或 env；**绝不入仓库工作树** | AC-0.3 不变式 |
| 项目级文件 | 仅非敏感键（路径/限速/venue 目录）；敏感键形态 → 启动护栏 `CrawlerError(CONFIG)` 拒启动 | D-025 护栏 |
| 日志/报告 | 敏感值一律 obslog `redact`（cookie/token/api_key/insttoken/password/secret/email/…） | AC-0.4 |
| 有状态凭证 | storage_state / cookie jar → AES-GCM `CredentialStore`（0600，keyring 主密钥） | D-023 ②类 |
| git 双保险 | `paper-crawler.toml` / `*.enc` / `.filekey` / `profiles.toml` / `auth/state/` 入 `.gitignore` | 07 §7 |

- **护栏正则与 obslog 脱敏键单一同源**（`src/paper_crawler/sensitive.py`），防两套清单漂移。
  项目级护栏不含裸 `key`（误伤 `key_ref` 引用名）与 `email`（`identity.email` 属合法非凭证键）。

## 新第三方凭证接入定式（D-025 §5）

未来第三方凭证（Kaggle 等）一律 `[auth.<name>]` 槽 + 单一 config-home，不依赖各工具家目录约定
（如 `~/.kaggle/kaggle.json`）。三步：①`config.py` 加 `Config.<name>_*` 字段（沿既有样板）
②`config.example.toml` 补注释槽 ③adapter 经既有 `ApiKeyConsumer`/专属 client 注入（凭证隔离红线）。
