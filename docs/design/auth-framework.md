---
title: 认证框架实现级详设（AuthProvider 四实现 + 凭证库 + CLI + pipeline 接缝）
status: draft
owner: fable5
updated: 2026-07-23
---

# 认证框架 · 实现级详设

> 本文档把 [design/07-auth-session.md](07-auth-session.md)（approved）§2 的设计伪代码与
> [design/04-auth-gated-module.md](04-auth-gated-module.md)（approved）§4/§5/§7 的运行时协议
> **落到字段级实现规格**，作为 Phase 4 W0 硬门禁件：实现 agent（T1~T7）只依据本文档开工，
> 双评审 `approved` 前不落 `src/paper_crawler/auth/` 代码。
> 语义基座不得漂移——本稿只**具体化**（伪代码→真实 Python 签名/类型/异常）与**接缝落地**，
> 不改 04/07 原文的任何决策；两文档的语义分歧一律以 04/07 为准，回本稿修订。
> 决策依据：D-006（人在回路首登 + storage_state 复用 + 绝不对抗风控）、D-014（UA 身份）。
> 红线（AGENTS.md §6）：只用用户自有合法凭证；不对抗风控/不解 CAPTCHA；凭证与 session 永不入 git。
> 接缝面：[design/02 §3](02-plugin-framework.md)（SourceAdapter 冻结协议）、
> [design/05 §2/§4](05-pipeline.md)（任务状态机 + 错误分类学）、[design/06 §2](06-data-model.md)（asset/fetch_log）；
> 平台侧详设（`elsevier_sd`/`oup_silverchair`/`wiley`）见各 adapter 文档（P0b 定稿，本稿不覆盖平台内部）。

## 0. 本 Phase 平台范围（controller 预裁决，写入即冻结，不再开放讨论）

| 平台 | 本 Phase 处置 | AuthProvider 载体 |
|---|---|---|
| `elsevier_sd` | **深做**（AC-4.1 载体 = Elsevier API 路径） | APIKey（真实 key 验证；JFE DOI 经 Article Retrieval API 取 PDF） |
| `oup_silverchair` | **深做**（QJE fulltext_source 收敛 #2） | CookieSession + SSOFlow（mock IdP 集成验证） |
| `wiley` | **条件件**（R0 勘察后裁决：纳入/骨架/顺延） | APIKey(TDM) — 依 R0 |
| `uchicago`/`informs`/`ieee_xplore`/`cambridge`/`springer`/`jstor` | **顺延后续 Phase**（development-plan R5 范围锁定） | — |
| `acm_dl` | D-020 到期重评 = 文档级独立小件（依 R0 证据），不在本框架内落码 | — |

- **AuthProvider 四实现全做**（不因平台范围收窄而少做 provider——框架完备性优先）：
  APIKey（elsevier 真实验证）、CookieSession + SSOFlow（oup 载体 + mock IdP 集成）、
  EZProxy（URL 重写纯逻辑 + mock 集成，**无真实机构凭证也可完整离线测试**）。
- **AC-4.1 载体锚定 Elsevier API**：`auth login elsevier` 即 APIKey 配置校验（不依赖机构 SSO）；
  JFE DOI 经 Article Retrieval API 取 PDF。这使 AC-4.1 的离线 DoD 不被"真实机构 SSO 首登"阻塞。
- **真实凭证 runbook**（机构 SSO 首登类）= 分层验收的"用户参与层"（testing/records 留痕），
  **离线 DoD 不依赖它**（沿 D-018 分层验收先例）。

## 1. 模块布局（`src/paper_crawler/auth/` 包内文件清单与职责）

新建包 `src/paper_crawler/auth/`，经 duck-typed 接线融入既有装配（不改 CLI `_build_env` 主干签名）。

| 文件 | 职责 | 依赖（import 方向，无环） |
|---|---|---|
| `auth/__init__.py` | 导出 `AuthProvider`/`SessionHandle`/`HealthStatus`/`AuthRequired`/`Challenged`/`load_providers`/`AuthManager` | — |
| `auth/protocol.py` | **接口冻结件**：`AuthProvider` Protocol（五方法）、`ProviderKind`；`@runtime_checkable` | `types`（SessionHandle/enum）、`errors` |
| `auth/store.py` | `CredentialStore`：AES-GCM 加解密、keyring↔文件密钥降级链、0600 强制、`profiles.toml` 加载 | `config`、`errors`；**惰性** import `cryptography`/`keyring` |
| `auth/providers/api_key.py` | `ApiKeyProvider`（Elsevier `X-ELS-APIKey`(+`X-ELS-Insttoken`)/Wiley TDM token/CORE 等） | `store`、`http`、`errors`、`types` |
| `auth/providers/cookie_session.py` | `CookieSessionProvider`（Silverchair 系直取 cookie jar；headless 复用 storage_state） | `store`、`http`、`browser`（惰性）、`challenge` |
| `auth/providers/sso_flow.py` | `SSOFlowProvider`（Shibboleth/OpenAthens；headless 重放续期） | `cookie_session`（共享 storage_state 机制）、`browser`（惰性） |
| `auth/providers/ezproxy.py` | `EZProxyProvider`（URL 重写表 + proxy cookie 维持）；`rewrite_url` 非恒等 | `store`、`http` |
| `auth/challenge.py` | `ChallengeDetector`（04 §7 特征库判定器）；`ClassifyResult` 四态 | `obslog`（redact）、`errors` |
| `auth/browser.py` | Playwright 边界薄封装（首登有头启动 / storage_state 导出 / 浏览器上下文下载）；**惰性** import `playwright` | `errors`；`[auth-browser]` extra |
| `auth/manager.py` | `AuthManager`：provider 注册表 + `active_profile` 解析 + session 缓存 + 健康门/配额编排入口 | 上列全部 |
| `auth/cli.py` | `crawler auth login/status/logout` 子命令实现（薄接线，纯逻辑在 manager/store） | `manager`、`store`；由 `cli.py` 挂载子 app |

- **接线原则（纯附加，零回归）**：沿 Phase 2/3 `HttpClientConsumer`/`EnrichmentSource` duck-typed 先例——
  auth_gated adapter 经既有 `resolve_assets(…, session)`/`fetch_asset(…, session)` 的 `session` 形参接收
  `SessionHandle`（该形参自 Phase 1 起即在冻结协议内，Phase 1-3 恒传 None）；pipeline 装配期由
  `AuthManager` 解析 session 并注入。**不新增 SourceAdapter 协议方法**。
- **Playwright 绝不成为核心路径硬依赖**：`auth/browser.py` 惰性 import；未装 `[auth-browser]` 时
  CookieSession/SSO 的**首登**抛 `AuthRequired(detail="pip install paper-crawler[auth-browser]")`，
  APIKey 路径（elsevier AC-4.1）与所有 httpx-直取 fetch/健康门/mock IdP 测试完全不触 Playwright（§9/§10）。

## 2. 接口冻结件候选（签名逐字精确；T1 落盘后冻结，改动须仲裁）

> 以下签名对齐 07 §2 伪代码，落为真实 Python（含类型、默认值、异常）。冻结后实现期不得改。

