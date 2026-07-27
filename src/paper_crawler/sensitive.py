"""敏感键名模式的**单一权威源**（D-025 / 10-config-layout §3.1；auth-framework §5）。

`obslog.redact()`（日志/报告脱敏）与 `config` 项目级敏感键护栏（拒启动）**共享核心
凭证键名**——在此定义一次，两个消费方各自在核心之上叠加自己的专属项，杜绝"两套清单
各自漂移"（此前 obslog 与 config 若各写一份正则，某天补了 `insttoken` 却漏了另一处）。

两个消费方的**受控差异**（非漂移，均有依据）：

- **obslog 脱敏**（`REDACT_KEY_PATTERN`）：核心 + `email`（unpaywall `?email=` 查询参数须
  与凭证同等脱敏，aggregators §3 B-B4）+ 具名认证头（`x-els-apikey` / `tdm-token` /
  `wiley-tdm-client-token`——`\btoken` 对 "insttoken"/"APIKey" 内嵌形态漏匹配，显式补以
  增强自证，auth-framework §5）+ **签名 URL 参数族**（`signature` / `sig` / `credential` /
  `key-pair-id`——browser-fetch 同批 volatile URL 的签名段即一次性凭证，design/11 §4.4）。
  脱敏宁滥勿缺。
- **config 项目级护栏**（`CONFIG_GUARD_KEY_PATTERN`）：核心 + 凭证同义词（`credentials?` /
  `passwd` / `private_key`）——但**不含** `email`（`identity.email` 属合法非凭证配置键）
  与**裸 `key`**（会误伤 `key_ref` 类引用名）。10-config §3.1 复审 §4 采纳（2026-07-23）。

消费方各自持 `re.IGNORECASE`；obslog 用 `\b(<pattern>)` 词边界，config 护栏用子串
`re.search`（10-config §3.1"规范化子串/正则匹配"）。核心片段均**无捕获组**，故安全用于
obslog `_HEADER_STYLE`/`_QUERY_STYLE` 的 `\b(...)` 包裹（组号不被内层组打乱）。
"""

# 核心凭证键名（obslog 与 config 护栏都视为敏感）：认证头 / 密钥 / 会话态。
# 各项为 `|` alternation 的裸片段；`insttoken` 单列因 `\btoken` 对 "insttoken" 无词边界
# 漏匹配（obslog 侧硬需求），config 侧子串匹配虽已被 `token` 覆盖，共列于此保单一同源。
_CORE_SENSITIVE_KEYS: tuple[str, ...] = (
    "set-cookie",
    "cookie",
    "authorization",
    "token",
    "api[_-]?key",
    "password",
    "secret",
    "session[_-]?id",
    "insttoken",
    "inst[-_]?token",
)

# obslog 脱敏专属追加（含 email + 具名认证头 + 签名 URL 参数；见模块 docstring 的受控差异）。
# **签名族**（T20 审计 R1 F-2）：browser-fetch 同批 volatile URL（design/11 §4.4）的签名段
# 就是一次性凭证——`Delivery.cfm?…&signature=…` / S3 `X-Amz-Signature`·`X-Amz-Credential` /
# CloudFront `Signature`·`Key-Pair-Id`。`\b` 词边界使 `X-Amz-` 类前缀天然覆盖（连字符是词
# 边界），亦不误伤形近参数（`design=`/`sig_alg=` 的 `sig` 后不是 `=`，不匹配）。
# 有意**不含** `expires`/`policy`：无签名即不可用，且时刻/策略段是审计可读面。
_REDACT_EXTRA_KEYS: tuple[str, ...] = (
    "email",
    "x-els-apikey",
    "tdm[-_]?token",
    "wiley-tdm-client-token",
    "signature",
    "sig",
    "credentials?",
    "key[-_]?pair[-_]?id",
)

# config 项目级护栏专属追加（凭证同义词；**不含** email / 裸 key，见模块 docstring）。
# 用 `credentials?`（非 `credential(s)?`）以避免引入捕获组——护栏用 `re.search` 不取组，
# 但保持无组更稳（防未来若被复用到需组号的场合）。
_CONFIG_GUARD_EXTRA_KEYS: tuple[str, ...] = (
    "apikey",
    "passwd",
    "credentials?",
    "private[-_]?key",
)

# obslog `redact()` 用（`\b(<pattern>)` 词边界 + IGNORECASE）。
REDACT_KEY_PATTERN: str = "|".join((*_CORE_SENSITIVE_KEYS, *_REDACT_EXTRA_KEYS))

# config 项目级 `./paper-crawler.toml` 敏感键护栏用（子串 `re.search` + IGNORECASE，拒启动）。
CONFIG_GUARD_KEY_PATTERN: str = "|".join((*_CORE_SENSITIVE_KEYS, *_CONFIG_GUARD_EXTRA_KEYS))


__all__ = ["CONFIG_GUARD_KEY_PATTERN", "REDACT_KEY_PATTERN"]
