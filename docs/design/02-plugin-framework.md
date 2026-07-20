---
title: 可插拔框架（Platform Adapter × Venue Spec）
status: implemented
owner: fable5
updated: 2026-07-21
---

# 02 · 可插拔框架设计

> 决策依据：D-002（两层结构）、D-003（双模块同协议）、D-005（元数据/全文源分离）。
> 配图：[diagrams/02-plugin-modules.svg](../diagrams/02-plugin-modules.svg)。

## 1. 功能说明

框架回答三个问题：
1. **怎样声明一个 venue**（期刊/会议/预印本源）——不写代码；
2. **怎样实现一个 platform adapter**——写代码，但只写站点专有部分；
3. **运行时怎样把 venue 请求路由到 adapter 与 fetcher/auth 基建**。

## 2. 两层结构

### 2.1 第一层：PlatformAdapter（代码）

一个平台一个 Python 包，实现 `SourceAdapter` 协议。预计清单（详见 [adapters/](adapters/README.md)）：

| 族 | adapter | 服务的 venue 示例 |
|---|---|---|
| open_access | `arxiv` | arXiv 全站（按 category 切 venue） |
| open_access | `ssrn` | SSRN 各 network/eJournal |
| open_access | `openreview` | ICLR、NeurIPS(评审)、部分 workshop |
| open_access | `pmlr` | ICML、AISTATS、COLT、UAI、CoRL… |
| open_access | `cvf` | CVPR、ICCV、WACV |
| open_access | `acl_anthology` | ACL、EMNLP、NAACL、COLING… |
| open_access | `neurips_proceedings` | NeurIPS 正式 proceedings |
| open_access | `aaai_ojs` | AAAI、AIES、HCOMP |
| open_access | `nber` | NBER working papers |
| open_access | `econsoc` | ECMA(部分)、TE、QE（学会自营，TE/QE 开放） |
| open_access | `repec` | RePEc/IDEAS 镜像的 WP 系列 |
| open_access | `acm_dl` | KDD、WWW、SIGIR、STOC、EC、SIGMOD…（**2026-01 起 ACM 全面 OA**，D-013；auth 能力保留作兜底） |
| open_access | `lipics` | ITCS 等 Dagstuhl/LIPIcs 出版会议 |
| open_access | `usenix` | OSDI、NSDI 等（全量 OA） |
| open_access | `pvldb` | VLDB（2008+ 期刊化 OA） |
| open_access | `isca` | INTERSPEECH（ISCA Archive OA） |
| open_access | `rss_proceedings` | RSS（roboticsproceedings.org） |
| open_access | `ijcai` | IJCAI（2017+ 自出版；此前年代经 era 路由） |
| open_access | `jmlr` / `jair` | JMLR、JAIR（OA 独立刊轻 adapter；TMLR 复用 `openreview`，TACL 复用 `acl_anthology`） |
| aggregator | `crossref` / `openalex` / `dblp` / `s2` / `unpaywall` | （元数据主干，见 D-005） |
| auth_gated | `elsevier_sd` | JFE、JME、JET、JBF、EJOR… |
| auth_gated | `wiley` | JF、ECMA、RAND、JEEA(部分)… |
| auth_gated | `oup_silverchair` | QJE、RFS、REStud、RF、EJ… |
| auth_gated | `uchicago` | JPE、JOLE、JLE… |
| auth_gated | `informs` | MS、OR、MSOM、IJOC、MOR… |
| auth_gated | `ieee_xplore` | ICASSP、ICRA、IROS、ICDM、FOCS、TPAMI…（IEEE 无 OA 新政，仍订阅制） |
| auth_gated | `siam` | SODA（epubs.siam.org——**出版方是 SIAM 非 ACM DL**，不受 ACM OA 覆盖） |
| auth_gated | `aea` | AER、AEJ 系、JEL、JEP（部分 OA） |
| auth_gated | `cambridge` | JFQA、ET、Econometric Theory… |
| auth_gated | `springer` | Mathematical Programming、F&S… |
| auth_gated | `mit_press` | REStat |
| auth_gated | `jstor` | 历史过刊兜底 |
| auth_gated | `pm_research` | JPM、Journal of Derivatives |

### 2.2 第二层：VenueSpec（YAML 声明）

一个 venue 一个文件，路径 `venues/<field>/<venue_id>.yaml`。**Schema v1**：

```yaml
# venues/finance/jfe.yaml —— 设计示例
id: jfe                       # 全局唯一，小写蛇形
kind: journal                 # journal | conference | preprint_channel
names:
  full: Journal of Financial Economics
  aliases: [JFE]
field: [finance]              # finance | econ | cs_ai | or_ms（可多值）
tier: T1                      # T1 必做 / T2 配置即得 / T3 暂缓（见 catalog）
identifiers:
  issn: ["0304-405X"]         # 期刊必填；会议用 dblp_key / openreview_id
  openalex_source: S154453860  # ⚠ 示例值，实现期核验
metadata_source: crossref     # discover/enumerate 用（D-005）
fulltext_source: elsevier_sd  # resolve/fetch 用
auth:
  level: institutional        # none | free_account | subscription | institutional
  provider_hint: elsevier     # 绑定的 AuthProvider profile 名
rate_limit:                   # 可缺省，缺省用 adapter 默认
  requests_per_minute: 10
quirks: {}                    # 平台 adapter 定义的自由参数（如 openreview 的 venue_id 模板）
status: active                # active | dormant | dead
notes: >
  SSRN 上有 First Look 先行版渠道，见 catalog/finance-journals.md。
```