### 2.1 SessionHandle + 枚举（**具体化 `types.SessionHandle`；AC-4.x 全线载体**）

`types.py` 现有 `SessionHandle = Any`（line 128–129，注释"Phase 4 具体化（design/07）；Phase 1 恒 None"）。
本 Phase **兑现该注释**——把别名替换为具体 frozen dataclass。这是既有代码显式预留的**受控具体化**，
非协议漂移：`SourceAdapter` 冻结协议的 `session: SessionHandle | None` 由 `Any|None` 精化为 `<concrete>|None`，
既有全部 adapter（恒传/收 None）零改动零回归。dataclass 与其枚举落在 `types.py`（leaf，避免
`auth/`→`types`→`auth/` 环），`auth/` 与 adapter 均从 `types` import。

```python
# types.py（替换 line 128–129 的 SessionHandle = Any）
class HealthStatus(StrEnum):
    OK = "ok"
    EXPIRED = "expired"
    CHALLENGED = "challenged"

class SessionBackend(StrEnum):
    HTTPX_COOKIES = "httpx_cookies"       # cookie jar → httpx（Silverchair 直取）
    PLAYWRIGHT_STATE = "playwright_state" # storage_state（浏览器上下文复用）
    BEARER_TOKEN = "bearer_token"         # API key / TDM token（无状态凭证）

@dataclass(frozen=True)
class SessionHandle:
    provider_id: str                      # 'elsevier' / 'oup@campus' / 'ezproxy_myuniv'
    backend: SessionBackend
    payload_ref: str                      # CredentialStore 内加密条目引用（state/ 文件名 或 keyring 条目名）
    established_at: datetime
    est_ttl: timedelta | None = None      # 经验估计，仅用于主动提前 health_check（07 §2）
```

- 值语义：`SessionHandle` 是**指针**（`payload_ref` 指向加密存储），**绝不内联凭证明文**——
  handle 可安全进日志（`payload_ref` 是条目名非密文；仍经 obslog 兜底脱敏）。frozen + hashable
  与既有 dataclass 约定一致（types.py 模块 docstring）。

### 2.2 AuthProvider Protocol（**五方法冻结签名**；`auth/protocol.py`）

```python
ProviderKind = Literal["cookie_session", "ezproxy", "sso_flow", "api_key"]

@runtime_checkable
class AuthProvider(Protocol):
    provider_id: str                      # profiles.toml 的 provider 键（含 profile 后缀，如 'elsevier@ezproxy'）
    kind: ProviderKind

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        """返回可用会话。不可用且 interactive=False → raise AuthRequired（不半途而废，07 §5-1）。
        interactive=True 时可走首登（headed 浏览器 / 交互式 key 配置校验）。"""

    def health_check(self, session: SessionHandle) -> HealthStatus:
        """OK | EXPIRED | CHALLENGED（07 §2）。探针不触发风控对抗——CHALLENGED 即如实上报。"""

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        """静默续期成功→新 handle；不可静默续期→None（07 §2；SSO 侧 IdP session 尚存时常见可续）。"""

    def invalidate(self, session: SessionHandle) -> None:
        """使 session 失效并从 CredentialStore 删除其 payload（AC-4.5 取证式彻底删除）。"""

    def rewrite_url(self, url: str) -> str:
        """默认恒等（AdapterProviderBase 提供）；仅 EZProxyProvider 覆盖为真实重写（07 §2/§3.2）。"""
```

- **异常契约**：`ensure_session(interactive=False)` 无 session → `AuthRequired`；探针命中风控 →
  `Challenged`（见 §2.4）。其余网络异常沿用 `HttpClient` 冻结错误映射（§6）。
- **便利基类** `AuthProviderBase`（非冻结，仿 `AdapterBase`）：提供 `rewrite_url` 恒等默认 + `invalidate`
  的 store 删除样板；四 provider 各覆盖 `ensure_session`/`health_check`/`refresh`。

### 2.3 CredentialStore 读写接口（`auth/store.py`）

```python
class CredentialStore:
    def __init__(self, home: Path) -> None: ...          # home/auth/{profiles.toml,state/}

    # -- 加密状态（storage_state / cookie jar；AES-GCM，见 §3）--
    def read_state(self, ref: str) -> bytes: ...          # 解密取；缺失→raise AuthRequired
    def write_state(self, ref: str, data: bytes) -> None: ...  # 加密落盘 state/<ref>.enc，0600 强制
    def delete_state(self, ref: str) -> None: ...         # 覆写后 unlink（AC-4.5；缺失静默 no-op）

    # -- 密钥类凭证（API key / TDM token / insttoken）--
    def read_key(self, ref: str) -> str | None: ...       # keyring 条目（首选）或 config 注入；缺→None
    def has_key(self, ref: str) -> bool: ...              # ensure_session 的存在性预检（不取值）

    # -- profiles 装载 --
    def load_profiles(self) -> dict[str, ProviderProfile]: ...  # 解析 profiles.toml（§3 schema）
```

- `read_state`/`write_state` 处理密文；主密钥解析（keyring vs 文件密钥）在 store 内部（§3 降级链），
  provider 不感知加密细节。`read_key` 供 APIKeyProvider——**密钥值绝不落 profiles.toml 明文**（只存 `key_ref`）。

### 2.4 AuthRequired / Challenged 异常（`errors.py` 分类学中的位置）

沿 `CapabilityNotSupported(CrawlerError)` 固定 `error_class` 的先例（errors.py line 42–46），
**纯附加**两个 `CrawlerError` 子类，落进既有九类错误分类学（design/05 §4），不新增 ErrorClass：

```python
# errors.py 追加（不改 ErrorClass 九类）
class AuthRequired(CrawlerError):
    """无可用 session 且未交互（首登缺失/session 已 invalidate）；error_class 恒 AUTH_EXPIRED。
    → runner 路由为整批 BLOCKED(auth)，提示 `crawler auth login <provider>`。"""
    def __init__(self, msg: str = "auth session required", *, detail: str = "") -> None:
        super().__init__(ErrorClass.AUTH_EXPIRED, msg, detail=detail)

class Challenged(CrawlerError):
    """风控/CAPTCHA/异常验证页命中特征库（§11）；error_class 恒 CHALLENGE。
    → runner 路由为 BLOCKED(challenge) + 平台冷却（§8）。绝不尝试破解（AC-0.2）。"""
    def __init__(self, msg: str = "anti-abuse challenge detected", *, detail: str = "") -> None:
        super().__init__(ErrorClass.CHALLENGE, msg, detail=detail)
```

- **映射到状态机**：`AUTH_EXPIRED`/`CHALLENGE` 均已在 runner `_route_error` 走 BLOCKED 路径
  （runner.py：AUTH_EXPIRED→block+同 venue 连带；CHALLENGE∈`_BLOCK_CLASSES`→block）——本 Phase
  只需让 provider/adapter 抛这两个子类，**runner 现有路由零改动即生效**（§8 细化冷却）。

## 3. 凭证库落地（存储、加密、schema、权限、gitignore）

### 3.1 存储布局（07 §4 具体化）

