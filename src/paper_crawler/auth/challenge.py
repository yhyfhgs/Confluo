"""`ChallengeDetector` 挑战页判定器（auth-framework §11；04 §7 特征库落地）。

**防御性判定器**：只做"命中特征 → 如实分类"，供 provider 的 fetch/probe 事后
判读——判定为 CHALLENGE 时上游一律 `Challenged` → BLOCKED + 平台冷却，**本模块
不含任何求解/绕过/重试逻辑**（AC-0.2/AC-4.6；AGENTS §6 红线）。

特征库数据驱动（模块内常量表，每特征注明出处）；判定优先级 = auth-framework
§11 特征表行序：CHALLENGE > LOGIN_REDIRECT > NO_ENTITLEMENT > OK（兜底——
正常页零特征命中即 OK，不误判）。仅适用页面型平台（OUP HTML 四类，B-M3）；
Elsevier JSON 封套不走本判定器（§11）。非页面态异常（5xx 等）由上游
`HttpClient` 冻结错误映射先行拦截（auth-framework §2.2/§6），不进本判定器。

真实脱敏 fixture（含 R0 [LIVE] 风控页）归 T4（oup-silverchair.md §8）；特征表
后续按 fixture 校准只增不改语义（数据表非冻结签名）。
"""

from collections.abc import Mapping
from enum import StrEnum


class ClassifyResult(StrEnum):
    OK = "ok"  # 已登录/有权全文页
    LOGIN_REDIRECT = "login_redirect"  # 未登录→signin（→ AUTH_EXPIRED）
    NO_ENTITLEMENT = "no_entitlement"  # 有登录无订阅（article-abstract 路由/Get access 面板）
    CHALLENGE = "challenge"  # 风控/CAPTCHA（→ Challenged）


# ---------------------------------------------------------------------------
# 特征库（auth-framework §11 特征表；比对一律小写化。每条注明出处）
# ---------------------------------------------------------------------------

# Cloudflare 质询响应头（名, 值）——值精确相等（小写化后）。
_CHALLENGE_HEADER_SIGNATURES: tuple[tuple[str, str], ...] = (
    # R0 勘察 [LIVE 2026-07-23] publisher-platforms-p4-recheck.md O2：OUP QJE 文章页
    # 403 `cf-mitigated: challenge`；acm-dl.md（07-22）同头；wiley.md §2 同判定。
    ("cf-mitigated", "challenge"),
)

# Cloudflare challenge 页 body 特征（子串，小写）。
_CHALLENGE_BODY_CLOUDFLARE_SIGNATURES: tuple[str, ...] = (
    # R0 O2 [LIVE 2026-07-23]："Just a moment…" 质询页 5604B（省略号变体一并覆盖，
    # 故不含结尾点号）。
    "just a moment",
    # R0 O2 [LIVE 2026-07-23]：质询页 body 含 `/cdn-cgi/challenge-platform/` 脚本路径。
    "/cdn-cgi/challenge-platform/",
)

# 验证码页特征（子串，小写）——检测即上报，绝不求解（AC-0.2）。
_CHALLENGE_BODY_CAPTCHA_SIGNATURES: tuple[str, ...] = (
    # 04 §7 风控挑战行 / auth-framework §11 特征表：CAPTCHA 页特征。
    "hcaptcha",
    "recaptcha",
)

# unusual-activity / 人机验证文案特征（子串，小写）。
_CHALLENGE_BODY_ACTIVITY_SIGNATURES: tuple[str, ...] = (
    # 04 §5 风控行为规范（"unusual activity" 提示）/ auth-framework §11。
    "unusual activity",
    # auth-framework §11 特征表：人机验证文案。
    "verify you are human",
)

_CHALLENGE_BODY_SIGNATURES: tuple[str, ...] = (
    _CHALLENGE_BODY_CLOUDFLARE_SIGNATURES
    + _CHALLENGE_BODY_CAPTCHA_SIGNATURES
    + _CHALLENGE_BODY_ACTIVITY_SIGNATURES
)

# 登录跳转：状态码 + 落点 URL 特征（子串，小写）。
_LOGIN_REDIRECT_STATUSES: frozenset[int] = frozenset({302})  # auth-framework §11（04 §7 302→login）
_LOGIN_URL_SIGNATURES: tuple[str, ...] = (
    # auth-framework §11；oup robots R0 复核含 `/Shibboleth.sso/` SP 端点（oup-silverchair.md §2）。
    "shibboleth.sso",
    # oup-silverchair.md §2/§7（302→signin；robots 禁 `/signin.aspx` 印证路由存在）。
    "/signin",
    # 04 §7 失败模式表（302→login 泛化登录路径）。
    "/login",
)

