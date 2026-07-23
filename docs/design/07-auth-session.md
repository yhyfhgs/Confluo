---
title: 认证与会话管理
status: implemented
owner: fable5
updated: 2026-07-23
---

# 07 · 认证与会话管理

> 决策依据：D-006。配图：[diagrams/04-auth-flow.svg](../diagrams/04-auth-flow.svg)。
> 红线（AGENTS.md §6）：只用用户自有合法凭证；不对抗风控；凭证与 session 永不入 git。

## 1. 功能说明

为 auth_gated 模块提供统一的"获得并维持合法访问状态"的服务：
- 四种 AuthProvider 实现，覆盖 cookie session、EZProxy、机构 SSO、官方 API key；
- 首次登录**人在回路**（有头浏览器人工完成，含 MFA/DUO）；
- 之后 headless 复用持久化 session；过期自动检测、可静默续期则续期、不能则明确提示人工重登。

## 2. 核心抽象（设计伪代码）

```python
class AuthProvider(Protocol):
    provider_id: str                       # 'elsevier', 'ezproxy_myuniv', ...
    kind: Literal['cookie_session', 'ezproxy', 'sso_flow', 'api_key']

    def ensure_session(self, interactive: bool = False) -> SessionHandle:
        """返回可用会话；不可用且 interactive=False 时抛 AuthRequired。"""
    def health_check(self, s: SessionHandle) -> HealthStatus:   # OK|EXPIRED|CHALLENGED
    def refresh(self, s: SessionHandle) -> SessionHandle | None # 静默续期，不可则 None
    def invalidate(self, s: SessionHandle) -> None
    def rewrite_url(self, url: str) -> str                      # 默认恒等；EZProxy 重写

@dataclass
class SessionHandle:
    provider_id: str
    backend: Literal['httpx_cookies', 'playwright_state', 'bearer_token']
    payload_ref: str          # 指向加密存储的 storage_state / cookie jar / token
    established_at: datetime
    est_ttl: timedelta | None # 经验估计，仅用于主动提前 health_check
```

## 3. 四种 Provider 设计

### 3.1 CookieSessionProvider（出版社直接账号 / 校内已认证态）
- 首登：`crawler auth login <provider>` → 启动 **有头** Playwright persistent context → 打开该平台登录页 → 用户人工登录（含任何 MFA）→ 用户回车确认 → 系统访问"已登录探针 URL"验证 → 导出 `storage_state` 加密落盘。
- 复用：headless context 以 storage_state 启动；HTTP 直取型平台（Silverchair 系）另导出 cookie jar 给 httpx。
- 探针 URL：每平台在 adapter 文档声明（如 Silverchair 的 account 页；判定规则=不重定向到 login 且页面含账号标识）。

### 3.2 EZProxyProvider（校外经代理访问）
- 配置：机构 EZProxy base（`https://login.<univ>.edu/login?url=`）+ 域名重写表（`www.sciencedirect.com → www-sciencedirect-com.<proxy>` 泛化规则）。
- 首登：对任一目标 URL 走 login 入口 → 人工完成校方认证 → proxy cookie 持久化。
- `rewrite_url` 在 fetch 前统一调用——**adapter 不感知代理存在**（架构上代理是 L2 关注点）。

### 3.3 SSOFlowProvider（Shibboleth / OpenAthens）
- 首登：有头浏览器走出版社的 "Institutional login" → WAYF 选机构 → IdP 登录（MFA）→ 回跳出版社种 cookie → 保存 storage_state。
- 特性：出版社侧 cookie TTL 常为数小时~数天；IdP 侧可能更长。`refresh` 策略：headless 重放 "Institutional login" 入口，若 IdP session 尚存则无人工介入完成续期（**这是常见可静默续期的情形**）；IdP 也过期 → None → BLOCKED。

### 3.4 APIKeyProvider（Elsevier / Wiley TDM / CORE / S2 等）
- 密钥来自 OS keyring（首选）或加密配置；`ensure_session` 仅校验 key 存在与配额探测端点连通。
- 机构 token（Elsevier insttoken）同库管理。

