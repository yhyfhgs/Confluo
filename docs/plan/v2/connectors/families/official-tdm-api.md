---
title: 官方 TDM API 族规范（official_tdm_api）
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 官方 TDM API 族规范（official_tdm_api）

> 本文回答：用户本人的 key 或 token 调用出版商官方全文、TDM 与元数据 API 这一族怎么写：族专有接口、清单与配方字段、族一致性套件，以及 `elsevier_tdm`、`wiley_tdm`、`springer_nature_api` 三张卡片。结论：全族 `exec_side: user`、只实现 `RecipeProvider`；平台不登记部署级出版商 key，也不接收、转发用户 key，配方只含 `{user_secret:<name>}` 占位符，由扩展或 pc-agent 在本机解析；每用户限额取书面值与 08 护栏的最严；带 UA 标记（SN `TextDataMining`）或查询串密钥的配方只由 pc-agent 执行，Elsevier `insttoken` 永不进浏览器；产物一律 `per_user_only`，私有派生按来源门控。APS 全量 Harvest 的卡片在 site_special，本文只给指向。通用协议见[连接器接口契约](../contract.md)。

## 要点

1. **全族用户侧**：受限全文只在用户显式点击后单篇取回（HC-03、HC-32，[03 用户侧全文取回](../../03-sources-and-corpus-pipeline.md#用户侧全文取回)）；平台 worker 不加载本族清单（契约 [§5](../contract.md#5-执行模型)）。
2. **平台只签发不含凭证的候选**：`locate_fulltext` 只产 `tdm_api`（带 `recipe_ref`），`open_in_tab` 由平台候选排序恒附（契约 §5）；配方随 PolicyBundle 签名，过期只剩 `open_in_tab`。
3. **凭证只在端侧**：只在扩展选项页或 pc-agent 录入与测试，PWA 只显示条目名与状态（[08 执行位置与凭证](../../08-compliance-security-privacy.md#执行位置与凭证)、[U2](../connector-ui.md#u2-我的连接)）；禁止池化、轮换、多 key 叠加（HC-04、HC-10）。
4. **多窗口限额取最严**：Elsevier 10 rps 与 50,000 次/周，Wiley 3 篇/s 与 60 次/10 分钟，SN 100 次/分与 500 次/日（◐），再叠加护栏（6 s、200 次/日）。
5. **请求身份**：执行器 UA 诚实标识自身，只追加出版商要求的标记；扩展按设计不改写 UA（最小权限），SN 配方因此只由 pc-agent 执行。
6. **`insttoken` 不进浏览器**（Elsevier 要求只在服务端）：V3 只交付"本人 key + 机构 IP"，变体待确认（OT-Q2）。
7. **私有产物不进共享层**：即使 CC BY 也 `per_user_only`；不发第三方 LLM；Elsevier、Wiley、SN 的本地 LLM 派生默认关闭，待法务（08 LQ-06、OT-Q3）。
8. **状态码语义逐源声明**：如 Elsevier 429 + `QUOTA_EXCEEDED` → `budget_exhausted`，Wiley 403 → `no_entitlement`；每行配证据与合成 fixture，"未核"行实录前不生效，按契约 §7 默认从严。
9. **桥接期限（已统一）**：`elsevier_tdm`、`wiley_tdm` 的 v1_bridge 版只作 `replay_only` 对拍基准、V2 出口退役（执行器 V3 才有，赶不上"V2 出口前移植"）；配方 W3 直接写、V3 出口达 CL3（OT-Q1）。
10. **证据强弱不一**：Elsevier 一手齐全；Wiley 限速有官方客户端佐证，端点与头名为二手；SN 多为二手或未核，V3 前以维护者本人 key 合成检查补齐。

## 1 本族回答什么与适用边界

本族覆盖"出版商官方文档化的全文、TDM 或元数据 API + 用户本人凭证"的取回，即 03 候选排序的第 3 位（前为共享 OA、OA 外链，后为机构会话配方、链接解析器、在出版社打开）。执行默认在 pc-agent；key 存在扩展的端到端凭证库中且配方允许时，也可由扩展执行（[02 受限全文在用户侧取回](../../02-architecture.md#受限全文在用户侧取回)）。

| 相邻族 | 分界 |
|---|---|
| `crossref_delegated` | 这些出版商的元数据与最新论文全部经 Crossref 委托（平台侧）；本族不产共享层 `NormRecord` |
| `platform_family` | 用户本人会话 + 托管平台配方（候选序 4），见 [platform-family.md](platform-family.md#atypon_user)；`wiley` 两族并存时本族优先 |
| `aggregator_api` | NASA ADS、Lens、alphaXiv 等"用户 token 的元数据或检索 API"归 aggregator_api 用户侧连接器，不在本族 |
| `site_special` | `aps_harvest` 主族；其 OA 集由平台收割，全量 Harvest（须 token 与许可）若开通按本族规则执行，见 §5 |

不在本族：IEEE Xplore API（HC-27；`ieee_xplore_user` 已撤销，待拍板确认 `link_only`，墓碑见 [site-special](site-special.md#ieee_xplore_user)；全文只外链）；Scopus、Web of Science（排除类，可选的"用户自带 key"连接器不列入计划）；OUP、T&F、SAGE、Cambridge 无公开的用户 TDM API（T&F"专用 IP 通道"为二手说法），全文只经平台族配方或外链；IOP、ACS 的 TDM 须另签书面协议或付费（[https://ioppublishing.org/?p=149832, 2026-09-30]、[https://solutions.acs.org/solutions/text-and-data-mining/, 2026-09-30]）。

## 2 族专有接口

```python
# 设计伪代码 —— official_tdm_api 族专有接口；RecipeProvider、FulltextOption、FulltextRecipe 的通用约束见 ../contract.md §5、§11
@dataclass(frozen=True)
class RateWindow:
    limit: int
    per_s: int  # 1、60、600、86400、604800
    scope: Literal["key", "user", "ip"]  # 书面计量主体
    basis: str  # 证据 id；无证据写 "未核"

@dataclass(frozen=True)
class RateSpec:  # 多窗口；执行器取全部窗口与护栏的最严
    windows: list[RateWindow]
    min_interval_s: float  # ≥6（护栏）；Wiley 取 10
    daily_cap: int  # ≤200（护栏）；同一 provider 的元数据与全文调用合并计数

@dataclass(frozen=True)
class QuotaHeaderMap:  # 统一映射到端侧的 limit / remaining / reset
    limit: str | None
    remaining: str | None
    reset: str | None  # epoch 秒
    exhausted_marker: tuple[str, str] | None # ("X-ELS-Status", "QUOTA_EXCEEDED")
    retry_after: bool

@dataclass(frozen=True)
class IdentityRule:
    ua_marker: str | None  # 如 "TextDataMining"：追加到执行器自身诚实 UA 之后，不替换、不伪装
    executors: frozenset[Literal["pc_agent", "extension"]]  # 需要改 UA 的只能 pc_agent

@dataclass(frozen=True)
class UserSecretDecl:
    name: str  # "elsevier.api_key"
    header: str | None  # 携密头名；与 in_query 二选一
    in_query: str | None  # 查询参数名；配方须标 secret_in_query 并经评审
    allowed_host: str  # 字面量 HTTPS 主机
    executors: frozenset[Literal["pc_agent", "extension"]]
    browser_forbidden: bool  # True：扩展既不录入它、也拒绝加载引用它的配方；PWA 对任何凭证都没有录入入口（08）
    optional: bool

@dataclass(frozen=True)
class ArtifactPolicy:
    ownership: Literal["per_user_only"]  # 恒定（03：许可是 CC BY 也不进共享层）
    third_party_llm: Literal["forbidden"]  # 02：私有全文不发第三方 LLM（personal 本机三道闸除外）
    local_derivation: Literal["allowed", "off_pending_legal", "forbidden"]
    retention: Literal["user_controlled", "project_duration"]
    snippet_max_chars: int | None  # 只约束未来任何跨用户外发（HC-25）

class OfficialTdmApi(RecipeProvider):  # kind: recipe_provider；exec_side: user
    per_user_limits: RateSpec
    quota_headers: QuotaHeaderMap | None
    request_identity: IdentityRule
    user_secrets: list[UserSecretDecl]
    status_overrides: list[StatusOverride]   # 行形式同契约 §2 {status, error_class, reason, fact_ref, fixture}，另加 verified: bool；
                                             # status 可带"+头或体特征"；verified=false（"未核"）的行 CI 不加载（FS-OT-03）；
                                             # 契约 §2 的覆盖表按端点声明，本族按配方声明，属族内扩展；下文 YAML 为简写，"未核"注释即 verified=false
    artifact_policy: ArtifactPolicy
    def entitlement_recipe(self, v: VersionView) -> FulltextRecipe | None: ...  # 可选预检；只在本次显式取回中执行
    # locate_fulltext(v, ctx)：只产 tdm_api（带 recipe_ref）；open_in_tab 由平台候选排序恒附；无 plan()，平台不发请求

def receipt_status(ec: ErrorClass | None, handed_over: bool) -> ReceiptStatus:
    # 设计伪代码：端侧 error_class → 08 回执五类；challenge、no_entitlement 先于 handed_to_user
    # （on_challenge 恒为 stop_then_open_in_tab，先判 handed_over 会使 challenge 永不出现）
    if ec in ("challenge", "no_entitlement"):
        return ec
    if handed_over:
        return "handed_to_user"  # 无错误而转为可见标签页交给用户
    return "ok" if ec is None else "error"
```

**端侧重试纪律**：`challenge`、`auth_expired`、`no_entitlement`、`budget_exhausted` 不重试；`rate_limited` 不在本次意图内重试，按 reset 或 `Retry-After` 在端侧记冷却；`transient` 在意图有效期（≤5 分钟）内至多重试 1 次；`integrity` 按契约 §7 重下 1 次。跨主机重定向前一律剥离携密头，落到 `allowed_host` 以外即停（`config/undeclared_host`）。

**覆盖表生效条件**：`status_overrides` 每行须有证据（一手文档、v1 生产口径或本人凭证实录）与合成 fixture；标"未核"的行实录登记前不生效，按契约 §7 默认（不明 401/403 按 `challenge` 从严）。

## 3 清单与配方字段

本族没有 ConnectorInstance（每家一个 API 主机）。`registry/connectors/<connector_id>.yaml` 在契约通用字段之上补：`per_user_limits`、`quota_headers`、`request_identity`、`user_secrets[]`、`status_overrides`、`artifact_policy`、`recipes[{recipe_id, version, method: tdm_api, executors}]`；合规证据（条款、TDMRep、商用门控）只在 SourceSpec 的 fulltext 通道。

| 凭证名 | 用于 | 位置 | 允许执行器 | 浏览器禁用 | 证据 |
|---|---|---|---|---|---|
| `elsevier.api_key` | `X-ELS-APIKey` | 头（Elsevier 也接受 URL 参数，本族禁止） | pc_agent、extension | 否 | [https://dev.elsevier.com/tecdoc_api_authentication.html, 2026-09-30] |
| `elsevier.insttoken` | `X-ELS-Insttoken` | 头 | pc_agent | 是 | 同上（"can't appear in any browser side code"） |
| `wiley.tdm_token` | `Wiley-TDM-Client-Token` | 头 | pc_agent、extension | 否 | 头名 ◐二手；token 性质见 [https://github.com/WileyLabs/tdm-client, 2026-09-30] |
| `springer_nature.api_key` | `api_key` | 查询参数（`secret_in_query: true`，待评审） | pc_agent | 是（查询串密钥不进浏览器） | [https://github.com/springernature/springernature_api_client, 2026-09-30] |

**本族新增规则**：`secret_in_query` 的配方 `executors` 只能是 `{pc_agent}`，pc-agent 本地日志对查询串脱敏（免得密钥留在浏览器历史、扩展或代理日志里；OT-Q6）。

```yaml
# 设计伪代码 —— registry/connectors/springer_nature_api.yaml（节选，数值以卡片为准）
connector_id: springer_nature_api
kind: recipe_provider
family: official_tdm_api
exec_side: user
impl: mapper  # 配方是数据；Meta JSON → 私域题录的 mapper 随 pc-agent 签名发布（超出契约 §5，待拍板 OT-Q9）
serves: [springer_link, nature_portfolio]
per_user_limits:
  windows:
    - {limit: 100, per_s: 60, scope: key, basis: ev_sn_rate_limits_2026-09-30}  # ◐
    - {limit: 500, per_s: 86400, scope: key, basis: ev_sn_rate_limits_2026-09-30}  # ◐
    - {limit: 1, per_s: 1, scope: key, basis: ev_sn_tdm_page_2026-09-30}  # 直接下载
  min_interval_s: 6
  daily_cap: 200
request_identity: {ua_marker: TextDataMining, executors: [pc_agent]}  # 长稿口径，未复核
user_secrets:
  - {name: springer_nature.api_key, in_query: api_key, allowed_host: api.springernature.com,
     executors: [pc_agent], browser_forbidden: true, optional: false}
artifact_policy: {ownership: per_user_only, third_party_llm: forbidden,
                  local_derivation: off_pending_legal, retention: project_duration} # 前者见 OT-Q3，retention 待拍板 OT-Q5
```

## 4 族一致性套件

通用契约测试见[一致性规范 §3](../conformance-and-testing.md#3-通用契约测试cl1)，RecipeProvider 适用 CT-01、02、03、05、08、10、11、12（同一致性规范 §3）与配方 schema、解释器对抗测试。本族另加（全部离线，用户侧 fixture 一律手写合成，不录真实全文；rule_id 按一致性规范的 `FS-<族缩写>-NN` 记法记为 `FS-OT-01`…`FS-OT-10`；`OT-Q*` 是本文未决事项编号，不是规则）：

| id | 断言 |
|---|---|
| FS-OT-01 | 配方 schema：步骤封闭枚举、`additionalProperties: false`；占位符只在 `request.headers` 或已评审的 `secret_in_query` 参数中；`allowed_host` 为字面量 HTTPS 主机；`on_challenge` = `stop_then_open_in_tab` |
| FS-OT-02 | 限额取最严：执行器模拟器断言每个 `RateWindow` 与护栏组合下的间隔与计数不越界（含 Wiley 60 次/600 s；SN 元数据与全文合并计数） |
| FS-OT-03 | `status_overrides` 每行一个合成 fixture 与一条证据；标"未核"的候选行在实录登记前不加载；未覆盖状态按契约错误矩阵兜底（不明 401/403 按 `challenge` 从严） |
| FS-OT-04 | 身份：`ua_marker` 非空的配方只由 pc-agent 加载，扩展加载即拒；pc-agent UA = 自身诚实 UA + 标记，不含浏览器 UA 串 |
| FS-OT-05 | `browser_forbidden` 与 `secret_in_query`：扩展静态检查拒绝引用 `elsevier.insttoken` 或带查询串密钥的配方；PWA 构建产物中不存在任何凭证的录入入口（08） |
| FS-OT-06 | 零外泄：RetrievalIntent、回执、PolicyBundle、平台日志、fixture 扫描中不出现凭证值；跨主机重定向前剥离携密头 |
| FS-OT-07 | 私域：产物写入路径只在 usr 域或设备本地；共享层写入零命中（[05 数据流规则](../../05-data-platform.md#数据流规则)）；`local_derivation` 门控生效 |
| FS-OT-08 | 回执：五类状态映射；回执不含内容、凭证与出版商 URL；回执不进任何跨用户统计（08），平台侧无按配方版本聚合回执的代码路径 |
| FS-OT-09 | 配额头：`X-RateLimit-*`、`CR-TDM-Rate-Limit*`（◐）、`Retry-After` 解析；余量只在端侧显示，不上传 |
| FS-OT-10 | 一用户一 provider 一把 key：执行器不轮换、不叠加；平台 API 没有接收 key 的端点 |

## 5 连接器清单总表

| connector_id | 类型 | 服务来源 | 最高优先级 | 波次 | exec_side | 代码量级 | v1 复用 | 前置依赖 | CL 当前 → 目标 |
|---|---|---|---|---|---|---|---|---|---|
| [elsevier_tdm](#elsevier_tdm) | v1 桥接（建议直接写配方） | `elsevier_sd`（含 Cell Press） | v2-P0 ⚑COMM | W3u | user | declarative；粗估 1.5 人日（E 清单，未核） | v1 `elsevier_sd`：parse 172 行、entitlement 预检、限流经验、runbook | V3 pc-agent 与扩展；用户 key | — → CL3（V3 出口） |
| [wiley_tdm](#wiley_tdm) | v1 桥接（建议直接写配方） | `wiley` | v2-P0 ⚑COMM | W3u | user | declarative；1.5 人日 | v1 `wiley`：parse 92 行、双窗口限速 | V3；用户 TDM token | — → CL3（V3 出口） |
| [springer_nature_api](#springer_nature_api) | 新写 | `springer_link`（元数据 + 全文）、`nature_portfolio`（全文） | v2-P0 ⚑COMM | W3u | user（pc-agent） | mapper（配方 + Meta JSON → 私域题录，OT-Q9）；2 人日 | — | V3 pc-agent；用户 api_key；SN 条款证据补齐 | — → CL3（V3 出口） |
| `aps_harvest` | 主族 site_special | `aps` | v2-P0 ⚑LIC（仅全量） | 见 [site-special.md](site-special.md#aps_harvest) | platform（OA 集）；全量待定（OT-Q8） | 卡片在 site_special | — | ⚑LIC：全量许可取得前不签发 | 本族按需补卡 |

`aps_harvest` 全量通道要点（未开通，仅供参照）：`harvest.aps.org` 的 `/v2/journals/articles` 与 `/{id}/accepted_fulltext`，认证为 Bearer token、APS 授权 IP 段或 CHORUS token 头，分页严格跟随 `Link` 头，文档未写限速 [https://harvest.aps.org/docs/harvest-api, 2026-09-30]；期刊站由 Cloudflare 与 429/503 控速 [https://journals.aps.org/robots.txt, 2026-09-30]。若按 OT-Q8 走用户 token，以 `{user_secret:aps.harvest_token}` 放头中、`executors: [pc_agent]`，按 FS-OT-01…FS-OT-10 执行。

## 6 连接器卡片

### elsevier_tdm

**1 身份**：`elsevier_tdm`；族 `official_tdm_api`；`kind: recipe_provider`；`impl: declarative`；`contract_version: 1`；`connector_version: 1.0.0`（计划；0.x 已由 v1_bridge 版占用，移植即 MAJOR）；`lifecycle: active`（计划）；v1 来历：adapter `elsevier_sd`，去向 `user_side`、模式 `replay_only`（契约 §17 枚举，即 v1 代码只作离线对拍基准；[v1-bridge 记录](v1-bridge.md#6-连接器卡片)），v1_bridge 版 `sunset_by` V2 出口，配方 V3 出口达 CL3（OT-Q1）；本清单 `impl: declarative`，不带契约 §2 只属 `impl: v1_bridge` 的 `v1` 字段；CL 当前 —（尚无清单），目标 CL3（V3 出口）；owner、backup_owner 待指派（P0 两人）；服务 `elsevier_sd`，venue 范围是其名下期刊（venue 名录核心 42 行、登记 72 行，据 E 清单）；波次 W3。

**2 通道与操作**：

| Operation | metadata | latest | fulltext |
|---|---|---|---|
| `locate_fulltext` | — | — | user：`tdm_api`（本人 key）；平台恒附 `open_in_tab` |
| `probe` | 平台侧：文档页与条款哈希、TDMRep 策略哈希（只访问 dev.elsevier.com、www.elsevier.com） | | |
| 其余 | 不支持；元数据与最新经 crossref_delegated（前缀 10.1016）；ScienceDirect Search 不用 | | |

**3 上游接口事实**：

- **端点**：Article Retrieval `https://api.elsevier.com/content/article/doi/{DOI}` 与 `/content/article/pii/{PII}` [https://dev.elsevier.com/tecdoc_text_mining.html, 2026-09-30]；检索端点本族不用（旧 `/content/search/scidir` 每次 ≤200 条；Search v2 为 `PUT /content/search/sciencedirect`，`offset` ≤6000，`loadedAfter` 为 ISO 8601 [https://dev.elsevier.com/tecdoc_sdsearch_migration.html, 2026-09-30]）。
- **认证**：`X-ELS-APIKey`（头或 URL 参数）；全文权限按客户端 IP 是否属订阅机构判定，非订阅只给 `META_ABS`；同一 IP 多账户经 Authentication API 取 authtoken（2 小时过期）；`insttoken` 只给客户或代客户的合作方，须"kept secure server-side"、"can't appear in any browser side code"、只走 https；客户端应用另有 OAuth（条件未核）[https://dev.elsevier.com/tecdoc_api_authentication.html, 2026-09-30]。key 须为本人专用 [https://www.elsevier.com/about/policies-and-standards/text-and-data-mining/license, 2026-09-30]。
- **限额**：Article Retrieval 50,000 次/周、10 rps，TDM 专用 key 不限周配额；头 `X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset`（epoch 秒）；超配额与超速都返回 429，配额耗尽另带 `X-ELS-Status: QUOTA_EXCEEDED`；未见 `Retry-After`（未核）[https://dev.elsevier.com/api_key_settings.html, 2026-09-30]。
- **数据形态**：`Accept: text/xml`（全文 XML）或 `text/plain`；`view=FULL` 无权限时报错 [https://dev.elsevier.com/tecdoc_text_mining.html, 2026-09-30]。PDF 形态沿用长稿示例与 v1 的 `httpAccept` 参数（v1 设计 `elsevier-sd.md` 2026-07-23，本轮未复核）。
- **条款**：订阅机构研究人员非商用 TDM [https://www.elsevier.com/about/policies-and-standards/text-and-data-mining, 2026-09-30]；产出片段 ≤200 字符并附 DOI 链接；禁止"substantially or systematically reproduce, retain or redistribute"与商用 [https://www.elsevier.com/about/policies-and-standards/text-and-data-mining/license, 2026-09-30]。图书馆指南引述 Elsevier 服务条款"不得把内容与任何 AI 工具结合使用"（◐二手 [https://guides.lib.strath.ac.uk/copyrightandgen-ai/inputs, 2026-09-30]，原条款所在文件与适用范围未核）。
- **TDMRep**：ScienceDirect 响应头 `tdm-reservation: 1`、`tdm-policy: https://www.elsevier.com/tdm/tdmrep-policy.json` [https://www.sciencedirect.com/robots.txt, 2026-09-30]；策略对 `stm:eu-dsm-article3` 用途无 duty，其余用途须 `obtainConsent` [https://www.elsevier.com/tdm/tdmrep-policy.json, 2026-09-30]。
- **相对长稿**：限额无变化；新增配额头与 429 语义、TDMRep 内容；`www.sciencedirect.com/robots.txt` 对本轮 UA 返回 403 拦截页（长稿记为可读），可能因 UA 或出口而异（未核）。

**4 请求声明**：

```yaml
# 设计伪代码 —— elsevier.article_retrieval（在长稿 §12.4 示例 1 上按契约收紧）
recipe_id: elsevier.article_retrieval
version: 1
provider: elsevier_tdm
method: tdm_api
executors: [pc_agent, extension]
steps:
  - request:
      method: GET
      url: "https://api.elsevier.com/content/article/doi/{doi}"
      headers:
        X-ELS-APIKey: "{user_secret:elsevier.api_key}"
        Accept: "application/pdf"  # PDF 形态为 v1 口径、未核（一手只见 text/xml、text/plain）；用户可在 pc-agent 改为 text/xml
      allowed_host: api.elsevier.com
      redirects: same_host_only
  - expect: {content_types: [application/pdf], magic: "%PDF", min_bytes: 10240}
status_overrides:
  "429+X-ELS-Status=QUOTA_EXCEEDED": budget_exhausted  # 停到 X-RateLimit-Reset
  "429": rate_limited
  "401": auth_expired  # 未核：实录登记前不生效
  "403": auth_expired  # v1 口径（L15）为证据，待实录复核
  "200+META_ABS": no_entitlement  # 非订阅 IP 只给 META_ABS；体特征待实录
  "404": gone
limits: {min_interval_s: 6, daily_cap: 200}
on_challenge: stop_then_open_in_tab
```

- `endpoint_id`：`elsevier.article_retrieval`；`request_class`（端侧）`fulltext_single`；计量：每用户每 key。
- `hosts_touched`：端侧 `api.elsevier.com`；平台探针只到 `dev.elsevier.com`、`www.elsevier.com`（每页每周 1 次）；`budget`：无平台配额账户，端侧即 `per_user_limits`。
- `Expectation`：伪成功为"200 但只有摘要视图"→ `no_entitlement`；HTML 拦截页 → `challenge`（按共享特征库）；小于 10 KB → `integrity`。
- 变体 `elsevier.article_retrieval_insttoken`：多一个 `X-ELS-Insttoken: "{user_secret:elsevier.insttoken}"` 头，`executors: [pc_agent]`；V3 不发布，见未决 OT-Q2。

**5 游标与增量**：无游标：单篇显式取回，不做检索式增量（ScienceDirect Search 的 `loadedAfter` 不用）。重启语义由 RetrievalIntent 的一次性承担。周配额余量是端侧计数，不是游标。撤稿与更正走 Crossref（`update-to`、Crossmark）。`late_path: none`。

**6 映射**：

- 端侧产物：PDF 或全文 XML，存设备本地，可选端到端同步（D-054；密文存于平台是否满足 Elsevier 条款待 08 LQ-20）；XML 由 pc-agent 用 v1 `parse` 转成私有阅读格式。
- `FulltextOption.version_claim`：`{stage: vor, basis: "publisher_api"}`；`license`：取平台已知的 Crossref `license[]`；无论许可如何，产物 `per_user_only`。
- API 返回的摘要按 C 类（出版商 API 个人许可），只进本人私域（HC-08）。

**7 SCD**：只声明 `locate_fulltext`（`exec_side: user`）；不参与 04 的联邦检索与路由；批量上限 1。

**8 合规**：

- **策略输入**：文档化 API（用户级）；bulk 无；robots 不适用于用户显式单篇 API 调用（HC-29 的"本人浏览"口径），但 SourceSpec 仍记录 ScienceDirect robots 不可达；ToS：非商用 TDM 许可；TDM/AI：TDMRep `1`。
- **上限模式**：`locate_fulltext` 上限 `user_side`（结构性：exec_side=user）。
- **闸门**：⚑COMM——商用开关开启时配方随 PolicyBundle 撤回（D-045、HC-23 精神）。
- **共享边界**：Elsevier API 内容不进共享 LLM（HC-11）；任何未来的跨用户外发（如分享卡摘录）片段 ≤200 字符、附 DOI 链接与规定声明（HC-25）；`local_derivation: off_pending_legal`（◐ AI 条款，待拍板 OT-Q3）。
- **用途枚举**：`stm:eu-dsm-article3` 如何映射到 Confluo 的用途枚举（LQ-17）待法务。

**9 全文**：

- 候选：`tdm_api`（`recipe_ref: (elsevier.article_retrieval, 1)`）→ `open_in_tab`（`https://doi.org/{doi}`）。平台总是附上 `tdm_api` 候选（平台不知道、也不记录用户有没有 key）；端侧没有执行器或没有对应 key 时退到 `open_in_tab`，原因码 `needs_entitlement` 由端侧本地给出（"可用你的权限"只在端侧计算）。
- 护栏：串行、每域 ≥6 s、每日 ≤200 次尝试（成败都计）、挑战即停并冷却 24 h（[03 护栏](../../03-sources-and-corpus-pipeline.md#用户侧全文取回)）。
- 校园网外：权限按 IP 判定，会得到 `META_ABS` → `no_entitlement`，文案提示"在机构网络或 VPN 内重试"，不引导任何绕过。

**10 测试**：

- 手写合成 fixture：`elsevier.pdf_ok`、`elsevier.xml_ok`、`elsevier.meta_abs_only`、`elsevier.401_invalid_key`、`elsevier.403`、`elsevier.429_quota_exceeded`（带 `X-RateLimit-*` 与 `X-ELS-Status`）、`elsevier.429_rate`、`elsevier.html_block`、`elsevier.small_pdf`。
- 真实响应只录头与错误体：由维护者本人 key 做合成检查（契约待拍板 P-7），不存全文。
- 契约测试：FS-OT-01…FS-OT-10；黄金决策行：有 key 与无 key、⚑COMM 开关两种状态。

**11 探针与替补**：

- `ProbeSpec`（平台侧，只访问文档与条款主机）：`tos_hash`（TDM 许可页、TDM 政策页，每周）、`structure`（配额表页哈希，每周）、`tdmrep`（策略 JSON 哈希，每周）、`deprecation`（开发者门户迁移公告，每月）。
- 处置：条款哈希变化 7 天宽限并进复核；配额表变化只提示维护者更新 `per_user_limits`（只能更严）。
- 替补链：共享 OA（Cell 系等 CC 许可篇）→ OA 位置外链（OpenAlex、Unpaywall）→ `elsevier_tdm` → 机构链接解析器 → 在出版社打开。摘要另经 OpenAlex、PubMed 补齐（平台侧，与本连接器无关）。

**12 运维**：新鲜度不适用。用户侧回执不进任何跨用户统计（08），运维台不显示用户侧成功率；配方健康只来自维护者合成检查（契约 P-7，待 08 认可）与用户自愿提交的工单，确认失效由 owner 经 PR 撤下 `tdm_api` 候选、只留 `open_in_tab`；如需回执聚合须另立 ADR（待拍板）。端侧"本周余量"只在 pc-agent 或扩展里显示（U2）。`review_every`：月看健康、季复核卡片；维护点数 declarative 0.5（未核）。

**13 已知坑与待决**：

- v1 对"任意 429"当日熔断；v2 区分 `QUOTA_EXCEEDED`（停到 reset）与超速（端侧冷却）。
- 周配额 50,000 在 200 次/日护栏下不起作用；TDM 专用 key 与普通 key 对用户无差别。
- URL 参数传 key 本族禁止；AI 条款见 §8 与 OT-Q3，`insttoken` 与 pc-agent 是否相容见 OT-Q2。

### wiley_tdm

**1 身份**：`wiley_tdm`；族 `official_tdm_api`；`kind: recipe_provider`；`impl: declarative`；`contract_version: 1`；`connector_version: 1.0.0`（计划；0.x 已由 v1_bridge 版占用，移植即 MAJOR）；`lifecycle: active`（计划）；v1 来历：adapter `wiley`，去向 `user_side`，v1_bridge 版 `sunset_by` V2 出口、配方 V3 出口达 CL3（写法同 `elsevier_tdm`，清单不带 `v1` 字段；[v1-bridge 记录](v1-bridge.md#6-连接器卡片)）；CL 当前 —，目标 CL3（V3 出口）；owner、backup_owner 待指派；服务 `wiley`（含 Wiley-VCH 与学会子域）；波次 W3。

**2 通道与操作**：

| Operation | metadata | latest | fulltext |
|---|---|---|---|
| `locate_fulltext` | — | — | user：`tdm_api`（本人 token）；平台恒附 `open_in_tab`；页面兜底见 [atypon_user](platform-family.md#atypon_user)（当前不签发） |
| `probe` | 平台侧：WileyLabs 客户端 README 与 TDM 页可达性（TDM 页 403 时记 unknown） | | |
| 其余 | 不支持；元数据与最新经 crossref_delegated（前缀 10.1002、10.1111）；feed 经 feed 族 | | |

**3 上游接口事实**：

- **端点**：`https://api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}`，头 `Wiley-TDM-Client-Token`，只能按 DOI 取 PDF、不支持检索（◐二手：图书馆指南与第三方代码；v1 生产实现使用同一端点，v1 设计 `wiley.md` 2026-07-29）。官方 TDM 页对本轮请求 403，未直读 [https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining, 2026-09-30]。
- **认证**：TDM token 为 UUID，用 Wiley Online Library 账户在 TDM 资源页领取；权限按 IP 认证，"SSO-only accounts are not supported" [https://github.com/WileyLabs/tdm-client, 2026-09-30]；接受 click-through TDM 协议后发 token，学术订阅者可用 ORCID 登录（◐二手 [https://guides.lib.uw.edu/research/text-mining/data/api, 2026-09-30]）。
- **限额**："up to 3 articles per second"且"60 requests per 10 minutes"，客户端默认批间隔 5 s [https://github.com/WileyLabs/tdm-client, 2026-09-30]；过快返回 429（◐二手）。
- **条款**：非商用学术研究，受机构订阅约束（◐二手）；AI 用途条款未核。
- **相对长稿**：无变化；限速现有 Wiley 官方 GitHub 组织 README 佐证。

**4 请求声明**：

```yaml
# 设计伪代码 —— wiley.tdm_article
recipe_id: wiley.tdm_article
version: 1
provider: wiley_tdm
method: tdm_api
executors: [pc_agent, extension]
steps:
  - request:
      method: GET
      url: "https://api.wiley.com/onlinelibrary/tdm/v1/articles/{doi_urlencoded}"
      headers: {Wiley-TDM-Client-Token: "{user_secret:wiley.tdm_token}"}
      allowed_host: api.wiley.com
      redirects: same_host_only  # 若实录发现 PDF 经 CDN 跨主机下发，须评审后显式登记
  - expect: {content_types: [application/pdf], magic: "%PDF", min_bytes: 10240}
status_overrides: {"403": no_entitlement, "401": auth_expired, "429": rate_limited, "404": gone}  # 403 以 v1 口径为证据；401 未核，实录前不生效；429、404 同契约默认
limits: {min_interval_s: 10, daily_cap: 200}  # 60 次/600 s 持续速率约每 10 s 一次，比 6 s 护栏更严
on_challenge: stop_then_open_in_tab
```

`endpoint_id`：`wiley.tdm_article`；计量：每用户每 token；`hosts_touched`：端侧 `api.wiley.com`，平台侧探针只读 GitHub README 与 TDM 页；`budget` 同 `elsevier_tdm`（端侧 `per_user_limits`）；`Expectation` 伪成功为 200 HTML → `integrity`（或按共享特征库判 `challenge`）。

**5 游标与增量**：无游标；同 `elsevier_tdm`。API 没有列表接口，增量走 Crossref。

**6 映射**：端侧产物为 PDF，本地解析；`version_claim{stage: vor, basis: "publisher_api"}`；`per_user_only`。

**7 SCD**：只声明 `locate_fulltext`（user）；批量上限 1。

**8 合规**：

- 策略输入：文档化 API（用户级）；站点 robots（Atypon 模板、具名禁 GPTBot 与 Google-Extended）只影响 `atypon_user`，不影响本 API 调用；TDMRep 文件被 CF 挑战 → `unknown`（按保留处理，上限仍为 `user_side`）。
- 闸门：⚑COMM；商用开关开启时撤回配方。
- 私有派生：AI 条款未核、站点具名禁 GPTBot 与 Google-Extended（08："内容不作 LLM 输入"）→ `off_pending_legal`（OT-Q3）；第三方 LLM 一律不发。

**9 全文**：

- 候选：`tdm_api` → `open_in_tab`。纯 SSO 用户拿不到可用 token（只认 IP），U2 在录入时说明，候选退回 `open_in_tab` 与一键保存。
- 60 次/10 分钟意味着每用户每小时至多 360 篇，但护栏把单日限在 200 次；U5 显示排队与节流状态。

**10 测试**：

- 手写合成 fixture：`wiley.pdf_ok`、`wiley.403_no_entitlement`、`wiley.401_bad_token`、`wiley.429`、`wiley.html_200`、`wiley.small_pdf`。
- 真实状态码与错误体须以维护者本人 token 实录一次（F5 标"未核"的三类），只存头与错误体。
- 契约测试：FS-OT-01…FS-OT-10；FS-OT-02 覆盖 60 次/600 s 窗口。

**11 探针与替补**：

- `ProbeSpec`：`structure`（WileyLabs 客户端 README 哈希，每月）、`tos_hash`（TDM 页，403 时记 unknown，每周）、`deprecation`（README 与门户公告）。
- 替补链：共享 OA → OA 位置外链 → `wiley_tdm` → `atypon_user`（当前不签发）→ 机构链接解析器 → 在出版社打开。

**12 运维**：同 `elsevier_tdm`；token 由用户在 WOL 账户页自行轮换，端侧检测 401 后把 U2 状态置为 `needs_reauth`。

**13 已知坑与待决**：

- 端点与头名只有二手与 v1 实现佐证，官方页未直读。
- 只认 IP：校外须机构 VPN；纯 SSO 账户不支持。
- v1 以"5 / 3"保守近似双窗口；v2 直接声明两个窗口。

### springer_nature_api

**1 身份**：`springer_nature_api`；族 `official_tdm_api`；`kind: recipe_provider`；`impl: mapper`（配方是数据；Meta API JSON → 私域题录的 mapper 运行在 pc-agent 签名发布的代码中，带 `mapper_version`；比 declarative 高一级的理由即此映射）；`contract_version: 1`；`connector_version: 0.1.0`（计划）；`lifecycle: active`（计划）；新写，无 v1 前身；CL 当前 —，目标 CL3（V3 出口）；owner、backup_owner 待指派；服务 `springer_link`（元数据 + 全文）与 `nature_portfolio`（全文，同一连接器配置）；波次 W3。

**2 通道与操作**：

| Operation | metadata | latest | fulltext |
|---|---|---|---|
| `lookup`（端侧） | user：Meta API v2 按 DOI 取本人私域题录与摘要（C 类）；RecipeProvider 声明端侧 `lookup` 超出契约 §5，待拍板 OT-Q9，拍板前不发布 | — | — |
| `locate_fulltext` | — | — | user：OA API（OA 篇 JATS）、Full Text TDM API（订阅篇 JATS，须机构 TDM 协议）；平台恒附 `open_in_tab` |
| `probe` | 平台侧：门户限额页、TDMRep 与策略 JSON、条款页哈希 | | |
| 其余 | 不支持；平台侧元数据与最新经 crossref_delegated（前缀 10.1007、10.1057、10.1186 等）与 nature RSS（feed 族，只作信号） | | |

全部执行器为 pc-agent（带查询串密钥 + TDM 的 UA 标记）。

**3 上游接口事实**：

- **产品**：门户列 Full Text（TDM，订阅内容）、Meta、Open Access 三类 API [https://dev.springernature.com/, 2026-09-30]；支持文章另列旧 Metadata API 与 Integro API，写明 OA API 须经订阅门户注册，且"does not offer MCP-based access to our content or platforms for direct use in AI-assisted research workflows" [https://support.springernature.com/en/support/solutions/articles/6000195668-springerlink-api-details, 2026-09-30]。
- **端点与参数**：`https://api.springernature.com/meta/v2/json`、`/openaccess/json`（◐二手）；官方客户端参数 `q`、`s`（从 1 起）、`p`、`api_key`，TDM API 返回 JATS XML，`api_metric` 含义未核 [https://github.com/springernature/springernature_api_client, 2026-09-30]；`p` 上限、错误码、能否头传 key 未核（门户 JS 渲染）。
- **认证**：用户级 `api_key`，须同意 SN API Terms [https://dev.springernature.com/, 2026-09-30]；TDM API 对订阅机构另收费 [https://www.springernature.com/gp/researchers/text-and-data-mining, 2026-09-30]。
- **限额**：Meta、OA API 的 Basic 均为 100 次/分、500 次/日，Premium 分别为 300、200 次/分，均 10,000 次/日（◐二手 [https://dev.springernature.com/docs/rate-limit-details/rate-limits, 2026-09-30]）；直接下载 ≤1 次/s [https://www.springernature.com/gp/researchers/text-and-data-mining, 2026-09-30]；TDM API 150 次/分（长稿 2026-09-26，未复核）；超限状态码与头未核。
- **条款**：机构订阅附带非商用 TDM；存储须在"secure internal server without access for third parties and only for the duration of the TDM project"[同上]；禁多账号多 key 规避限额、TDM 请求 UA 须含 `TextDataMining`（长稿 2026-09-26/27，本轮未复核）。
- **TDMRep**：`link.springer.com` 与 `www.nature.com` 的 `tdmrep.json` 声明 `tdm-reservation: 1`，策略对两种用途都带 duty `obtainConsent` [https://link.springer.com/.well-known/tdmrep.json, 2026-09-30]、[https://dev.springernature.com/tdm/SNTDMPolicy.json, 2026-09-30]。
- **robots**：两站均具名禁 anthropic-ai、ClaudeBot、GPTBot、Google-Extended、CCBot 等 [https://link.springer.com/robots.txt, 2026-09-30]、[https://www.nature.com/robots.txt, 2026-09-30]——站点页面不做任何代发，只走 API 或 `open_in_tab`；`api.springernature.com` 的 robots 未核。
- **相对长稿**：Basic 限额无变化；新增 Premium 数值（二手）与"不提供 MCP 式接入"声明；UA 标记要求未复核。

**4 请求声明**：

```yaml
# 设计伪代码 —— 三个配方共用的约束（节选）
recipes:
  - recipe_id: springer_nature.meta_lookup  # metadata 通道，端侧 lookup
    steps:
      - request: {method: GET, url: "https://api.springernature.com/meta/v2/json",  # 端点 ◐二手；doi: 查询语法未核
                  params: {q: "doi:{doi}", api_key: "{user_secret:springer_nature.api_key}"},
                  secret_in_query: true, allowed_host: api.springernature.com}
      - expect: {content_types: [application/json], min_bytes: 200}
  - recipe_id: springer_nature.oa_jats  # OA 篇全文
    steps:
      - request: {method: GET, url: "https://api.springernature.com/openaccess/jats",  # 路径未核，以实录为准
                  params: {q: "doi:{doi}", api_key: "{user_secret:springer_nature.api_key}"},
                  secret_in_query: true, allowed_host: api.springernature.com}
      - expect: {content_types: [application/xml, text/xml], min_bytes: 1024}
  - recipe_id: springer_nature.tdm_fulltext  # 订阅篇全文（机构 TDM 协议）
    steps: [...]  # 端点未核；UA 标记必需
executors: [pc_agent]
request_identity: {ua_marker: TextDataMining}
status_overrides: {"401": auth_expired, "403": no_entitlement, "429": rate_limited}  # 候选行，全部未核；实录登记前 401/403 按契约默认 challenge
limits: {min_interval_s: 6, daily_cap: 200}  # 三个配方合并计数；日配额 500（◐）另由端侧计数兜底
on_challenge: stop_then_open_in_tab
```

`endpoint_id`：`springer_nature.meta_lookup`、`springer_nature.oa_jats`、`springer_nature.tdm_fulltext`；计量：每用户每 key；`hosts_touched`：端侧 `api.springernature.com`（TDM API 主机未核），平台侧探针只到门户、条款页与两站 `tdmrep.json`、robots；`budget` 同 `elsevier_tdm`；`Expectation` 伪成功：200 但 `result` 为空 → `gone`（DOI 不在 SN）或 `no_entitlement`（订阅篇），体特征待实录。

**5 游标与增量**：无游标。`onlinedatefrom`/`onlinedateto` 可做日期窗口（◐二手 [https://dev.springernature.com/adding-constraints, 2026-09-30]），但本族不做后台或检索式增量：日配额 500 次是硬约束，只服务用户显式请求的单篇。撤稿走 Crossref。

**6 映射**：

- `springer_nature.meta_lookup` 的 JSON 由 pc-agent 内的 mapper 转成本人私域题录（`mapper_version` 递增须附黄金差异）；摘要按 C 类，只进本人私域，不进共享索引、嵌入或共享 LLM（名录红线、HC-08）。
- OA JATS 虽多为 CC BY，经用户凭证取得的副本仍 `per_user_only`；共享层的 OA 副本只能由平台经公开通道（如 PMC、Europe PMC）自行取得。
- `version_claim{stage: vor, basis: "publisher_api"}`。

**7 SCD**：端侧 `lookup` 与 `locate_fulltext`；不进 04 路由（平台侧的 SN 元数据查找能力由 crossref_delegated 提供）。

**8 合规**：

- **策略输入**：文档化 API（用户级；R2-14：OA/Meta API 在条款书面确认前同样按用户级凭证处理，不登记部署级 key）；站点 robots 具名禁 AI UA → 站点页面上限 `link_only`（`open_in_tab` + 一键保存）；TDMRep 保留且要求 `obtainConsent`（任何用途）→ 全文 TDM 只在用户机构已签 SN TDM 协议时有意义，API 自身会拒绝无权限请求。
- **上限模式**：`user_side`。闸门 ⚑COMM。
- **保存期**：条款要求"只在 TDM 项目期间"保存于"secure internal server without access for third parties"；`retention: project_duration` 的产品含义（到期提醒还是自动删除）待拍板 OT-Q5；端到端密文同步是否满足该条款待 08 LQ-20，结论前 SN 产物不开同步。
- **私有派生**：`off_pending_legal`（TDMRep `obtainConsent`、具名 AI 禁令；OT-Q3）。
- **AI 工作流**：SN 声明不提供 MCP 式接入；Confluo 不是 MCP，但属法务输入（⚑COMM 复核时一并看）。

**9 全文**：

- 候选：OA 篇先 `oa_link`（平台 OA 定位链）→ `tdm_api`（`springer_nature.oa_jats` 或 `tdm_fulltext`）→ `open_in_tab`。
- 用户没有登记 pc-agent 时，候选只剩 `oa_link` 与 `open_in_tab`（原因码 `needs_entitlement`，U4 提示"安装本机代理后可用你的 SN key"）；有 pc-agent 但本机无 key 时由端侧退回同样结果。

**10 测试**：

- 手写合成 fixture：`sn.meta_ok`、`sn.meta_empty`、`sn.oa_jats_ok`、`sn.tdm_no_entitlement`、`sn.401`、`sn.429`、`sn.daily_quota`（体特征未核，按实录修正）。
- FS-OT-04、FS-OT-05：扩展加载任一 SN 配方即拒；pc-agent UA 带 `TextDataMining` 标记、不含浏览器串，本地日志对 `api_key` 脱敏。
- 私域题录 mapper 的黄金输出（OT-Q9 采纳后）覆盖有摘要、无摘要、多作者、章节类型；它不是共享层 NormRecord。

**11 探针与替补**：

- `ProbeSpec`（平台侧）：`structure`（限额文档页哈希，JS 渲染时记 unknown，每周）、`tdmrep`（两站 `tdmrep.json` 与 `SNTDMPolicy.json` 哈希，每周）、`tos_hash`（TDM 条款页、API Terms，每周）、`robots`（两站，每日；只作站点上限依据）。
- 替补链：共享 OA（经 PMC/Europe PMC 取得的 CC BY 副本）→ OA 位置外链 → `springer_nature_api` → 机构链接解析器 → 在出版社打开。

**12 运维**：同 `elsevier_tdm`；端侧日配额余量（500 次，◐）只在 pc-agent 显示。

**13 已知坑与待决**：

- 限额、端点路径、错误码多为二手或未核，本人 key 合成检查补齐前不达 CL2；`api_key` 是否支持头传未核，已按 `secret_in_query` 收紧到 pc-agent。
- UA 标记要求只见于长稿，须一手复核；即使只对 TDM API 要求，Meta/OA 配方也因查询串密钥留在 pc-agent。
- "项目期间保存"与私有文库的长期保存习惯冲突（OT-Q5）。

## 7 本族风险、坑与待决

| # | 风险或坑 | 处置 |
|---|---|---|
| 1 | 用户侧桥接赶不上"V2 出口前移植" | 桥接版只回放、V2 出口退役；W3 直接写配方，V3 出口达 CL3（OT-Q1、PF-Q5） |
| 2 | `insttoken` 须"只在服务端" | V3 只交付 key + 机构 IP（OT-Q2） |
| 3 | AI 条款、TDMRep 与具名 AI 禁令可能约束私域 LLM | 三家 `off_pending_legal`（OT-Q3） |
| 4 | SN 证据偏弱（门户 JS 渲染） | 本人 key 合成检查补齐前不达 CL2 |
| 5 | Wiley 只认 IP，纯 SSO 不可用 | U2 录入时说明；退回一键保存 |
| 6 | key 共享或多 key 叠加 | 端侧一 provider 一 key；平台无接收入口；U2 标"个人专用"（Elsevier 条款） |
| 7 | 查询串密钥泄漏（SN） | 只在 pc-agent；本地日志脱敏；回执不含 URL |
| 8 | 配额表、条款、TDMRep 变化 | 哈希探针；限额只改得更严；条款变化 7 天宽限 |

## 怎么验收

- **CL0**：三个清单、本卡、SourceSpec 证据齐全；lint 通过；第二人合规复核在 CL0 出口完成（重点：⚑COMM、`artifact_policy`、`user_secrets` 的执行器限制）。
- **CL1**：适用于 RecipeProvider 的 CT-01、02、03、05、08、10、11、12，配方 schema 与解释器对抗测试，FS-OT-01…FS-OT-10 全过；`status_overrides` 生效行都有证据与 fixture，候选行未加载。
- **CL2**：维护者本人凭证合成检查通过（口径待 08 认可，契约 P-7）：真实状态码与头与 `status_overrides` 一致、零凭证外泄、零白名单外主机；平台侧探针 staging 连续 ≥14 天全绿。
- **CL3（V3 出口）**：取回意图、配方与回执中没有凭证与内容；配方解释器对抗测试全拒；用户侧护栏成立；回执不进跨用户统计（[09 V3](../../09-roadmap-and-milestones.md#v3-多用户平台)、[08 HC](../../08-compliance-security-privacy.md#合规硬约束hc)）。

## 未决事项

- **OT-Q1**（已统一）：`elsevier_tdm`、`wiley_tdm` 不在生产经 v1_bridge 过渡：v1_bridge 版只作 `replay_only` 离线对拍基准，`sunset_by` 按契约 §17 取 V2 出口；同一 id 的配方在 W3 直接编写、V3 出口达 CL3（与 [PF-Q5](platform-family.md#未决事项)、[v1-bridge](v1-bridge.md#未决事项) 未决 7 一致）。卡片只在本文，v1-bridge §6.1 只列桥接期条款；其 §2.2 已把 v1 `API_CALL` 映射为 `tdm_api`（契约 §11）。
- **OT-Q2**：Elsevier `insttoken` 是否允许放在 pc-agent（用户本机算不算"server-side"），以及 OAuth 的接入条件，须向 Elsevier 确认。
- **OT-Q3**：Elsevier、Wiley、SN 的端侧本地 LLM 派生默认关闭，待法务（08 LQ-06）；审校按从严默认把 Wiley、SN 原稿的 `allowed` 改为 `off_pending_legal`，放行后逐家恢复。
- **OT-Q4**：回执 `error` 是否细分 `auth_expired`、`integrity`、`not_found`、`rate_limited`（长稿建议），属 08 字段，待拍板。
- **OT-Q5**：SN "项目期间保存"在产品上的含义（到期提醒、自动删除或只在 TDM 语料中生效）。
- **OT-Q6**：本族新增规则"`secret_in_query` 的配方只由 pc-agent 执行"，请契约评审确认后写入契约 §11。
- **OT-Q7**：pc-agent 的 UA 格式（名称、版本、说明页；是否附用户本人联系邮箱）须在 V3 前定稿。
- **OT-Q8**：APS 全量 Harvest 在 ⚑LIC 解除后走哪条路：main 03 把它列为部署方待取得的数据许可（平台侧），site-special 与本文按用户授权 token 预留（pc-agent）；两种读法待拍板，选后者时在本族补卡。
- **OT-Q9**：SN 端侧 `lookup`（Meta API → 私域题录）与 pc-agent 内 mapper 超出契约 §5 的 RecipeProvider 协议（只产 `FulltextRecipe`）；须契约评审决定扩展协议（与待拍板 P-13 `QueryRecipe` 一并定：契约 v1 不新增协议，用户侧元数据查询停在 CL0），或并入 V3"题录导入只进私域"流程；拍板前 `springer_nature.meta_lookup` 不发布，只交付两个全文配方。
- **OT-Q10**：卡片小节标签本文已统一为 `**1 身份**：` 形式（原 `#### 1 身份` 四级标题）；按[卡片模板](../connector-card-template.md)，V0 起以 `card render` 的输出为准。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–5.4、§12.3–12.6 候选排序、配方示例与执行者护栏、§14.1 v1 adapter 去向）；`git show v2-drafts:docs/plan/v2/08-compliance-security-privacy.md`（§5.1 用户侧取回流程与签名对象）；通用契约见[连接器接口契约](../contract.md)。