```
<config-home>/auth/            # config-home = Config.home（不硬编码 ~/.paper-crawler；PAPER_CRAWLER_HOME 可覆盖）
├── profiles.toml              # provider 定义（无密钥明文；只引用 keyring 条目名 / state 文件名）
├── state/                     # 加密的 storage_state / cookie jar
│   ├── <ref>.enc              # AES-GCM 密文（0600）
│   └── .filekey               # 降级路径的文件主密钥（0600；keyring 可用时不存在）
```

- 目录随 `Config.ensure_dirs()` 扩展创建（`auth/`、`auth/state/`）；**目录权限 0700、文件 0600 强制**（§3.4）。

### 3.2 加密方案（`cryptography` 依赖 vs 标准库——评估与结论）

**评估**：Python 标准库**无任何对称加密原语**（`hashlib`/`hmac` 只有摘要与 MAC，无 AES/ChaCha 分组密码）——
07 §4 明文要求的 **AES-GCM 认证加密无法用纯标准库实现**。候选：

| 方案 | 提供 AES-GCM | 评估 |
|---|---|---|
| **`cryptography`（pyca）** | `hazmat.primitives.ciphers.aead.AESGCM` | 事实标准、经审计、维护活跃；二进制（Rust/OpenSSL）依赖较重 |
| `pynacl`（libsodium） | 仅 XSalsa20-Poly1305（非 AES-GCM） | 与 07 §4"AES-GCM"字面不符；换算法需改设计 |
| 纯标准库 | ✗ | 不可行（无分组密码） |

**结论**：取 **`cryptography>=42`，用 `AESGCM`**，**作为可选依赖** `[project.optional-dependencies].auth`
（**不进核心 `dependencies`**——Phase 1-3 聚合层零加密需求，核心框架不应因认证域引入重二进制依赖）。
`auth/store.py` **惰性 import**：未装 `[auth]` 时，需加密的路径（CookieSession/SSO 首登、`write_state`）
抛 `CrawlerError(CONFIG, "pip install paper-crawler[auth]")`；纯 APIKey 路径（elsevier key 存 keyring/config，
无 storage_state 加密需求）**不触 `cryptography`**——AC-4.1 离线 DoD 不被该依赖阻塞。
保持 07 §4"AES-GCM"字面不漂移。

**加密参数（实现期冻结）**：AES-256-GCM；每文件随机 12-byte nonce（前置于密文）；主密钥 32 byte；
`AESGCM(key).encrypt(nonce, plaintext, associated_data=ref.encode())`（AAD 绑定条目名，防跨条目重放）。

### 3.3 主密钥解析与降级链（keyring 首选 → 文件密钥 + 显式警告）

```
主密钥获取（store 内部，惰性）:
1. try import keyring; keyring.get_keyring() 非 fail 后端
   → 有: 从 keyring 服务名 "paper-crawler" 取/存主密钥（首次随机生成 32B 存入）; backend="keyring"
2. keyring 不可用（ImportError / keyring.errors.NoKeyringError / 后端为 fail/null）
   → 降级: state/.filekey（32B 随机，0600）; backend="filekey"
   → **显式警告一次**（obslog WARNING + stderr）:
     "⚠ 系统无可用 keyring 后端；认证主密钥降级为文件密钥 state/.filekey（0600）。
      该文件泄漏等价 session 泄漏——确保 config-home 目录访问受控（AGENTS §6.4）。"
```

- **降级判定点**：`get_keyring()` 返回 `keyring.backends.fail.Keyring` 或抛 `NoKeyringError` 即判无后端
  （常见于无 SecretService 的 headless Linux）。判定与警告在 `CredentialStore._resolve_master_key()`，
  每进程仅警告一次（缓存标志）。
- keyring 亦为 `[auth]` extra 成员（`keyring>=24`）；**包安装成功 ≠ 后端可用**——降级看运行时后端。

### 3.4 profiles.toml schema（全字段）

```toml
# <config-home>/auth/profiles.toml —— 无任何密钥明文
schema_version = 1

[providers.elsevier]                      # profile 键 = provider_id（无 @ 后缀 = 默认 profile）
kind = "api_key"                          # cookie_session | ezproxy | sso_flow | api_key
platform = "elsevier_sd"                  # 绑定的 adapter_id（VenueSpec.auth.provider_hint 指向本键的前缀）
key_ref = "elsevier_apikey"               # keyring 条目名（值不在此文件）
insttoken_ref = "elsevier_insttoken"      # 可选：机构 token 条目名
quota_probe = "https://api.elsevier.com/content/article/doi/10.1016/j.jfineco.2011.03.021"
                                          # ensure_session 连通性/entitlement 探测端点（已知有权 DOI）

[providers."oup@campus"]                  # @ 后缀 = 具名 profile（多机构/多账号，07 §6）
kind = "cookie_session"
platform = "oup_silverchair"
login_url = "https://academic.oup.com/qje"          # 首登打开页
probe_url = "https://academic.oup.com/my-account"   # 已登录探针（判定=不 302→signin 且含账号标识）
state_ref = "oup_campus_state"            # state/<ref>.enc（加密 storage_state）
est_ttl_hours = 24                        # 经验 TTL（主动提前 health_check）

[providers."oup@shib"]                     # 同平台 SSO profile
kind = "sso_flow"
platform = "oup_silverchair"
inst_login_url = "https://academic.oup.com/…/InstitutionalLogin"
wayf_hint = "My University"                # WAYF 机构选择关键词（首登辅助，非自动化 MFA）
probe_url = "https://academic.oup.com/my-account"
state_ref = "oup_shib_state"
est_ttl_hours = 8                          # 出版社侧 cookie 常数小时

[providers."elsevier@ezproxy"]
kind = "ezproxy"
platform = "elsevier_sd"
proxy_base = "https://login.myuniv.edu/login?url="  # EZProxy 登录入口
# 域名重写表（泛化规则：host 的 '.' → '-'，追加 proxy 后缀）
rewrite_suffix = ".login-myuniv-edu.ezproxy"
state_ref = "ezproxy_myuniv_state"        # proxy cookie
est_ttl_hours = 12
```

对应 `config.toml`（非敏感）声明运行时选择（07 §6）：
```toml
[auth]
active_profile = { oup_silverchair = "oup@campus", elsevier_sd = "elsevier" }
# CLI --profile 临时覆盖；场景：在校用直连、离校切 elsevier@ezproxy，无需改 VenueSpec
```

- `ProviderProfile` dataclass（store 解析产物）字段 = 上表全键，`extra` 严格拒绝（未知键 → `CrawlerError(CONFIG)`，
  仿 `VenueSpec` 的 `extra="forbid"`）；`kind` 与必填字段的组合校验在 `load_profiles`（如 `api_key` 必有 `key_ref`）。

### 3.5 0600 权限强制点 + .gitignore 双保险

- **强制点**：`write_state` 用 `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)`（原子创建即带权限，
  不依赖后续 chmod 的竞态窗）；`.filekey` 同法；`auth/`、`auth/state/` 目录 `mkdir(mode=0o700)`。
  启动期 `AuthManager` 巡检既有文件权限，非 0600 → obslog WARNING（不自动改，避免掩盖问题）。
