---
title: 平台族规范（platform_family）
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 平台族规范（platform_family）

> 本文回答：托管平台（Atypon、Silverchair、HighWire）与仓储软件（DSpace、EPrints、InvenioRDM、OJS）这两类"平台知识"在连接器体系里怎么落地：接口、实例字段、族一致性套件，以及 `atypon_user`、`silverchair_user`、`cambridge_core_user` 三张卡片（最后一张已撤销，待拍板确认 `link_only`）。结论：同一个族名下两半执行位置相反。托管平台只产用户侧 `FulltextRecipe`（`kind: recipe_provider`，W3，V3 出口达 CL3），平台侧对这些主机只读公开信号（AC-V1 冲突见 PF-Q2）；按 main 03 与 08 的具名 AI 规则，加上本族对 robots 不可达从严的口径（PF-Q10），目前 7 个 Atypon 实例都命中"具名 AI 规则覆盖全文路径"或 robots 不可达，`user_fetch` 一律不签发，实际只提供"在出版社打开 + 打开后一键保存"。仓储软件与 OJS 不单独立连接器，只给 `oai_pmh` 引擎提供实例模板与指纹，新端点走 SOP B 零代码。通用协议见[连接器接口契约](../contract.md)，本文只写其上的族专有部分。

## 要点