# 账号标识（body 子串，小写）——命中即"已带登录态"，否决 LOGIN_REDIRECT
# （auth-framework §11"且无账号标识"守卫；oup-silverchair.md §5 探针判定=含账号标识）。
# T4 校准（2026-07-23，兑现 T1a ⚠ 注释）：三串**经 oup 四件套 fixture ④（已登录全文页，
# Silverchair 登录态 header 含 `My Account` 按钮 + `My Account`/`Sign out` 菜单项）验证充分
# ——"sign out"/"my account" 为 Silverchair 登录态菜单强特征；"signed in as" 为通用兜底守卫
# （只增不改语义原则下保留，无害）。**未增删**：OUP 的 OK 正例主锚是全文节点
# （article-pdf/citation_pdf_url，`_FULLTEXT_BODY_SIGNATURES`），账号标识仅作 LOGIN_REDIRECT
# 否决的辅助守卫，故三串已足。fixture ③④ 为合成占位（无凭证的诚实现实），runbook 首登采
# 真实脱敏样本后可再核（oup-silverchair.md §7；表仍循"只增不改语义"）。
_ACCOUNT_IDENTITY_SIGNATURES: tuple[str, ...] = (
    "sign out",
    "signed in as",
    "my account",
)

# 无订阅权限：落点 URL / body 面板特征（子串，小写）。
_ABSTRACT_URL_SIGNATURES: tuple[str, ...] = (
    # oup-silverchair.md §2：无权时 302→`/article-abstract/` 路由（auth-framework §11）。
    "article-abstract",
)
_ACCESS_WALL_BODY_SIGNATURES: tuple[str, ...] = (
    # auth-framework §11 / oup-silverchair.md §3③："Get access"/"Purchase" 面板。
    "get access",
    "purchase",
)

# 全文/PDF 节点（body 子串，小写）——命中即"页面自带全文出口"，否决 NO_ENTITLEMENT
# 的面板分支（auth-framework §11"且无 PDF 链接"守卫）。
_FULLTEXT_BODY_SIGNATURES: tuple[str, ...] = (
    # oup-silverchair.md §2：PDF 链接路径 `/{code}/article-pdf/…`。
    "article-pdf",
    # oup-silverchair.md §3②：`<meta name="citation_pdf_url">` 全文页 meta（解析首选）。
    "citation_pdf_url",
)


class ChallengeDetector:
    """四态判定器（auth-framework §11 冻结规格）。

    provider fetch/probe 后调 `classify` → 由调用方映射为 `HealthStatus` /
    抛 `AuthRequired`/`Challenged` / 标 no_entitlement（§11）——本判定器纯分类、
    不抛错、不发请求、不含任何对抗逻辑。
    """

    def classify(
        self, *, status: int, headers: Mapping[str, str], final_url: str, body: bytes
    ) -> ClassifyResult:
        """按 §11 特征表行序判定（结构化 `status`，非文本嗅探；§6 对齐）。

        1. CHALLENGE：质询头 / Cloudflare 质询页 / 验证码 / unusual-activity 文案；
        2. LOGIN_REDIRECT：302 或落点命中登录路径，**且无账号标识**；
        3. NO_ENTITLEMENT：落点 article-abstract 路由，或 access 面板**且无 PDF 链接**；
        4. OK：兜底——零特征命中（含"status 200 + 账号标识 + 全文/PDF 节点"正例行）。
        """
        text = body.decode("utf-8", errors="replace").lower()
        url = final_url.lower()
        header_map = {
            name.strip().lower(): value.strip().lower() for name, value in headers.items()
        }

        if any(header_map.get(name) == value for name, value in _CHALLENGE_HEADER_SIGNATURES):
            return ClassifyResult.CHALLENGE
        if any(signature in text for signature in _CHALLENGE_BODY_SIGNATURES):
            return ClassifyResult.CHALLENGE

        has_account_identity = any(signature in text for signature in _ACCOUNT_IDENTITY_SIGNATURES)
        login_hit = status in _LOGIN_REDIRECT_STATUSES or any(
            signature in url for signature in _LOGIN_URL_SIGNATURES
        )
        if login_hit and not has_account_identity:
            return ClassifyResult.LOGIN_REDIRECT

        if any(signature in url for signature in _ABSTRACT_URL_SIGNATURES):
            return ClassifyResult.NO_ENTITLEMENT
        has_fulltext_node = any(signature in text for signature in _FULLTEXT_BODY_SIGNATURES)
        if (
            any(signature in text for signature in _ACCESS_WALL_BODY_SIGNATURES)
            and not has_fulltext_node
        ):
            return ClassifyResult.NO_ENTITLEMENT

        return ClassifyResult.OK


__all__ = ["ChallengeDetector", "ClassifyResult"]