- **.gitignore 双保险**（07 §7"双保险"）：现有 `.gitignore` 已含 `credentials/`、`*.secret`、
  `storage_state*.json`、`auth_profiles/`、`.env*`。本 Phase **新增条目**（config-home 通常在仓库外，
  双保险防误置仓库内）：
  ```gitignore
  # ---- 认证框架（Phase 4；绝不入库）----
  auth/state/
  *.enc
  .filekey
  profiles.toml
  ```
  （AC-0.3：git 全历史扫描断言无 `*.enc`/`.filekey`/`profiles.toml`/cookie 形态。）

> **AC 对应**：§3 全节 = AC-0.3（凭证不入 git）、AC-4.5（logout 无残留，见 §4.3 取证清单）；`cryptography` 选择 = 设计取舍记录（§9 修订记录候选 ADR）。

## 4. `crawler auth login/status/logout` CLI（参数、输出、退出码）

`cli.py` 挂载子命令组 `auth`（`typer.Typer`）；纯逻辑在 `auth/manager.py`+`auth/cli.py`，`cli.py` 只接线（既有分工）。

### 4.1 `crawler auth login <provider> [--profile P] [--home H] [-v]`

| kind | 行为 | 退出码 |
|---|---|---|
| `api_key` | 校验 `key_ref` 存在（keyring/config）→ 调 `quota_probe` 连通+entitlement 探测 → 写/更新 `SessionHandle(BEARER_TOKEN)` | 0 成功；2 key 缺失（提示配置路径）；1 探测失败 |
| `cookie_session` | 惰性 import `auth/browser.py` → **有头** persistent context 打开 `login_url` → 提示"完成登录（含 MFA）后回车" → 访问 `probe_url` 验证 → 导出 storage_state（+ cookie jar）加密落盘 | 0；2 未装 `[auth-browser]`（提示 `pip install paper-crawler[auth-browser]`）；1 探针失败 |
| `sso_flow` | 同上，打开 `inst_login_url` → WAYF 选机构（`wayf_hint` 提示）→ IdP 登录 → 回跳种 cookie → 保存 storage_state | 同上 |
| `ezproxy` | 有头打开 `proxy_base + <目标URL>` → 人工完成校方认证 → proxy cookie 持久化 | 同上 |

- 参数：`<provider>`（位置，profiles.toml 键；未知 → 退出 2）；`--profile`（临时覆盖 active_profile）；
  `--home`/`-v` 同既有全局项。**首登人在回路**（D-006/07 §3）——不自动填密码、不自动过 MFA。

### 4.2 `crawler auth status [--home H] [-v]`

输出状态表（`_render_table` 既有渲染），列：

| provider | kind | backend | session | last_health | est_expiry | state |
|---|---|---|---|---|---|---|
| elsevier | api_key | bearer_token | configured | OK (2026-07-23) | — | ready |
| oup@campus | cookie_session | httpx_cookies | age 3h | OK (2026-07-23 09:00) | ~21h | ready |
| oup@shib | sso_flow | playwright_state | age 9h | EXPIRED | expired | needs `auth login oup@shib` |
| elsevier@ezproxy | ezproxy | httpx_cookies | absent | — | — | needs `auth login elsevier@ezproxy` |

- `session` = `now - established_at`；`est_expiry` = `established_at + est_ttl - now`（无 est_ttl → "—"）；
  `last_health` = 最近一次 health_check 结果+时刻（缓存于 state 元数据）。**只读，不触发真实探测**（避免
  status 命令消耗配额/触发风控）；退出码恒 0（状态呈现非对账判据，同 `oa-report` 口径）。

### 4.3 `crawler auth logout <provider> [--home H]`（AC-4.5 取证式无残留）

- 调 `provider.invalidate(session)` → `store.delete_state(ref)`（**先覆写随机字节再 unlink**，防删除后
  磁盘残留可恢复）+ keyring 条目删除（api_key 类）+ 清除 state 元数据缓存。退出码 0；provider 未知 → 2。
- **AC-4.5 取证清单**（runbook + 自动断言双证）：logout 后 ①`state/<ref>.enc` 不存在
  ②keyring 无对应条目 ③进程内 session 缓存清空 ④obslog/report 无该 session 的明文残留（redact 断言）
  ⑤`git status` 无新增被跟踪凭证文件。

> **AC 对应**：§4 = AC-4.1（login 载体）、AC-4.5（logout 无残留）；退出码契约沿 design/05 Task 8 既有口径（用法/配置错=2、失败=1、成功/只读=0）。

## 5. 脱敏扩展（obslog `_SENSITIVE_KEYS` 新增键 + FetchLog URL 规则）

现状（obslog.py line 47–49）：`_SENSITIVE_KEYS = set-cookie|cookie|authorization|token|api[_-]?key|password|secret|session[_-]?id|email`。
`_HEADER_STYLE`/`_QUERY_STYLE` 用 `\b(<keys>)` 词边界匹配 `Key: value` / `key=value`（含引号变体）。

**逐键核验现状与缺口**（Phase 4 认证头/参数）：

| 键 | 现状 | 结论 |
|---|---|---|
| `cookie` / `set-cookie` | 已含 | ✅ 覆盖（storage_state 导出的 cookie 头） |
| `authorization` | 已含 | ✅ 覆盖（Bearer 头） |
| `x-els-apikey`（Elsevier） | `api[_-]?key` 经 `\b` 命中 `X-ELS-APIKey` 中 `APIKey`（`-`/`A` 处有词边界） | ✅ 覆盖，但**建议显式补** `x-els-apikey` 增强自证 |
| `tdm-token`（Wiley `Wiley-TDM-Client-Token`）| `token` 经 `\b` 命中 `-Token`（`-`/`T` 处边界） | ✅ 覆盖，但**建议显式补** `tdm[_-]?token` 与 `wiley-tdm-client-token` |
| **`insttoken`（Elsevier `X-ELS-Insttoken`）** | `\btoken` **不命中**——"Insttoken" 内 `t`/`t` 无词边界 | ❌ **缺口，必须新增** `insttoken`（含 `inst[_-]?token`） |

**T2 新增（`_SENSITIVE_KEYS` 追加，复用既有 `_HEADER_STYLE`/`_QUERY_STYLE` 分支，无需新正则）**：
```
… |email|insttoken|inst[-_]?token|x-els-apikey|tdm[-_]?token|wiley-tdm-client-token
```
- **`insttoken` 是唯一真实缺口**（单词无分隔符，`\btoken` 漏）；其余为显式增强（防未来头名变体 + 自证清晰）。
  沿 aggregators.md §3 B-B4 的 email 先例：**先扩脱敏正则 + 补脱敏单测，再实现携该头的 provider**（T2→T3 顺序硬约束）。
- **FetchLog URL 脱敏规则扩展**：`fetch_log.url`（design/05 §7）已恒经 `obslog.redact()`（http.py 每请求
  `log_event(url=…)`；stages fetch 落 `FetchLogRow.url=plan.url`）。EZProxy 重写后的 URL 含 proxy host
  但**不含凭证**（cookie 在头不在 URL），无需额外规则；若某平台把一次性 token 塞进 URL 查询参数
  （如 IEEE `stamp.jsp?…`，本 Phase 顺延），`_QUERY_STYLE` 对 `token=`/`apikey=` 已覆盖。**结论**：
  URL 侧无新增正则需求，只需 §5 的头键补全；FetchLog 存脱敏 URL 的既有不变式保持。