```yaml
# venues/cs_ai/iclr.yaml —— 会议示例
id: iclr
kind: conference
names: {full: International Conference on Learning Representations, aliases: [ICLR]}
field: [cs_ai]
tier: T1
identifiers:
  dblp_key: conf/iclr
metadata_source: openreview
fulltext_source: openreview
auth: {level: none}
quirks:
  openreview_venue_template: "ICLR.cc/{year}/Conference"
  first_year: 2013
status: active
```

校验规则（Registry 加载时强制）：id 唯一；metadata_source/fulltext_source 必须是已注册 adapter；auth.level 与 adapter 能力兼容（如 `elsevier_sd` 不接受 `none`）；**期刊必须有 issn**（D-015 修订：OpenAlex 改信用计费后 openalex_source 降为可选补充字段，不再可替代 issn——Crossref 按 ISSN 枚举是期刊元数据主干的硬前提）。

## 3. SourceAdapter 协议（设计伪代码）

```python
class Capability(Flag):
    DISCOVER = auto()      # 能产出时间轴
    ENUMERATE = auto()     # 能列出期/届内论文
    RESOLVE = auto()       # 能定位资产 URL
    FETCH = auto()         # 能亲自下载（否则交给通用 fetcher）
    SEARCH = auto()        # 支持查询式订阅（arXiv/SSRN/聚合源）

class SourceAdapter(Protocol):
    adapter_id: str                      # "elsevier_sd"
    family: Literal["open_access", "auth_gated", "aggregator"]
    capabilities: Capability
    default_rate: RatePolicy             # 官方建议或保守默认，文档必须注明出处
    auth_requirement: AuthLevel          # 本平台最低认证等级

    def discover_timeline(self, venue: VenueSpec, since: Date | None) -> Iterable[IssueRef]: ...
    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]: ...
    def resolve_assets(self, venue: VenueSpec, paper: PaperStub,
                       session: SessionHandle | None) -> list[AssetPlan]: ...
    def fetch_asset(self, plan: AssetPlan, io: FetchIO,
                    session: SessionHandle | None) -> FetchResult: ...
    def search(self, query: SubscriptionQuery) -> Iterable[PaperStub]:  # 仅 SEARCH 能力者
        ...
    def healthcheck(self, session: SessionHandle | None) -> HealthReport: ...
```

关键语义：
- **能力缺失即路由**：某 adapter 无 `DISCOVER`（如 `uchicago` 页面难枚举），Registry 按 VenueSpec 把 discover/enumerate 路由给 `metadata_source`（crossref），resolve/fetch 才到 `uchicago`。这是 D-005 的机制化。
- **AssetPlan** 携带 `auth_needed`、`expected_type`（pdf/si/html/bibtex）、`url_strategy`（direct | render_page | api_call），fetch 基建据此选 HttpFetcher 或 BrowserFetcher。
- **adapter 永不自己 sleep/重试**——声明 `default_rate`，由 L2 RateLimiter/RetryPolicy 统一执行（否则限速逻辑散落各处不可审计）。

## 4. 注册与发现机制

1. **内置 adapter**：包内 `paper_crawler.adapters.*`，通过 Python entry points `paper_crawler.adapters` 组注册；
2. **第三方 adapter**：任何 pip 包声明同名 entry point 即被发现（可插拔的"插"）；
3. **VenueSpec**：启动时扫描 `venues/**/*.yaml` + 用户目录 `~/.paper-crawler/venues/`（后者可覆盖前者同 id 条目）；
4. **绑定解析**：Registry 构建 `venue_id → (metadata_adapter, fulltext_adapter, auth_profile, rate_policy)` 的路由表，启动即校验失败早报。

版本兼容：adapter 声明 `spec_version = 1`；框架破坏性变更递增版本并提供迁移说明（process/status-workflow 管理）。

## 5. 新增 venue 的两条路径（NFR-1/2 的落实）

**路径 A（≤30 分钟）**：平台已支持 → 写 YAML → `crawler venues lint` → `crawler timeline <id> --dry-run` 冒烟 → catalog 登记。
**路径 B（≤2 人日）**：新平台 → 按 [adapters/README.md](adapters/README.md) 模板先写设计文档（站点勘察、URL 模式、限速依据、风险）→ 实现 adapter + fixture 测试 → canary 注册 → 路径 A 收尾。

## 6. 测试与验收（本模块）

- **契约测试**：一套参数化测试跑所有 adapter——能力声明与实际实现一致（声明 ENUMERATE 者必须对 fixture 产出非空且 schema 合法的 PaperStub）。
- **Registry 单测**：YAML 校验拒绝非法 spec（未知 adapter、auth 不兼容、id 冲突）。
- **验收**（对应 AC-1.x）：mock adapter + 两条真实 VenueSpec（jfe.yaml、iclr.yaml）通过 lint 与路由解析；第三方 entry point 演示包可被发现。