## 4. 凭证与状态存储

```
~/.paper-crawler/
├── config.toml               # 非敏感配置（active_profile、路径）
├── auth/
│   ├── profiles.toml         # provider 定义（无密钥明文；引用 keyring 条目名）
│   └── state/                # 加密的 storage_state / cookie jar（0600 权限）
```

- 加密：OS keyring 存主密钥，状态文件 AES-GCM 加密；机器无 keyring 时降级为文件密钥+显式警告。
- 日志脱敏：URL 中 token/query 参数、Cookie 头一律 `***`；FetchLog 只存脱敏 URL。
- `crawler auth status`：各 provider 的 session 年龄、上次 health_check 结果、预计过期。

## 5. 运行时协议（与 pipeline 的接口）

1. fetch 批任务启动 → `ensure_session(interactive=False)`；无 session → 该批直接 BLOCKED(auth)（不半途而废）；
2. 批内按 design/04 §4 的节奏 health_check；EXPIRED → `refresh()` → 失败 → 批暂停 + BLOCKED；
3. CHALLENGED（风控）→ 不 refresh、不重试，BLOCKED(challenge) + 平台冷却（design/05 错误分类学）；
4. BLOCKED 的人工恢复：`crawler auth login <provider>`（重登）或 `crawler resume`（用户已在浏览器处理挑战后）。

## 6. 多机构 / 多账号（Profile）

`profiles.toml` 支持同一平台多条 provider 配置（`elsevier@campus`、`elsevier@ezproxy`）；`config.toml` 的 `active_profile` 映射表决定运行时选择；CLI `--profile` 临时覆盖。场景：在校用直连、离校切 EZProxy，无需改 VenueSpec。

## 7. 安全威胁模型（简）

| 威胁 | 缓解 |
|---|---|
| storage_state 泄漏（等价账号被盗） | 加密+0600；不入 git（.gitignore 双保险）；`auth logout` 彻底删除 |
| 日志泄漏 cookie/token | 统一脱敏层，测试断言日志无敏感模式 |
| 误用他人凭证 | 文档明确单用户假设；profiles 无共享机制 |
| 系统被用于绕过付费墙 | 无凭证即无闭源获取路径（架构性保证，非策略性） |

## 8. 测试与验收

- **单元**：URL 重写表（含边界域名）；脱敏器（正则集）；加密 round-trip。
- **集成（mock IdP）**：用本地假登录页模拟 login→state 保存→复用→过期→refresh 全生命周期（无真实凭证依赖，可 CI）。
- **手动 runbook**（真实凭证，testing/records 留痕）：每 provider 一份——首登、复用、拔线重连、过期重登、logout 清理。
- **验收**（AC-4.x 关联）：AC-4.1/4.2（见 design/04）；另 AC-4.5：`auth logout` 后磁盘无任何可恢复 session 残留（取证式检查清单）。

## 9. 修订注记（不改正文语义段）

- **2026-07-23（A-M3 / D-023）**：§4 "APIKeyProvider 密钥来自 OS keyring（首选）或加密配置" 的实现级落地采**两级凭证模型**（见 [D-023](../plan/decision-log.md) 附注 2 + [auth-framework.md §3.4](auth-framework.md)）：①**简单字符串密钥**（Elsevier `api_key`/`insttoken`、Wiley TDM `token`）走 `[auth.<platform>]` 明文 Config-slot（家目录 config、仓库外、0600、obslog 脱敏、env 覆盖），keyring 为**可选加固层**——这是对 Phase 2/3 既有惯例（`[auth.s2].api_key`/`[auth.openreview].token`）的诚实收敛，非本节语义推翻；②**有状态凭证**（storage_state/cookie jar）方走本节 §4 的 AES-GCM 加密存储。config 分层与敏感边界完整规范见 [design/10-config-layout.md](10-config-layout.md)（D-025）。本注记不改动上文任何设计段落。