> **AC 对应**：§5 = AC-0.4（日志/报告无未脱敏 cookie/token）；测试判据见 §12（`insttoken` 明文注入→断言 jsonl 无残留）。

## 6. HttpClient 结构化扩展（检查单 #4 闭合：`CrawlerError.status_code`）

**问题**（phase3-report §5/§6 #4）：openalex 的 402（credit 耗尽）识别靠 `openalex/adapter.py::_looks_like_status`
正则解析 `CrawlerError` 消息里的 `"HTTP {status} for …"` 前缀——依赖异常消息格式，非稳定契约。

**纯附加方案**（`errors.py` + `http.py`，零回归）：给 `CrawlerError` 增结构化 `status_code` 字段，**默认 None**：

```python
# errors.py CrawlerError.__init__ 追加（keyword-only，默认 None——既有全部构造点零改动）
def __init__(self, error_class: ErrorClass, msg: str, *, detail: str = "",
             status_code: int | None = None) -> None:
    super().__init__(msg)
    self.error_class = error_class
    self.detail = detail
    self.status_code = status_code          # None = 非 HTTP 来源（超时/连接/解析等）
```

```python
# http.py _error_for_status / _rate_limited：映射时带上 status（该处 response.status_code 已在手）
return CrawlerError(ErrorClass.NO_ENTITLEMENT, msg, status_code=status)   # 例：403
# _rate_limited 同法带 status_code=429/503
```

- **默认 None 不破坏既有消费者**：`CrawlerError` 的现有构造点（http.py 超时/连接错、stages/adapter 的
  逻辑错）不传 `status_code` → None；读 `.status_code` 的新代码用 `exc.status_code == 402` 判定，
  非 HTTP 来源天然为 None（不会误判）。`http.py` 错误**映射表本身不变**（402 仍归 CONFIG"其余 4xx"）——
  只是**额外携带**原始 status，供上层精确重分类。
- **openalex 402 文本嗅探迁移路径**（T2 顺带闭合，或 T6 债务回填）：
  `_looks_like_status` 的正则解析 → 改为 `isinstance(exc, CrawlerError) and exc.status_code == 402`
  → 重分类为 `rate_limited` 特化（当日预算熔断，aggregators.md §5.3 语义不变）；旧正则删除。
  这是**更稳定的契约**（不依赖异常消息措辞），phase3-report §6 #4 闭合。
- **Phase 4 复用**：elsevier API 的 429+`X-ELS-Status: QUOTA_EXCEEDED`、entitlement 403 的精确分流
  （403 无权 vs 403 风控）同样受益于 `status_code`——provider 层 `exc.status_code` 直读，不再嗅探文本。

> **AC 对应**：§6 = 检查单 #4 闭合 + AC-4.3（no_entitlement 精确识别的基础设施）；测试：`test_errors.py` 断言默认 None + 带值路径，`test_http.py` 断言各状态码映射携带正确 `status_code`。

## 7. canary 凭证注入（检查单 #3 闭合）

**问题**（phase3-report §6 #3）：`cli.py::canary()`（line 1171–1187）在 `_env` 内**另起** `load_adapters()`
新鲜实例后直接 `run_canary()`——未像 `pull`（`_build_env` 的 `bind_http_client`+`_bind_openreview_token_client`）
/`enrich`（`_prepare_enrich_source`）那样注入 token/api_key。即便用户已配置 `openreview_token`/`s2_api_key`/
`openalex_api_key`（**含 Phase 2 已生效于 pull 的 openreview_token 存量**），canary 仍体现为匿名/未配置。

**设计**：抽出复用装配步骤 `_bind_healthcheck_credentials(env, adapters) -> list[HttpClient]`（返回专属
client 供调用方 close），canary 在 `run_canary` 前调用它，对每 adapter 施加与 pull/enrich 同款的凭证注入：

```
_bind_healthcheck_credentials(env, adapters):
  dedicated: list[HttpClient] = []
  bind_http_client(adapters, env.http)                    # 共享 UA+limiter（arxiv 等），同 _build_env
  orc = _bind_openreview_token_client(adapters, env.ctx.config, env.ctx.limiter)  # 复用既有
  if orc: dedicated.append(orc)
  # enrich 源：openalex（key 走 URL 参数，复用共享 client）+ s2（key 走头，需专属 client）
  for sid in ("openalex", "s2"):
      a = adapters.get(sid)
      if isinstance(a, EnrichmentSource): _apply_enrich_key(env, a, sid, dedicated)  # 抽自 _prepare_enrich_source
  # Phase 4 auth_gated：为已注册 provider 的 adapter 解析 session 注入（AuthManager）
  for aid, a in adapters.items():
      if getattr(a, "family", None) == "auth_gated":
          _try_inject_session(env, a, aid)                # 无 provider/无 session → 不注入（healthcheck 走 SKIP）
  return dedicated
```

- **canary 语义保持**（canary.py 分类规则不变）：auth_gated adapter 无配置 session → `healthcheck()` 抛
  `NotImplementedError`（或 `AuthRequired` 归一）→ **SKIP**（非 unhealthy，不误报退出码 1）；有 session →
  真实探针 → healthy/unhealthy。**精确复用** s2/openalex 的"无 key→NotImplementedError→SKIP"先例
  （零 canary.py 改动）。
- **收敛点**：`_build_env` 与 `canary` 共用同一装配语义（`_bind_healthcheck_credentials` 抽公共部分；
  `_build_env` 保留其 openreview 分支的现状调用，或一并改调该 helper——实现期择一，接口等价）。
  canary 的 `finally` 关闭 `dedicated` 全部 client（同 `_env` 对 `openreview_http` 的关闭）。

> **AC 对应**：§7 = 检查单 #3 闭合；测试：`test_cli_canary.py` 注入假 config（含 openreview_token）→ 断言
> openreview 行不再显示匿名态（healthy 而非因 403 unhealthy）；auth_gated 无 session → SKIP。

## 8. pipeline 接缝（检查单 #12 闭合 + 健康门 + 日配额 + BLOCKED 恢复）

> 本节落地 04 §4/§5 的运行时协议到 `pipeline/stages.py` + `runner.py` 的具体接线点。均为**纯附加**
> （新 StageContext 字段默认关闭 → Phase 1-3 venue 零行为变化）。

### 8.1 no_entitlement → unpaywall OA-fallback 接线点（#12，AC-4.3）

**现状缺口**（phase3-report §6 #12）：T5 只落 unpaywall adapter 能力（`lookup` 直调正确），
pipeline 侧 `no_entitlement → unpaywall 兜底`**未接线**。

**接线点 = `runner._route_error` 的 NO_ENTITLEMENT 分支**（runner.py line 371–372 现只 `mark_asset(no_entitlement)`）。
新增 OA-fallback 编排（受 `StageContext.oa_fallback: bool` 门控，默认 False；auth_gated venue 或 VenueSpec
声明 OA-fallback 时置 True）：