1. **两半、一个族名**：`hosted`（Atypon、Silverchair、HighWire）为 `exec_side: user`、不后台；`repository`（DSpace、EPrints、InvenioRDM、OJS）为 `exec_side: platform`、可后台，收割由 [oai_pmh](oai-pmh.md#oai_pmh) 执行（[03 九族](../../03-sources-and-corpus-pipeline.md#连接器九族与执行位置)）。
2. **托管平台只产配方**：`atypon_user`、`silverchair_user` 实现 `RecipeProvider`，没有 `plan()`，平台不向这些主机的全文路径发任何请求；元数据与最新论文一律经 [crossref_delegated](crossref-delegated.md#crossref_delegated)。
3. **具名 AI 规则按"UA × 路径"求值**，不是"站点有没有 AI 条目"：INFORMS 对 5 个 AI UA 只禁 `/doi/full/`、`/doi/pdf/`、`/doi/epdf/`，放行 `/doi/abs/`；`User-agent: 008`（Silverchair 模板）不是 AI UA，不触发。按路径求值只用于收紧；若站点的具名 AI 组只禁非全文路径，先按 08 的站点级口径从严（PF-Q3）。
4. **结论是逐实例的，不是逐族的**：同一 Atypon 族内，Wiley 禁 GPTBot 与 Google-Extended，Science 禁 6 个，T&F、AOM、SIAM、UChicago 只禁 GPTBot；族模块只共享解析器与指纹，合规结论逐实例进 SourceSpec。
5. **robots 不可达即全禁**（RFC 9309 unreachable：5xx、网络错误、被挑战、TLS 失败）：SAGE、Cambridge Core 属此类，只给外链与一键保存。平台侧这是 08 的既定处置；对 `user_fetch` 比 main 更严（main 把显式单篇视为本人浏览、不看 robots），沿用长稿 R16，待拍板 PF-Q10。
6. **平台迁移只触发复勘，不自动改配方**：指纹发现模板变化（ACS 的 robots 与 Silverchair 同模板、RSC 迁 Silverchair、Emerald 2025-07 迁 Silverchair）只开复勘工单。
7. **仓储软件是实例模板**：默认路径与实际实例常不一致（EconStor 用 DSpace 6 旧路径 `/oai/request`）；实例显式值覆盖族默认，并以 `Identify` 校验。
8. **待拍板与已统一**：AC-V1"平台出口访问用户侧全文主机为 0"须按路径而非主机定口径（PF-Q2）；`cambridge_core_user` 已撤销，待拍板确认 `link_only`、不建连接器（PF-Q6）；签发门对 robots 的从严口径（PF-Q10）。用户侧桥接（`silverchair_user` 等）已统一：v1_bridge 版只回放、V2 出口退役，配方 W3 直接写、V3 出口达 CL3（PF-Q5）。

## 1 本族回答什么与适用边界

**托管平台（hosted）**：出版商把期刊托管在同一套软件上，站点模板、robots 模板、URL 形态高度一致。本族把"DOI → 落地页 → PDF"的规则写成声明式配方，由用户的浏览器扩展（Companion Extension）或本机 pc-agent 在用户显式点击后单篇执行（[03 用户侧全文取回](../../03-sources-and-corpus-pipeline.md#用户侧全文取回)、[08 执行位置与凭证](../../08-compliance-security-privacy.md#执行位置与凭证)）。平台侧对这些主机只做三件事：探针读取 `/robots.txt`、`/.well-known/tdmrep.json` 与条款页哈希；判定并签发 RetrievalIntent 的候选项；向 `feed` 族提供"该实例 feed 路径是否被 robots 放行"的规则（父路径被禁的 eTOC 须显式 Allow）。第一、三件与 03"平台出口不访问出版商的受限全文主机"及 AC-V1 按主机的口径冲突，本文按"全文路径零请求"设计，待拍板 PF-Q2；不获采纳时探针与 feed 对这些主机一并停用。

**仓储软件（repository）**：机构仓储与 OJS 期刊站点暴露标准 OAI-PMH 端点。本族提供默认路径、分页、删除语义、token 寿命等默认值和平台指纹；`oai_pmh` 引擎按实例 YAML 执行，卡片在 [oai-pmh.md](oai-pmh.md#oai_pmh)。新增一个已支持软件的端点是 SOP B（≤30 分钟，[03 SOP](../../03-sources-and-corpus-pipeline.md#新增来源-sop-与成本目标)）。

| 相邻族 | 分界 |
|---|---|
| `crossref_delegated` | 托管平台来源的元数据、最新论文全部经 Crossref 委托；本族不产 `NormRecord` |
| `feed` | Atypon `/action/showFeed`、Wiley `/feed/{eissn}/most-recent`、T&F `/feed/rss/{code}`、Silverchair `/rss/site_*` 的执行与卡片在 [feed.md](feed.md#feed)；本族 `feed_rule()` 只回答放行与否 |
| `official_tdm_api` | 出版商官方 API + 用户本人 key 是候选序 3，本族配方（用户本人会话）是序 4；同一来源两族并存时（`wiley`）TDM API 优先，见 [wiley_tdm](official-tdm-api.md#wiley_tdm) |
| `oai_pmh` | 引擎与连接器卡片在 oai-pmh.md；本族只供模板与指纹 |
| `site_special` | 自有 API 或结构化页面的专站，平台侧执行 |
| `v1_bridge` | `silverchair_user` 源自 v1 `oup_silverchair`；完整卡片只在本文，[v1-bridge.md](v1-bridge.md) §6.1 只列桥接期条款（去向 `user_side`、模式 `replay_only`）并指向本卡 |

不在本族：自建平台出版商。Springer Nature 的用户侧走 `official_tdm_api`；IOP、ACS、IEEE 只取元数据、全文外链（HC-27；IOP 2026-07 T&DM 政策点名 agent 与自动化工作流须另签协议 [https://ioppublishing.org/?p=149832, 2026-09-30]）；Cambridge Core 见 §6 [cambridge_core_user](#cambridge_core_user)。

## 2 族专有接口

```python
# 设计伪代码 —— platform_family 族专有接口；通用协议（RecipeProvider、FulltextOption、FulltextRecipe、ProbeSpec）见 ../contract.md
FamilyId = Literal["atypon", "silverchair", "highwire", "dspace", "eprints", "invenio_rdm", "ojs"]

@dataclass(frozen=True)
class HostObservation:  # 探针产物，只含公开信号；请求由探针框架经网关发出，族模块不发请求
    host: str
    robots_state: Literal["ok", "unavailable", "unreachable"]  # RFC 9309：4xx=unavailable；5xx/网络/挑战/TLS=unreachable
    robots_sha256: str | None
    robots_groups: list[RobotsGroup]  # 解析后的 UA 组与 Allow/Disallow
    content_signal: str | None  # Cloudflare 托管 robots 的 Content-Signal 行（APS 注释线索）
    tdmrep: TdmRepSignal  # {file, header, meta, policy_url, reservation: 0|1|unknown}；挑战页也读头
    header_hints: dict[str, str]  # 只留白名单头（server、x-powered-by、cf-ray 是否存在）

@dataclass(frozen=True)
class FingerprintResult:
    family_id: FamilyId | Literal["self_hosted", "unknown"]
    score: float  # 0–1；低于阈值记 unknown
    evidence: list[str]  # 命中的特征 id（§3 特征表）
    template_rev: str | None

@dataclass(frozen=True)
class NamedAiRule:  # 进 SourceSpec 的 fulltext 通道证据，运行值在 ops
    ua: str  # 规范化小写产品标记，如 "gptbot"
    scope: Literal["all", "fulltext", "paths"]
    paths: list[str]  # scope=paths 时的 Disallow 模式

@dataclass(frozen=True)
class AiRuleVerdict:
    blocked: bool
    matched: list[NamedAiRule]
    basis: Literal["named_ua", "content_signal", "unreachable", "none"]
    ai_ua_list_version: str  # AI UA 名单是 PolicyBundle 数据，版本化

class PlatformFamilyModule(Protocol):
    family_id: FamilyId
    kind: Literal["hosted", "repository"]
    background_allowed: bool  # hosted=False；repository=True（仍逐实例过策略）
    fulltext_paths: list[str]  # 族级全文路径模式，实例可追加
    def fingerprint(self, obs: HostObservation) -> FingerprintResult: ...
    def oai_defaults(self, inst: ConnectorInstance) -> OaiInstance | None: ...  # 只 repository
    def feed_rule(self, inst: ConnectorInstance, obs: HostObservation) -> FeedRule | None: ...
    def landing_url(self, inst: ConnectorInstance, doi: str) -> str: ...  # open_in_tab 的目标

class HostedRecipeProvider(RecipeProvider):  # atypon_user / silverchair_user
    module: PlatformFamilyModule
    # locate_fulltext：只产 user_fetch（issue_gate() 为真时，带 recipe_ref）；open_in_tab 由平台候选排序恒附，
    #   本族只经 landing_url() 提供其目标（契约 §5：RecipeProvider 只产 tdm_api / user_fetch）
    # recipes()：每实例一份 FulltextRecipe，随 PolicyBundle 签名，绑定实例 site_hosts

def ai_rule(obs: HostObservation, path: str, ai_uas: AiUaList) -> AiRuleVerdict:
    # 设计伪代码：按 UA × 路径求值；RFC 9309 最长匹配，同长 Allow 优先
    if obs.robots_state == "unreachable":
        return AiRuleVerdict(True, [], "unreachable", ai_uas.version)
    groups = [] if obs.robots_state == "unavailable" else obs.robots_groups
    matched = []
    for ua in ai_uas.tokens:
        g = named_group(groups, ua)  # 只取具名组；落到 * 组不算"具名禁止"
        if g is not None and not allowed(g, path):
            matched.append(NamedAiRule(ua, scope_of(g, FULLTEXT_PATHS), disallows(g)))
    if matched:
        return AiRuleVerdict(True, matched, "named_ua", ai_uas.version)
    if content_signal_reserves_ai(obs.content_signal):  # 对 user_fetch 的效力待拍板（PF-Q1、LQ-17），默认从严
        return AiRuleVerdict(True, [], "content_signal", ai_uas.version)
    return AiRuleVerdict(False, [], "none", ai_uas.version)

def issue_gate(inst, v, verdict: ChannelVerdict, obs: HostObservation, ai_uas) -> bool:
    # 设计伪代码：签发 user_fetch 候选的门（08/02 的代发条件 + 长稿 R16 + 具名 AI + 证据完整）；任何一项不满足只给 open_in_tab
    # "用户已授权该域"由端侧执行器检查，不在平台门内
    pdf_path = inst.paths.pdf.format(doi=v.doi)
    return (verdict.mode_cap >= "user_side"
            and verdict.tos_automation in ("allowed", "silent")  # unknown 视为不满足
            and obs.robots_state != "unreachable"  # 下两行为长稿 R16 口径，比 main HC-29 更严
            and robots_allows_star(obs, pdf_path)  # （main 不对显式单篇看 robots），待拍板 PF-Q10
            and not ai_rule(obs, pdf_path, ai_uas).blocked  # LQ-19 有结论前从严
            and not verdict.cooling_down
            and verdict.evidence_fresh)
```

AI UA 名单（`ai_uas`）的初值取本轮实测 robots 中出现的具名 AI 标记：GPTBot、ChatGPT-User、OAI-SearchBot、ClaudeBot、Claude-Web、anthropic-ai、Google-Extended、GoogleOther、CCBot、PerplexityBot、Applebot-Extended、Bytespider、meta-externalagent、cohere-ai、Diffbot、Amazonbot（F5 §1.2 [https://link.springer.com/robots.txt, 2026-09-30]、[https://iopscience.iop.org/robots.txt, 2026-09-30]、[https://www.aeaweb.org/robots.txt, 2026-09-30]）。GoogleOther、Amazonbot 未必只用于 AI（未核），列入属从严，随 PF-Q4 复核。增删经 PR 与合规复核，随 PolicyBundle 版本发布。

## 3 实例与清单字段

**合规证据只在 SourceSpec**（[契约 §2](../contract.md#2-三层声明与-connectormanifest)）：本族给 SourceSpec 的 fulltext 通道补一个证据字段 `robots_named_ai[{host, ua, scope, paths}]`（F5 §1.2 的建议）与 `content_signal`；运行值由探针写 ops，经 `EffectiveStatus` 叠加，只能收紧。ConnectorInstance 只放技术知识。

```yaml
# 设计伪代码 —— registry/instances/atypon/informs_pubsonline.yaml（托管实例：只放技术知识）
instance_id: atypon/informs_pubsonline
family_id: atypon
serves: [informs_pubsonline]
site_hosts: [pubsonline.informs.org]
paths:
  landing: "/doi/{doi}"
  abstract: "/doi/abs/{doi}"
  pdf: "/doi/pdf/{doi}"  # user_fetch 目标（若签发）
  epdf: "/doi/epdf/{doi}"  # 阅读器页，永不作下载目标
fulltext_paths_extra: []
pdf_link: {selector_ref: atypon.pdf_link}  # entitlement_probe 用的受限选择器引用
feed: {path: "/action/showFeed?type=etoc&feed=rss&jc={code}"}  # 是否放行由 feed_rule() 按 robots 判
quirks: []  # 只能打开引擎已登记的旗标，每个旗标有 fixture
```

```yaml
# 设计伪代码 —— registry/instances/dspace/econstor.yaml（仓储实例：oai_defaults 之上的显式覆盖）
instance_id: dspace/econstor
family_id: dspace
serves: [econstor]
oai:
  base_url: https://www.econstor.eu/oai/request  # DSpace 6 旧路径，不套 7+ 默认 /server/oai/request
                                                 # [https://www.econstor.eu/oai/request?verb=Identify, 2026-09-30]
  metadata_prefix: dim  # oai_dc 缺 JEL；映射待录 fixture 后定
  granularity: second  # 取值同 OaiInstance.granularity
  deleted_record: transient
  page_size_hint: 100  # 族默认（xoai.xml），本实例未核
  token_ttl_s: null  # 未核
  reconcile: {every: P7D, via: self}  # deleted_record=transient 必填（oai-pmh ReconcilePolicy）
  quirks: []  # 旧路径已由 base_url 显式覆盖，不需旗标
```

**族默认值与指纹特征**（repository 默认值是建议，实例须以 `Identify` 校验）：

| family_id | kind | 默认 OAI 路径 | 页长 | deletedRecord（已见实例） | token | 指纹主特征 | 证据 |
|---|---|---|---|---|---|---|---|
| `atypon` | hosted | — | — | — | — | robots 禁 `/action`、`/rss`、`/doi/epdf/`，Allow `/action/showJournal`、`/action/showXml`，多为 `Crawl-delay: 1` | [https://onlinelibrary.wiley.com/robots.txt, 2026-09-30]；[https://www.tandfonline.com/robots.txt, 2026-09-30] |
| `silverchair` | hosted | — | — | — | — | `User-agent: 008` 全禁；`*` 禁 `/bin/`、`/searchresults.aspx`、`/DownloadFile/`、`/Shibboleth.sso/`；`cassette.axd` 规则 | [https://academic.oup.com/robots.txt, 2026-09-30]；[https://pubs.aip.org/robots.txt, 2026-09-30] |
| `highwire` | hosted | — | — | — | — | Drupal 标准 robots（禁 `/search/`、`/user/login`、`/admin/`），有 sitemap | [https://genome.cshlp.org/robots.txt, 2026-09-30] |
| `dspace` | repository | 7+：`/server/oai/request`；≤6：`/oai/request` | 100 | `transient`（EconStor、PsychArchives） | 未核 | `Identify` 与路径；Solr 索引导入后才可见，滞后未核 | [https://raw.githubusercontent.com/DSpace/DSpace/main/dspace/config/modules/oai.cfg, 2026-09-30]；[https://raw.githubusercontent.com/DSpace/DSpace/main/dspace/config/crosswalks/oai/xoai.xml, 2026-09-30] |
| `eprints` | repository | `/cgi/oai2`（长稿 2026-09-27，未复核） | 未核 | 未核 | 未核 | 未核 | [https://wiki.eprints.org/w/OAI, 2026-09-30]（未给技术细节） |
| `invenio_rdm` | repository | `/oai2d` | 实例可调（Zenodo 50） | `no`（须 `ListIdentifiers` 对账） | 默认 1 分钟，过期 422 | `oai_datacite` 格式、`X-RateLimit-*` 头 | [https://inveniordm.docs.cern.ch/reference/oai_pmh/, 2026-09-30] |
| `ojs` | repository | `/index.php/<journal>/oai` | 100（`oai_max_records`） | `persistent`（AAAI）、`no`（TE [https://econtheory.org/ojs/index.php/te/oai?verb=Identify, 2026-09-30]） | 未核 | `Identify` 的 PKP toolkit 版本；set 为栏目 id、逐年变化 | [https://raw.githubusercontent.com/pkp/ojs/main/config.TEMPLATE.inc.php, 2026-09-30]；[https://ojs.aaai.org/index.php/AAAI/oai?verb=Identify, 2026-09-30] |

**ConnectorManifest 的族特有字段**（托管 RecipeProvider）：`kind: recipe_provider`、`exec_side: user`、`impl: declarative`（配方是数据；实例 `impl: instance`）、`recipes[{recipe_id, version, method: user_fetch, applies_to, executors: [extension|pc_agent], limits}]`、`ai_ua_list_ref`、`fingerprint_features_ref`。v1 来历（`silverchair_user` 源自 `oup_silverchair`）只记在卡片 §1 与 [v1-bridge](v1-bridge.md)：契约 §2 的 `v1{adapter, destiny, sunset_by}` 只属 `impl: v1_bridge` 清单；PF-Q5 不获采纳、保留桥接期时，同一 `connector_id` 的清单在桥接期取 `impl: v1_bridge` 并带该字段，移植后改为 `declarative`。仓储模块不出清单，差异按 `oai_pmh` 的 `OaiInstance` 字段表达：旧 DSpace 路径用 `base_url`，在场对账用 `reconcile`，InvenioRDM 422 用端点覆盖表（判定者待 W0 定）；OJS set 名轮换与 Zenodo 200 响应带 `retry-after: 60`（[https://zenodo.org/oai2d?verb=Identify, 2026-09-30]，见 F2）拟作新 `OaiQuirk` 旗标，须在 oai-pmh 族登记并配 fixture，列入未决。

## 4 族一致性套件

通用契约测试见 [一致性规范 §3](../conformance-and-testing.md#3-通用契约测试cl1)：托管 RecipeProvider 适用 CT-03、05、08、10、12，仓储实例随 `oai_pmh` 引擎跑全部 CT-01…CT-12；套件参数化方式见 [§5](../conformance-and-testing.md#5-族一致性套件)。本族另加（rule_id 按一致性规范的 `FS-<族缩写>-NN` 记法，以 H、R 区分托管与仓储两半：`FS-PF-H1`…`H7`、`FS-PF-R1`…`R5`；`PF-Q*` 是本文未决事项编号，不是规则）：

| id | 适用 | 断言 |
|---|---|---|
| FS-PF-H1 | hosted | 配方 schema：步骤封闭枚举、`additionalProperties: false`；托管配方**不得出现** `{user_secret:*}`（只用用户会话）；`allowed_hosts` 为字面量 HTTPS 主机且 ⊆ `doi.org` ∪ 实例 `site_hosts`；`on_challenge` = `stop_then_open_in_tab`；`limits` 不宽于 6 s / 200 次与来源书面值 |
| FS-PF-H2 | hosted | 签发门黄金决策表：7 个 Atypon、5 个 Silverchair 实例的当前快照逐行给出候选集；任一输入变严，候选集不增（单调性属性测试） |
| FS-PF-H3 | hosted | AI 规则 UA × 路径矩阵：Wiley（GPTBot、Google-Extended 全禁）、INFORMS（5 个 AI UA 只禁全文路径，`/doi/abs/` 放行）、Science（6 个）、OUP（只有 `008`，不触发）、robots 5xx/挑战（含 403 挑战页）/TLS 失败（unreachable → 全禁）、robots 非挑战的 4xx 如 404（unavailable → 无具名规则；Content-Signal 在 robots.txt 内，随之缺失，TDMRep 照常读） |
| FS-PF-H4 | hosted | 指纹：每族 ≥2 份真实 robots 模板 + 1 份反例（Springer 自建、IOP 自建）；模板变化只产 `platform_migration_suspected` 工单，不改配方、不改实例清单 |
| FS-PF-H5 | hosted | 用户侧四类手写合成 fixture（[一致性规范 fixture 政策](../conformance-and-testing.md#4-fixture-政策)）：成功（`%PDF`、≥10 KB）、无权限（登录或购买页 → `no_entitlement`）、会话过期（跳 SSO → `auth_expired`）、挑战（CF "Just a moment..." → `challenge`，终止、冷却 24 h、转 `open_in_tab`）；另加 PDF 路径回 HTML（`integrity`）与 epdf 阅读器页 |
| FS-PF-H6 | hosted | 平台出口零接触全文路径：网关审计回放中，`site_hosts` 上除 `/robots.txt`、`/.well-known/tdmrep.json`、登记的条款页与 feed 族登记且 robots 求值放行的 feed 路径外零请求 |
| FS-PF-H7 | hosted | `feed_rule()` 对父路径被禁的 eTOC（`/action/showFeed`）只在 robots 显式 Allow 时返回规则（PNAS、Science、SIAM 返回；INFORMS 返回 None）；未被禁的 feed 路径（Wiley `/feed/`、T&F `/feed/rss/`）按求值放行（与 [feed](feed.md#feed) 的 R15 解释一致） |
| FS-PF-R1 | repository | 每实例录 `Identify`、`ListMetadataFormats`、`ListSets`、一页 `ListRecords`、一页带 token 续页、一条 deleted 头（若有）、一个错误响应（F2 §6 最小集） |
| FS-PF-R2 | repository | 实例值覆盖族默认；`granularity`、`deletedRecord`、`earliestDatestamp` 与 `Identify` 不符即 `config` 失败 |
| FS-PF-R3 | repository | InvenioRDM 422（判定者待 W0 定）与 `badResumptionToken` 均归 `cursor_expired`，从本次运行窗口起点重启 ≤2 次 |
| FS-PF-R4 | repository | 删除：`persistent` 直接产 tombstone；`transient`、`no` 经周期 `ListIdentifiers` 对账产 tombstone（属性测试） |
| FS-PF-R5 | repository | `X-RateLimit-*` 只作令牌桶输入，不判错误；200 上的 `retry-after`（Zenodo）忽略，`Retry-After` 只在 429/503 上生效（F2） |

## 5 连接器清单总表

| connector_id / 模块 | 类型 | 服务来源 | 最高优先级 | 波次 | exec_side | 代码量级 | v1 复用 | 前置依赖 | CL 当前 → 目标 |
|---|---|---|---|---|---|---|---|---|---|
| [atypon_user](#atypon_user) | 族核心 RecipeProvider | 7：`wiley`、`tandf_online`、`sage_journals`、`uchicago_journals`、`siam`、`informs_pubsonline`、`aom_journals` | v2-P0 | W3u | user | declarative + 7 实例；粗估 2 人日（E 清单，未核） | `ChallengeDetector` 特征库；v1 wiley 页面兜底知识 | V3 扩展与 pc-agent；LQ-19 | — → CL3（V3 出口） |
| [silverchair_user](#silverchair_user) | 桥接 → RecipeProvider | 5：`oup_academic`、`aip`、`aaa_pubs`、`geoscienceworld`、`misq` | v2-P0 | W3u+W4u | user | declarative + 5 实例；1.5 人日 | v1 `oup_silverchair`：parse 123 行、四态判定、`CookieSession`/`SSOFlow`（入 pc-agent） | V3 | — → CL3（V3 出口） |
| [cambridge_core_user](#cambridge_core_user) | RecipeProvider（撤销；由 site_special 移入） | 1：`cambridge_core` | v2-P1 | 撤销（待拍板确认 link_only） | user | — | — | 待拍板 PF-Q6 | — → 不建 |
| `highwire` 模块 | 族模块（只指纹） | 0（`cshl_press` 全文经 PMC） | — | — | — | 指纹特征 | — | — | 按需补卡 |
| `dspace` 模块 | 实例模板 | `econstor`、`psycharchives` | 随实例 | 随 oai_pmh | platform | instance（SOP B） | v1 `_oai.py` | oai_pmh 引擎（W1） | 随实例，卡片在 [oai-pmh.md](oai-pmh.md#oai_pmh) |
| `invenio_rdm` 模块 | 实例模板 | `zenodo` | 随实例 | 随 oai_pmh | platform | instance | — | 同上 | 同上 |
| `ojs` 模块 | 实例模板 | `aaai_ojs`（经 `aaai_ojs_oai`）、`econsoc_journals`（TE/QE）、`iacr_eprint` 旗下 ToSC/TCHES | 随实例 | 随 oai_pmh | platform | instance | v1 `aaai_ojs` 的 `quirks.volume_map` → `editions.explicit` | 同上 | 同上 |
| `eprints` 模块 | 实例模板 | 0（MPRA 的 `/cgi/` 在 robots 禁区，只经 RePEc） | — | — | platform | 按需补卡 | — | EPrints 行为未核 | 按需补卡 |

## 6 连接器卡片

### atypon_user

**1 身份**：`atypon_user`；族 `platform_family`（`family_id: atypon`）；`kind: recipe_provider`；`impl: declarative`（族配方），7 个实例 `impl: instance`；`contract_version: 1`；`connector_version: 0.1.0`（计划）；`lifecycle: active`（计划）；CL 当前 —（尚无清单，本卡是 CL0 材料之一），目标 CL3（V3 出口，P0 用户侧通道）；owner、backup_owner 待指派（P0 须两人）；服务 7 个来源，venue 范围是这些来源在 venue 名录里的全部期刊（元数据由 crossref_delegated 按 ISSN 负责）；波次 W3。

**2 通道与操作**：

| Operation | metadata | latest | fulltext |
|---|---|---|---|
| `locate_fulltext` | — | — | user：`user_fetch` 只在签发门为真时产；`open_in_tab` 由平台恒附（目标取 `landing_url()`） |
| `probe` | 平台侧：robots、tdmrep、ToS 哈希、指纹（只读公开信号路径） | | |
| 其余 | 不支持：元数据与最新经 crossref_delegated，feed 经 feed 族 | | |

**3 上游接口事实**：

| 实例 | 主机 | robots 要点 | 具名 AI（UA × 范围） | TDMRep | ToS / TDM |
|---|---|---|---|---|---|
| `wiley` | onlinelibrary.wiley.com | `Crawl-delay: 1`；禁 `/action`、`/rss`、`/doi/epdf/` [https://onlinelibrary.wiley.com/robots.txt, 2026-09-30] | GPTBot、Google-Extended：all | CF 挑战 → unknown [https://onlinelibrary.wiley.com/.well-known/tdmrep.json, 2026-09-30] | 非商用学术 TDM（◐二手 [https://guides.lib.uw.edu/research/text-mining/data/api, 2026-09-30]）；官方 TDM 页 403 未直读 |
| `tandf_online` | www.tandfonline.com | `Crawl-delay: 1`；禁 `/action`、`/rss`、`/doi/epdf/*` [https://www.tandfonline.com/robots.txt, 2026-09-30] | GPTBot：all | CF 挑战 → unknown [https://www.tandfonline.com/.well-known/tdmrep.json, 2026-09-30] | 订阅者非商用 TDM 免费，建议先联系 [https://taylorandfrancis.com/our-policies/textanddatamining/, 2026-09-30] |
| `sage_journals` | journals.sagepub.com | TLS 失败两次 → unreachable [https://journals.sagepub.com/robots.txt, 2026-09-30] | 不可读 | 未核 | 非商用 TDM 免许可；"any AI uses including generative AI" 须许可 [https://www.sagepub.com/tdm-ai-policy, 2026-09-30]；按 PT 时段限速（◐二手） |
| `uchicago_journals` | www.journals.uchicago.edu | Atypon 模板，`Crawl-delay: 1` [https://www.journals.uchicago.edu/robots.txt, 2026-09-30] | GPTBot：all | 未核 | 批量下载需事先许可（长稿 2026-09-27，未复核） |
| `siam` | epubs.siam.org | 显式 `Allow: /action/showFeed` [https://epubs.siam.org/robots.txt, 2026-09-30] | GPTBot：all | 未核 | TDM 不被许可（长稿 ◐，未复核） |
| `informs_pubsonline` | pubsonline.informs.org | 禁 `/action`、`/rss`，`Crawl-delay: 1` [https://pubsonline.informs.org/robots.txt, 2026-09-30] | GPTBot、ChatGPT-User、Google-Extended、PerplexityBot、anthropic-ai：fulltext（`/doi/full/`、`/doi/pdf/`、`/doi/epdf/`），放行 `/doi/abs/` | 未核 | T&C 禁机器人下载、离线浏览 ≤20 页/分（长稿 ◐，未复核） |
| `aom_journals` | journals.aom.org | Atypon 模板，`Crawl-delay: 1` [https://journals.aom.org/robots.txt, 2026-09-30] | GPTBot：all | 未核 | 未核 |

- **认证**：用户本人浏览器会话（校园 IP、EZproxy、SSO）；无 key。登录永远由用户本人在出版方页面完成。
- **限速**：无文档化的用户侧数值；`Crawl-delay: 1` 针对爬虫；用户侧取护栏 6 s、200 次/日。
- **分页、增量、bulk**：不适用（单篇）。
- **当前结论**：7 个实例全部命中"具名 AI 规则覆盖 `/doi/pdf/`"或 robots 不可达，`user_fetch` 一律不签发，只有 `open_in_tab` 与打开后一键保存（`tab_save`，扩展的用户在场动作，不是 `FulltextOption.kind`）。与长稿一致（长稿 §12.3"Atypon 主机上的选项 4 多半不签发"）。

**4 请求声明**：

- **平台侧**：RecipeProvider 没有 `RequestSpec`。探针请求由 `ProbeSpec` 声明，`endpoint_id` 形如 `atypon.robots@<host>`、`atypon.tdmrep@<host>`；令牌桶五元组中来源为服务的 `source_id`、请求类 `probe`、凭证为部署 UA 身份（无 key）；`hosts_touched` = 实例 `site_hosts`，路径只限 `/robots.txt`、`/.well-known/tdmrep.json` 与登记的条款页（口径见未决 PF-Q2）；`budget`：每主机 robots 每日 1 次、tdmrep 与条款页每周各 1 次（单日峰值 ≤3 次）。
- **用户侧配方**：`allowed_hosts: [doi.org, {instance.site_host}]`；`Expectation{content_types: [application/pdf], magic: "%PDF", min_bytes: 10240, fake_success: [(登录页特征, no_entitlement), (CF 挑战特征, challenge), (其他 HTML, integrity)]}`；`limits{min_interval_s: 6, daily_cap: 200}`，日上限计数键见契约待拍板 P-6，本族建议按"用户 × `family_id`"计（一个平台多个域时更严）。

**5 游标与增量**：无游标：单篇 `locate_fulltext`。重启语义由 RetrievalIntent 承担（签名、≤5 分钟、同一 `intent_id` 只执行一次）。删除、撤稿、更正走 crossref_delegated 的 `status_claims`。`late_path: none`；`window_max`、`migrate_cursor` 不适用。

**6 映射**：不产共享层 `NormRecord`。`FulltextOption.version_claim` 取 `{stage: vor, basis: "publisher_site"}`；`license` 取 Crossref `license[]`（多为 `publisher_copyright`），用户侧取得的副本一律 `per_user_only`，与许可无关（03、HC-01）。回执只含五类状态与配方版本。

**7 SCD**：只声明 `locate_fulltext`（`exec_side: user`）；无 `search`、`enumerate`、`lookup`；每次取回 1–3 个请求（resolve、可选 entitlement_probe、download）；批量上限 1；不参与 04 的联邦路由。

**8 合规**：

- **策略输入**：文档化 API 无；bulk 无；robots 逐主机（含具名 AI 组）；ToS 自动化逐实例（INFORMS 禁机器人下载 → `forbidden`；其余多为未核 → `unknown`，签发门视为不满足）；TDM/AI：TDMRep 被挑战记 `unknown`，按保留处理。
- **上限模式**：`locate_fulltext` 上限 `user_side`；`user_fetch` 还须 R16 与签发门；具名 AI 覆盖全文路径的实例只给 `open_in_tab` + `tab_save`（[08 robots 与 ToS 统一政策](../../08-compliance-security-privacy.md#robots-与-tos-统一政策)，LQ-19 前）。
- **闸门**：⚑COMM（`wiley`、`tandf_online`、`sage_journals`），⚑RECHECK（`sage_journals`）；商用开关开启时 ⚑COMM 实例的配方随 PolicyBundle 撤回，只留外链（D-045）。
- **书面确认**：无；平台不代表用户与出版商签约。

**9 全文**：

- **FulltextOption**：`open_in_tab`（平台恒附，目标 `landing_url()` = `https://{site_host}/doi/{doi}`，原因码 `publisher_only` 或 `needs_entitlement`）；`user_fetch`（`recipe_ref: (atypon.pdf_from_doi, v)`，当前全部实例不签发）。
- **配方要点**：`resolve`（doi.org → 实例主机，跨出白名单即停）→ `entitlement_probe`（`selector_ref: atypon.pdf_link`，只在本次显式取回中执行）→ `download`（`/doi/pdf/{doi}`；epdf 阅读器永不作目标）→ `expect`。无占位符、不填表、不点同意按钮、不并发；挑战即 `stop_then_open_in_tab`，该平台冷却 24 h。
- **一键保存**：用户在自己的标签页打开 PDF 后点扩展按钮，经 `activeTab` 存入本人私有空间（设备本地，可选端到端同步）；扩展不另发请求。

**10 测试**：

- fixture（用户侧全部手写合成）：`atypon.ok`、`atypon.login_wall`、`atypon.sso_expired`、`atypon.cf_challenge`、`atypon.html_at_pdf`、`atypon.epdf_reader`。
- 平台侧探针 fixture（经 staging 网关录制）：7 个主机的 robots（本轮快照已存 scratchpad，仅作参照，正式件须重录）、tdmrep 挑战页。
- 契约测试：FS-PF-H1…H7 与适用于 RecipeProvider 的 CT-03、05、08、10、12；黄金决策行 7 行；属性测试：签发门单调。

**11 探针与替补**：

- `ProbeSpec`：`robots`（每主机每日）、`tdmrep`（每周）、`tos_hash`（INFORMS T&C、T&F 政策、Sage 政策，每周）、`structure`（指纹，随 robots 探针计算）。
- 处置：robots 变严或新增 AI 组立即收紧；AI 组消失、robots 变可读只告警并进复核（只降不升）；模板变化开复勘工单；ToS 哈希变化 7 天宽限。
- 替补链（fulltext）：共享 OA → OA 位置外链（OpenAlex、Unpaywall）→ `wiley_tdm`（仅 `wiley`）→ `atypon_user` → 机构链接解析器 → 在出版社打开。

**12 运维**：新鲜度不适用。SLO：探针结果进入 PolicyBundle 的延迟 ≤24 h。用户侧回执不进任何跨用户统计（08），运维台不显示用户侧成功率；配方健康只来自维护者合成检查（契约 P-7，待 08 认可）与用户自愿提交的工单，确认失效由 owner 经 PR 停用 `user_fetch`、保留 `open_in_tab`；如需回执聚合须另立 ADR（待拍板）。告警：AI 组变化、模板变化、ToS 哈希变化、robots 不可达。`review_every`：月看健康、季复核卡片（P0 口径，数值未核，一致性规范待拍板 P-12）；维护点数 declarative 0.5 + 实例 0.1×7（数值未核）。

**13 已知坑与待决**：

- `user_fetch` 全部休眠，价值取决于 LQ-19；本连接器在 V3 实际交付的是签发门、`open_in_tab` 目标与一键保存的来源归属。
- `wiley` 同时有官方 TDM API，候选序在前；页面兜底只在 TDM 不可用时出现。
- SAGE robots 不可达可能因出口而异；复测只能人工换出口，不改 UA。
- UChicago 走 epdf 阅读器，PDF 直链形态未核。
- 实例清单随探针维护（长稿 §19 第 18 条），新增实例须复核后才进 `applies_to`。候选实例 `pubs.aeaweb.org`（`aea_journals`，Atypon 模板、只具名禁 GPTBot [https://pubs.aeaweb.org/robots.txt, 2026-09-30]）：[site-special](site-special.md#aea_fulltext_user) 建议 `aea_fulltext_user` 的用户侧候选并入本连接器，未决 PF-Q11。

### silverchair_user

**1 身份**：`silverchair_user`；族 `platform_family`（`family_id: silverchair`）；`kind: recipe_provider`；`impl: declarative`，5 个实例 `impl: instance`；`contract_version: 1`；`connector_version: 0.1.0`（计划）；`lifecycle: active`（计划）；v1 来历：adapter `oup_silverchair`，去向 `user_side`、模式 `replay_only`（契约 §17 枚举，见 [v1-bridge 族 §6.1](v1-bridge.md#6-连接器卡片)），v1_bridge 版 `sunset_by` V2 出口，配方 V3 出口达 CL3（PF-Q5）；本清单 `impl: declarative`，不带契约 §2 的 `v1` 字段；CL 当前 —，目标 CL3（V3 出口，`oup_academic` 为 P0）；owner、backup_owner 待指派；服务 `oup_academic`（P0）、`aip`、`aaa_pubs`、`misq`（P1）、`geoscienceworld`（P2 ⚑RECHECK）；波次 W3。E 清单把它记为 `v1_bridge→platform_family`，本卡建议跳过桥接期直接写配方（未决 PF-Q5）。

**2 通道与操作**：同 `atypon_user`：只有 `locate_fulltext`（user）与平台侧 `probe`。

**3 上游接口事实**：

| 实例 | 主机 | robots 要点 | 具名 AI | TDMRep | ToS / TDM |
|---|---|---|---|---|---|
| `oup_academic` | academic.oup.com | Silverchair 模板；另禁多个学会子路径（含 `/pnas/`、`/lms/`、`/aaea/`）[https://academic.oup.com/robots.txt, 2026-09-30] | 无（只有 `008`） | 404 [https://academic.oup.com/.well-known/tdmrep.json, 2026-09-30] | 非商用 TDM 25 次内容请求/分、用后删除（◐二手 [https://sheffield.ac.uk/library/research/text-and-data-mining-tdm/tdm-university-collections-and-subscribed-resources, 2026-09-30]）；官方 TDM 页 URL 未找到；页面有 CF 质询（长稿） |
| `aip` | pubs.aip.org | Silverchair 模板 [https://pubs.aip.org/robots.txt, 2026-09-30] | 无 | 未核 | ToS 未核 |
| `aaa_pubs` | publications.aaahq.org | Silverchair 模板（F6 实测 robots [https://publications.aaahq.org/robots.txt, 2026-09-30]） | 无（只有 `*` 与 `008` 两组，F6 快照） | 未核 | ToS、TDM 未核 |
| `misq` | misq.umn.edu | Silverchair 模板（F6 实测 robots [https://misq.umn.edu/robots.txt, 2026-09-30]） | 无（同上） | 未核 | ToS 未核 |
| `geoscienceworld` | 主机未核 | 模板 robots + CF（长稿 2026-09-27，未复核） | 未核 | 未核 | 未核 |

- **认证**：用户本人机构会话；pc-agent 复用 v1 `CookieSession`、`SSOFlow`（长稿 §14.1）。
- **限速**：OUP 25 次/分（◐）远宽于护栏，护栏 6 s、200 次/日为准。
- **当前结论**：OUP、AIP 没有具名 AI 条目，是第一批可能签发 `user_fetch` 的实例，但 ToS 自动化条款未核，复核完成前签发门为假；AAA、MISQ 无具名 AI 条目（F6 快照），ToS 未核，同样不签发；GeoScienceWorld 待 ⚑RECHECK。

**4 请求声明**：

- 平台侧探针同 `atypon_user`（`silverchair.robots@<host>` 等）。
- 配方 `allowed_hosts: [doi.org, {instance.site_host}]`；Silverchair 的 PDF 可能经重定向落到另一主机（如 watermark 子域，未核），确认后须把该主机列入实例 `site_hosts` 并逐主机判 robots，否则跨主机重定向即停（`config/undeclared_host`）。
- PDF 链接取带内自描述值（`citation_pdf_url` 一类，v1 教训 L3），`extract_link{selector_ref: silverchair.pdf_link}`，字段是否存在未核，以 fixture 定。
- `Expectation` 与 `limits` 同 `atypon_user`。

**5 游标与增量**：无游标；同 `atypon_user`。

**6 映射**：同 `atypon_user`；OUP 学会子路径（`/pnas/` 等）上的期刊须按路径判 robots，`landing_url()` 与 PDF 路径都要过路径级判定。

**7 SCD**：同 `atypon_user`。

**8 合规**：

- 策略输入同 `atypon_user`；OUP、AIP 的 AI 维度无保留，ToS 维度 `unknown` → 当前上限对 `user_fetch` 不满足，只给 `open_in_tab`。
- 闸门：`geoscienceworld` ⚑RECHECK，复勘前只外链。
- `mit_press_direct`（同为 Silverchair）明文禁脚本抓取（长稿，未复核），不在 `serves` 中，只元数据。

**9 全文**：

- `open_in_tab` 由平台恒附；`user_fetch`（`recipe_ref: (silverchair.pdf_from_doi, v)`）只在 OUP、AIP 复核通过后按实例签发。
- 配方：`resolve` → `extract_link` → `entitlement_probe`（v1 四态判定：CHALLENGE > LOGIN_REDIRECT > NO_ENTITLEMENT > OK，特征库与网关共用）→ `download` → `expect`。

**10 测试**：

- fixture（手写合成）：`silverchair.ok`、`silverchair.login_redirect`、`silverchair.no_entitlement`、`silverchair.cf_challenge`、`silverchair.cross_host_redirect`。v1 的 ③④ 两个 fixture 本来就是合成的，须用维护者本人凭证做合成检查后校准（契约待拍板 P-7）。
- 探针 fixture：5 个主机 robots（含 `008` 组，断言不触发 AI 规则）。
- 契约测试：FS-PF-H1…H7 与 CT-03、05、08、10、12；黄金决策行 5 行。

**11 探针与替补**：

- `ProbeSpec`：`robots`（每日，重点盯新增 AI 组）、`tdmrep`（每周）、`tos_hash`（OUP 等，每周）、`structure`（模板指纹）。
- 迁移观察：RSC 已换 Silverchair 式模板 [https://pubs.rsc.org/robots.txt, 2026-09-30]；ACS robots 与该模板相同、是否迁移未核 [https://pubs.acs.org/robots.txt, 2026-09-30]；Emerald 2025-07 迁 Silverchair（长稿）。只开复勘工单，不自动加实例；ACS 受 HC-27 约束，任何时候都不加。
- 替补链：共享 OA → OA 位置外链 → `silverchair_user` → 机构链接解析器 → 在出版社打开。

**12 运维**：同 `atypon_user`；v1 `oup_silverchair` 的 runbook 迁入 pc-agent 手册。`review_every` 同 P0。

**13 已知坑与待决**：

- OUP 页面有 CF 质询：用户浏览器通常正常通过；一旦命中即停、冷却，不重试。
- `User-agent: 008` 全禁是对 80legs 爬虫的规则，不能误记为 AI 规则。
- 桥接期问题：E 清单把本连接器记为 v1 桥接，但用户侧执行器在 V3 才有，赶不上契约"V2 出口前移植"的期限（未决 PF-Q5）。

### cambridge_core_user

P1 紧凑卡。**已撤销（待拍板确认 `link_only`）**：由 `site_special` 移入本族，本卡是该 id 唯一的卡片（site-special 总表只留指向行）；不建连接器，全文通道记 `link_only`。

**1 身份**：`cambridge_core_user`；`platform_family`（`family_id: self_hosted`，Cambridge Core 自建平台，不属 Atypon/Silverchair）；`kind: recipe_provider`；服务 `cambridge_core`（v2-P1 ⚑COMM）；波次：撤销，不排；目标：待拍板确认 `link_only`（建议 CLX 不启用、`connector_id` 保留不复用）。

**2 通道与操作**：`locate_fulltext`（user）只可能产 `open_in_tab`；元数据经 crossref_delegated（前缀 10.1017）。

**3 上游接口事实**：官方写明不提供 API [https://cambridge.org/core/services/open-research-policies/text-and-data-mining, 2026-09-30]；TDM 限非商用，个人或集体下载超过 500 PDF/时可撤销访问 [https://www.cambridge.org/core/legal-notices/terms, 2026-09-30]；robots.txt 与 tdmrep.json 均 CF 挑战 403 [https://www.cambridge.org/robots.txt, 2026-09-30]。

**5 游标与增量**：无。

**8 合规**：robots unreachable → 全禁，签发门恒假（对用户侧属本族从严口径，PF-Q10；按 main 口径 ToS 与"集体"计量仍使代发不成立）；⚑COMM；"集体"计量意味着同机构多个用户合并触发，平台又不能协调跨用户信号（HC-02），所以不做任何代发。

**10 测试**：黄金决策行 1 行：候选集只有 `open_in_tab`，原因码 `publisher_only`。

**11 探针与替补**：robots 可读性每日探测；变为可读只告警并复核，不自动启用；替补链为 OA 位置外链 → 机构链接解析器 → 在出版社打开。

**其余**：配方在 robots 可读且 ToS 复核通过前不编写；一键保存照常可用（用户本人在标签页中操作）。

## 7 本族风险、坑与待决

| # | 风险或坑 | 处置 |
|---|---|---|
| 1 | 具名 AI 规则让 `atypon_user` 的 `user_fetch` 全部休眠 | 按 main 从严；LQ-19 有结论后按"UA × 路径"重算签发门，只改 PolicyBundle，不改配方 |
| 2 | AC-V1"平台出口访问用户侧全文主机为 0"与探针、feed 的冲突：SIAM 的全文在用户侧，但 `epubs.siam.org/action/showFeed` 由平台 feed 族读取；探针也要读这些主机的 robots | 待拍板 PF-Q2：口径改为"全文路径零请求"，按 `fulltext_paths` 审计 |
| 3 | robots 不可达三类（ScienceDirect 403、Cambridge CF、SAGE TLS）可能因出口或 UA 而异 | 按 unreachable 全禁；只能人工换出口复测，不换 UA |
| 4 | "集体"限额（Cambridge 500 PDF/时；World Scientific 短时 200 次下载即切断，◐） | 单用户硬顶远低于阈值；不做跨用户协调（HC-02） |
| 5 | 平台迁移（RSC、Emerald、TechRxiv、Authorea、ChemRxiv 迁 Atypon REX 等） | 指纹只开复勘；迁移后重录 fixture |
| 6 | 仓储默认值不可靠（DSpace 两套路径、EPrints 全部未核、Solr 索引滞后未核） | 实例显式值 + `Identify` 校验；EPrints 模块按需补卡 |
| 7 | 部分仓储主机 robots 禁 OAI 路径（OKR 禁 `/server/oai/`，MPRA 禁 `/cgi/`，Zenodo exporter 在禁区 `/api/` 下） | 不建实例或只经他源；放宽只提"待评审" |
| 8 | 用户侧日上限计数键未定（契约 P-6） | 本族建议按"用户 × `family_id`" |

## 怎么验收

- **CL0**：`atypon_user`、`silverchair_user` 的清单、本卡、SourceSpec 证据（含 `robots_named_ai`）齐全；13 条注册表 lint 与 6 条连接器 lint 通过；第二人合规复核在 CL0 出口完成。
- **CL1**：适用于 RecipeProvider 的 CT-03、05、08、10、12、配方 schema 与解释器对抗测试、FS-PF-H1…H7 在离线 CI 全过；仓储实例 CT-01…CT-12 与 FS-PF-R1…R5 随 `oai_pmh` 实例回放全过。
- **CL2**：平台侧探针在 staging 连续 ≥14 天全绿；用户侧配方以维护者本人凭证做合成检查（口径待 08 认可，契约 P-7），零挑战、零白名单外主机。
- **CL3（V3 出口）**：对应 main 03 的 V3 验收：取回意图、配方与回执中没有凭证与内容；配方解释器对抗测试全拒；用户侧护栏成立（[09 V3](../../09-roadmap-and-milestones.md#v3-多用户平台)）。另加 FS-PF-H6：网关审计中全文路径零请求。

## 未决事项

- **PF-Q1**：Content-Signal（`ai-train=no` 等）是否等同具名 AI 禁令、阻止 `user_fetch`（属 08 LQ-17 的机器可读信号映射）；本文默认从严阻止。
- **PF-Q2**：AC-V1 的"用户侧全文主机"改按路径定义（允许 `/robots.txt`、`/.well-known/tdmrep.json`、登记的条款页与 robots 放行的 feed 路径；全文路径零请求），需改 03、09 验收措辞，待拍板。
- **PF-Q3**："只具名 GPTBot"与"具名 ClaudeBot/anthropic-ai"是否同等处理（LQ-17、LQ-19）；本文同等处理。另：08 的"具名禁止 AI UA 的站点"是站点级口径，本文按"UA × 路径"求值，遇"具名 AI 组只禁非全文路径"的站点会比 main 宽（现有 12 个实例无此情形）；拍板前此类站点按站点级从严。
- **PF-Q4**：AI UA 名单的维护者与发布节奏（建议随 PolicyBundle，季度复核）。
- **PF-Q5**（已统一）：用户侧桥接连接器（`silverchair_user`，以及 `elsevier_tdm`、`wiley_tdm`）的 v1_bridge 版只以 `replay_only` 作离线对拍基准，不在生产运行，`sunset_by` 按契约 §17 取 V2 出口；同一 id 的 RecipeProvider 在 W3 直接编写、V3 出口达 CL3，复用 parse、特征库与 fixture。去向值用契约 §17 的 `user_side`（旧稿的 `to_pc_agent` 作废）。三处口径（本文、[official-tdm-api](official-tdm-api.md#未决事项) OT-Q1、[v1-bridge](v1-bridge.md#未决事项) 未决 7）一致；卡片只在目标族，v1-bridge §6.1 只列桥接期条款。
- **PF-Q6**：`cambridge_core_user` 改 `link_only` 且不建连接器（建议），还是保留配方位待 robots 可读后启用。
- **PF-Q7**：SourceSpec fulltext 通道新增 `robots_named_ai[]`、`content_signal` 两个证据字段（属对 03 SourceSpec 的细化，须在 V0 schema 中登记）。
- **PF-Q8**：OUP、AIP 的 ToS 自动化条款复核，决定首批签发 `user_fetch` 的实例。
- **PF-Q9**：DSpace 族默认路径是否按版本分两套；EPrints 行为与默认路径实测。
- **PF-Q10**：签发门中"robots 不可达即不签发"与"`*` 组须放行 PDF 路径"两项取自长稿 R16（用户侧自动请求也看 robots），比 main 更严：main 02、08（HC-29 与代发条件）把用户显式点击的单篇取回视为本人浏览、不看 robots。本文在 LQ-19 有结论前保留从严；若拍板按 main，删去这两项，SAGE 仍因 ToS 自动化条款未核而不签发，Cambridge 见 PF-Q6。`official_tdm_api` 的文档化 API 调用按 main 口径不看站点 robots，两族口径差异随本条一并拍板。
- **PF-Q11**：`aea_fulltext_user` 的用户侧候选是否并入 `atypon_user`（补 `atypon/aea_pubs` 实例、`serves` 增 `aea_journals`），还是 `link_only`；按现行签发门它也只给 `open_in_tab` 与一键保存。与 site-special 未决 8 一并拍板。
- **PF-Q12**：卡片小节标签本文已统一为 `**1 身份**：` 形式（原 `#### 1 身份` 四级标题与列表写法）；按[卡片模板](../connector-card-template.md)，V0 起以 `card render` 的输出为准。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–5.4 九族与族专有接口、§7.9、§12.3–12.6 候选排序与配方、§14.1 v1 adapter 去向）；`git show v2-drafts:docs/plan/v2/08-compliance-security-privacy.md`（§5.1 用户侧取回）；通用契约见[连接器接口契约](../contract.md)，卡片模板见 [connector-card-template](../connector-card-template.md)。