```
NO_ENTITLEMENT（fetch 失败 或 resolve entitlement 预检否）:
  1. mark_asset(asset_id, state="no_entitlement")            # 现有，保留
  2. if ctx.oa_fallback and 该 paper 有 doi identifier:
       enqueue 子任务 "oa_fallback"（params={"paper": <id>, "doi": <doi>}, parent_id=pull_id）
     （不重试原 asset、不计失败率——04 §4"不重试、不计失败率"）
```

新增 **`_stage_oa_fallback`**（stages.py，第七个 handler，仅本通道用）：
```
_stage_oa_fallback(ctx, task):
  doi = params["doi"]; paper_id = params["paper"]
  ua = ctx.unpaywall_adapter                          # AuthManager/StageContext 注入的 unpaywall 实例
  if ua is None: return "skipped"                     # 未装配 OA-fallback → 静默跳过
  ctx.limiter.acquire(ua.domains[0]) → sleeper        # unpaywall 独立域/独立 5 req/s（非 auth 平台配额）
  plan = ua.lookup(doi)                               # RESOLVE：best_oa_location.url_for_pdf（aggregators §5.5）
  if plan is None: return "done"                      # 无 OA 副本（AC-4.3"若存在"——不存在即如实无副本）
  new_asset = ctx.repo.plan_asset(paper_id, plan, source_adapter="unpaywall")  # kind=pdf, version="oa"
  enqueue "fetch"（asset=new_asset）                   # 走通用 fetcher（auth_needed=none, direct）
```

- **与 open_access 模块共享该 fallback**（04 §4）：同一 `_stage_oa_fallback` 亦服务开放模块的 no_entitlement
  兜底（非 auth 专属）。OA 副本 asset 独立身份 `(paper, pdf, "oa")`——与原平台 asset `(paper, pdf, None)`
  并存，不覆盖（asset 唯一键 `(paper_id, kind, version)`，design/06 §2）。
- **限速隔离**：unpaywall fetch 走 unpaywall 域桶（5 req/s），**不占 auth 平台的日配额**（§8.3）——
  OA 兜底不应被闭源平台的保守限速拖慢。

### 8.2 session 健康门（每 N=20 篇 / 15 min healthcheck；AC-4.2）

**接线点 = `runner._execute_claimed` 的 fetch 分支前**（新增门控，仅 auth_gated venue）。runner 新增运行态：

```
self._auth_batch: dict[str, _BatchGate]     # venue_id → 门计数器（每次 _new_report 重置）
_BatchGate = {fetched_since_check: int, last_check_at: datetime, session: SessionHandle}

fetch 执行前（auth_gated venue，有 session）:
  gate = self._auth_batch[venue]
  if gate.fetched_since_check >= 20 or (now - gate.last_check_at) >= 15min:
      status = provider.health_check(gate.session)         # OK|EXPIRED|CHALLENGED
      if status == EXPIRED:
          new = provider.refresh(gate.session)             # 静默续期
          if new: gate.session = new; gate.reset()
          else:  raise AuthRequired（→ 整批 BLOCKED(auth)，§8.4）
      elif status == CHALLENGED: raise Challenged（→ BLOCKED(challenge)+冷却，§8.4）
      else: gate.reset()                                    # OK
  # 执行 fetch；成功后 gate.fetched_since_check += 1
```

- **防"半批 401 轰炸"**（04 §4/AC-4.2）：门在**批内周期性**主动探测 + 首个 fetch 的 auth_expired 即
  `_auth_blocked_venues.add(venue)`（runner 现有机制），使**同 venue 剩余 fetch 连带 BLOCKED**——
  日志无连续 401/403（AC-4.2"≤2 次即停"）。N=20/15min 阈值经 `Config.auth_health_interval`（默认 20 篇）
  /`auth_health_max_age_s`（默认 900s）可配。
- **文件验证器联动**（04 §4）：fetch 后 magic-bytes 非 `%PDF` 或 <10KB → 现有 `INTEGRITY` 路径
  （stages.py `validate_pdf_magic`）**额外触发一次 health_check**（疑似 auth_leak——拦截页伪装 PDF）；
  实现为 `INTEGRITY` 路由时若 venue 为 auth_gated 则强制门 `last_check_at = 0`（下个 fetch 必探）。

### 8.3 日配额（FetchLog 对账；AC-4.4）

**接线点 = fetch 执行前（auth_gated venue）**，`repo` 新增只读查询 `count_fetch_today(domain) -> int`：
```
SELECT COUNT(*) FROM fetch_log
WHERE domain = ? AND error_class IS NULL AND DATE(created_at) = DATE('now')   # 成功取回计数
```
```
fetch 前:  if count_fetch_today(domain) >= cap:      # cap = VenueSpec.rate_limit 或 Config.auth_daily_cap（默认 200）
             raise CrawlerError(CONFIG, "daily quota reached", detail=f"cap={cap}")  # → BLOCKED(config)
```
- **对账证据源 = FetchLog**（design/05 §7 明示"AC-4.4 数据源"）——每资产取回一行；日配额判定读同表。
  `cap` 来源优先级：VenueSpec `rate_limit`（若声明日上限）> `Config.auth_daily_cap`（默认 200，04 §4）。
- **"宁慢勿封"**（04 §4）：配额达上限即 BLOCKED 该 venue 剩余 fetch（非 FAILED），次日或 `--force` 恢复。

### 8.4 BLOCKED(auth) / BLOCKED(challenge) → Phase 1 状态机映射

| provider/adapter 抛出 | error_class | runner 现有路由 | Phase 4 增量 |
|---|---|---|---|
| `AuthRequired` / 401 / 302→login / health_check EXPIRED 且 refresh→None | AUTH_EXPIRED | `queue.block` + 同 venue 剩余 fetch 连带 BLOCKED（`_auth_blocked_venues`）；提示 `crawler auth login` | **零改动**——现有 AUTH_EXPIRED 路径即满足 04 §7 |
| `Challenged` / 特征库命中（§11） | CHALLENGE | ∈ `_BLOCK_CLASSES` → `queue.block` | **新增平台冷却**：写 `<config-home>/state/cooldown/<platform>.json = {until: now+24h}`；`route_for`/健康门读该状态，冷却内该平台全队列 BLOCKED（04 §5"停止该平台全部队列 + 冷却 24h"） |
| 日配额达上限 | CONFIG | ∈ `_BLOCK_CLASSES` → `queue.block` | detail="daily quota"，报告显著呈现 |

- **人工恢复**（05 §2 / 04 §7）：BLOCKED 不占重试、不自动恢复；`crawler auth login <provider>`（重登，
  清对应 `_auth_blocked_venues`）→ `crawler resume <task|--all>` 转回 PENDING → 下次 drain 继续。
  challenge 冷却期满（或用户已在浏览器处理挑战后）`crawler resume` 恢复。**冷却状态非 git**（config-home）。
- **runner 状态复用**：`_auth_blocked_venues`（现有）承接 auth 连带；新增 `_challenge_cooldown`（venue→until）
  与 `_auth_batch`（健康门），均在 `_new_report` 重置（每次运行独立）。冷却 24h 跨运行持久化在
  config-home JSON（进程重启不丢），运行态缓存加速。

> **AC 对应**：§8.1=AC-4.3、§8.2=AC-4.2、§8.3=AC-4.4、§8.4=AC-4.2/4.6 + design/05 §2 BLOCKED-resume。

## 9. mock IdP 测试设计（AC-4.2/4.5/4.6 离线载体；纯 httpx vs 浏览器结论）

**核心结论（测试面最小化）**：**登录生命周期集成测试全程纯 httpx，进 CI，零 Playwright**。
Playwright 仅留给"真实首登"（headed）与"JS 生成 PDF 链接"两条**本 Phase 不进 CI**的路径。

**论证**——拆解 07 §8"login→state 保存→复用→过期→refresh 全生命周期"，逐段判定可测性：

| 生命周期段 | 能否纯 httpx | 载体 |
|---|---|---|
| 首登（人工输密码/MFA→导出 storage_state） | ✗（本质人在回路 + 真实 IdP） | 真实凭证 runbook（不进 CI）；单测用**假 Playwright seam**（§10）注入预置 storage_state |
| state 加密落盘 → 复用（headless 载 cookie jar → 探针） | ✅ | `CredentialStore` round-trip + httpx.Client(cookie jar) → mock 探针 |
| health_check（探针分类 OK/EXPIRED/CHALLENGED） | ✅ | mock 按请求 cookie 有效性返 200(账号页)/302→login/挑战页 |
| refresh（SSO 静默续期：重放 InstitutionalLogin） | ✅（mock IdP 发**纯 302 重定向 + Set-Cookie**，无 JS 自动提交表单） | mock 模拟 IdP session 尚存→回跳种新 cookie；IdP 也过期→ mock 停在 login→refresh 返 None |
| EZProxy rewrite + proxy cookie | ✅ | `rewrite_url` 纯字符串单测 + mock proxy 302 |
| APIKey ensure_session（quota 探测） | ✅ | mock 返 200+quota 头 / 401 / 429+QUOTA_EXCEEDED |

**mock IdP 机制（明确：纯 httpx，无本地服务器进程）**：
- 复用 `HttpClient` 既有 DI seam——`transport: httpx.BaseTransport | None`（http.py line 24 注释
  "T4 单测注入 `httpx.MockTransport` 的唯一通道"）。mock IdP = 一个 `httpx.MockTransport` 处理函数 +
  **进程内状态字典**（已签发 cookie→TTL、IdP session 标志），据请求路径/cookie/时钟返构造响应：
  ```
  /login          → 200 登录页（首登探测锚点）
  /my-account     → 有有效 cookie: 200 + 账号标识；无/过期: 302 → /login
  /InstitutionalLogin → IdP session 存: 302 链 + Set-Cookie(新)；否则: 302 → /idp/login（refresh→None）
  /article-pdf/…  → 有权: 200 %PDF…；无权: 302 → /article-abstract（no_entitlement）；风控: 403 + 挑战特征
  ```
- httpx.Client 在**单个 flow 内自维护 cookie jar**（跨请求携带），天然复现"种 cookie→后续请求带 cookie→
  TTL 到期→探针 302"。时钟经**可注入的 `now()`**（provider 依赖注入，测试推进假时钟触发 est_ttl/过期），
  不 sleep。storage_state 复用跨"进程重启"= 新 provider 实例 `read_state` → 载入新 `HttpClient(MockTransport)`。
- **零真实网络**（socket 禁网护栏内，同聚合层）；**无 ASGI/WSGI 本地服务器**（MockTransport 足够，更快更稳）。

**Playwright 的 CI 门控策略（若确需浏览器测试）**：
- 首登 headed 流程与浏览器上下文下载**默认不进 CI**。`auth/browser.py` 的逻辑经**假 seam**单测（§10）；
  真实浏览器集成测试标 `@pytest.mark.skipif(not _auth_browser_installed() or not os.environ.get("PC_BROWSER_TESTS"))`
  ——需**同时**满足"装了 `[auth-browser]`"且"显式置环境变量"才跑，默认 CI 双重跳过。
- **绝不让 Playwright 成为 `make check` 硬依赖**：默认 `pytest` 不 import playwright（惰性 + skip 门控）。

> **AC 对应**：§9 = AC-4.2（mock 过期检测≤20 篇内 BLOCKED）、AC-4.5（mock logout 后 store 无残留）、
> AC-4.6（mock 注入挑战页 → BLOCKED(challenge)+冷却）——**三者全在 CI 离线跑通**，不依赖真实凭证/浏览器。

## 10. Playwright 依赖策略（extras、无 playwright 环境行为、绝不硬依赖）

`pyproject.toml` 新增 `[project.optional-dependencies]`（现无该表）：
```toml
[project.optional-dependencies]
auth = ["cryptography>=42", "keyring>=24"]          # 凭证库：AES-GCM + 主密钥存储（§3.2/3.3）
auth-browser = ["playwright>=1.40"]                 # 首登 headed / 浏览器上下文下载（§9）
```

- **无 playwright 环境行为**：`auth/browser.py` 顶层不 import playwright；`_require_browser()` 在需要时
  `try import playwright` 失败 → 抛 `AuthRequired(detail="需浏览器首登：pip install paper-crawler[auth-browser] && playwright install chromium")`。
  受影响仅 CookieSession/SSO/EZProxy 的**首登**与**浏览器上下文 fetch**；APIKey 全链（elsevier AC-4.1）、
  所有 httpx-直取 fetch、健康门、mock IdP 测试**完全不触** playwright。
- **绝不成为核心路径硬依赖**：核心 `dependencies` 不含 playwright/cryptography/keyring；`make check`
  默认不 import 它们（惰性 + skip 门控）。CI 装 `[auth]`（轻）跑凭证库测试，**不装** `[auth-browser]`
  （重，含浏览器二进制）——浏览器测试靠 `PC_BROWSER_TESTS` 手动门。

> **AC 对应**：§10 = AGENTS §6 依赖最小化姿态（D-017 精神）+ AC-4.1 不被浏览器依赖阻塞。

## 11. 风控行为规范落地（挑战页判定器 + 四类 fixture）

`auth/challenge.py` 落地 04 §7 特征库：

```python
class ClassifyResult(StrEnum):
    OK = "ok"                          # 已登录/有权全文页
    LOGIN_REDIRECT = "login_redirect"  # 未登录→signin（→ AUTH_EXPIRED）
    NO_ENTITLEMENT = "no_entitlement"  # 有登录无订阅（article-abstract 路由/Get access 面板）
    CHALLENGE = "challenge"            # 风控/CAPTCHA（→ Challenged）

class ChallengeDetector:
    def classify(self, *, status: int, headers: Mapping[str, str],
                 final_url: str, body: bytes) -> ClassifyResult: ...
```

**特征库**（04 §5/§7 + elsevier-sd.md §2 / oup-silverchair.md §2 / wiley.md §2 勘察）：
| 信号 | 判定 |
|---|---|
| `cf-mitigated: challenge` 头 / body 含 "Just a moment..." / `/cdn-cgi/challenge-platform/` | CHALLENGE |
| body 含 hCaptcha/reCAPTCHA/"unusual activity"/"verify you are human" | CHALLENGE |
| 302/final_url 命中 `Shibboleth.sso`/`/signin`/`/login` 且无账号标识 | LOGIN_REDIRECT |
| final_url 命中 `article-abstract` / body 含 "Get access"/"Purchase" 面板且无 PDF 链接 | NO_ENTITLEMENT |
| status 200 + 账号标识 + 全文/PDF 节点 | OK |

- **判定器接口对齐 status_code**（§6）：`classify` 收结构化 `status`（非文本嗅探）；provider fetch/probe
  后调 `classify` → 映射为 `HealthStatus`/抛 `AuthRequired`/`Challenged`/标 no_entitlement。
- **四类 fixture 清单**（离线判定器回归，04 §8；每平台一套，本 Phase = oup + elsevier）：
  ① 已登录全文页（脱敏 storage_state 态）② 未登录跳转页（302→signin）③ 无权限页（article-abstract/Get access）
  ④ 风控页（Cloudflare "Just a moment..." / 挑战特征）。真实响应录制**脱敏**（无 cookie/token/个人信息）后入库
  （fixture 纪律）；magic-bytes 伪装 PDF（HTML 存 .pdf）另入文件验证器单测（04 §8）。
- **不对抗**（AC-0.2/AC-4.6）：CHALLENGE 一律 `Challenged`→BLOCKED+冷却，**无任何破解/绕过/重试尝试**；
  UA 不伪装浏览器裸抓闭源 PDF（04 §5——要么真浏览器上下文要么官方 API）。

> **AC 对应**：§11 = AC-4.6（风控即停 + 冷却 + 报告提示 + 无破解）、AC-4.3（no_entitlement 判定）、AC-0.2（无 CAPTCHA 求解）。

## 12. 测试与验收（AC-4.x 对账 + 各节测试判据汇总）

| 层 | 覆盖 | AC |
|---|---|---|
| 单元（离线） | URL 重写表（含边界域名，07 §8）；脱敏器新键正则（`insttoken` 明文注入→jsonl 无残留，§5）；AES-GCM 加解密 round-trip + AAD 绑定（§3.2）；keyring→文件密钥降级判定与警告（§3.3）；`CrawlerError.status_code` 默认 None + 带值（§6）；ChallengeDetector 四态（§11）；profiles.toml schema 校验（未知键拒绝，§3.4） | AC-0.4/0.5 |
| 集成（mock IdP，纯 httpx，进 CI） | login→state 加密保存→复用→过期检测→refresh 全周期（§9）；健康门 ≤20 篇内检出 EXPIRED→BLOCKED 无 401 轰炸；日配额达上限→BLOCKED（FetchLog 对账）；no_entitlement→unpaywall OA-fallback 产 OA asset；挑战页→BLOCKED(challenge)+冷却；logout 后 store 取证式无残留 | AC-4.2/4.3/4.4/4.5/4.6 |
| canary（离线） | 凭证注入后 openreview/auth_gated 行状态正确（§7）；无 session→SKIP 非 unhealthy | 检查单 #3 |
| 真实凭证 runbook（`tests/manual/`，records 留痕，不进 CI） | 每 provider：首登→healthcheck→取 1 篇→过期重登→logout 清理；**AC-4.1**：`auth login elsevier`（APIKey）→ JFE DOI 经 Article Retrieval API 得合法 PDF（魔数校验） | AC-4.1 |
| AC-0 系统性扫描 | git 全历史无 `*.enc`/`.filekey`/`profiles.toml`/cookie 形态（AC-0.3）；日志正则无未脱敏凭证（AC-0.4）；限速 ≤ 站点声明、robots 禁区不访问（AC-0.5） | AC-0.1~0.5 |

- **分层验收（D-018 先例）**：AC-4.2/4.5/4.6 **离线 mock 层即可判定 PASS**（不依赖真实凭证/浏览器）；
  AC-4.1 = 真实凭证"用户参与层"（runbook），离线 DoD 不阻塞于它。
- **覆盖率门禁**：auth 包解析/判定模块 ≥90%（对齐 adapter 解析器纪律）；`make check` 全绿方可合并。

## 13. 与既有冻结件的兼容性核对（实现期防漂移清单）

| 既有冻结件 | 本 Phase 触碰方式 | 兼容性 |
|---|---|---|
| `types.SessionHandle = Any` | 具体化为 frozen dataclass（§2.1） | **受控**（types.py:128 注释预留"Phase 4 具体化"）；`Any\|None`→`concrete\|None` 精化，adapter 零改动 |
| `SourceAdapter` 五方法协议（adapter.py） | `session` 形参类型精化，**方法签名不变** | ✅ 无新增方法 |
| `CrawlerError`（errors.py） | 加 `status_code=None` keyword-only（§6）+ `AuthRequired`/`Challenged` 子类（§2.4） | ✅ 纯附加，既有构造点零改动 |
| `HttpClient`（http.py 冻结签名） | `_error_for_status`/`_rate_limited` 内部带 `status_code`（§6）；`extra_headers` 复用（§3 携密 client） | ✅ 公开签名不变（沿 T6 post_json 纯附加先例） |
| `obslog._SENSITIVE_KEYS`（§5） | 追加键，复用既有正则分支 | ✅ 纯附加（沿 T5 email 先例） |
| pipeline `StageContext`/`runner`（stages.py/runner.py） | 新增默认关闭的字段 + `_stage_oa_fallback` + 健康门/配额/冷却运行态（§8） | ✅ 默认 False→Phase 1-3 venue 零行为变化 |
| `Config`（config.py） | 新增 `auth_daily_cap`/`auth_health_interval`/`auth_health_max_age_s`/`[auth].active_profile`（§4/§8） | ✅ 纯附加，均有保守默认 |
| canary.py 分类规则 | 零改动（§7 复用 NotImplementedError→SKIP） | ✅ |

## 14. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-23 | 初稿：07 §2 伪代码 → 实现级冻结签名（SessionHandle/AuthProvider/CredentialStore/异常）；04 §4/§5/§7 运行时协议 → pipeline 接线点（OA-fallback #12 / 健康门 / 日配额 / BLOCKED 冷却）；闭合检查单 #2（QJE fulltext_source，见 plan T4）/#3（canary 凭证注入）/#4（status_code）/#12（OA-fallback）；`cryptography` vs 标准库评估（结论：cryptography 作 `[auth]` extra）；mock IdP 纯 httpx vs Playwright 结论（结论：生命周期全纯 httpx 进 CI，Playwright 仅真实首登不进 CI） | 本次 W0 P0 扩写任务（controller 预裁决 §0） |

> **[待 controller 裁决 / 双评审]**：①`cryptography` 依赖引入（虽为 optional extra，仍是首个二进制依赖——是否需独立 ADR）；②`types.SessionHandle` 具体化虽有代码注释预留，是否需在 decision-log 追记为受控变更；③健康门阈值 N=20/15min、日配额默认 200、challenge 冷却 24h 的默认值确认（04 §4/§5 已给，本稿沿用）；④wiley 是否纳入本 Phase（R0 勘察后裁决，§0 条件件）。
