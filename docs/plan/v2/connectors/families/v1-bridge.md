---
title: v1 桥接族（v1_bridge）规范与连接器卡片
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# v1 桥接族：`v1_bridge`

本文回答：v1 的 20 个生产 adapter 在 v2 里各去哪里，桥接期怎样经出站网关运行、豁免什么、何时退役，v1 fixture 与 `PaperStub` 怎样接上 v2 一致性测试。结论：20 个 adapter 各有一份 `impl: v1_bridge` 清单以便追溯，去向分六类（§1.1）：平台侧桥接 7、降为族实例或族内连接器 5、改写为快照 1、转用户侧 5、暂停 2。只有平台侧桥接的 7 个（§5）在生产跑 v1 代码，请求经网关垫片 `EgressShim` 逐个变成 `RequestSpec`，照样过 robots、令牌桶、策略复核与审计；其余只在 CI 回放 v1 fixture，给移植件对拍。桥接只豁免"声明式 plan"，纯函数纪律、fixture 政策、依赖禁表与全部合规闸照常适用；V2 出口前全部 `impl: v1_bridge` 版本退役（移植的 id 升 1.0.0 按目标族运行，并入族实例或拆分的 id 转 `CLX`）。

## 要点

- **桥接是过渡，不是族**：不接新来源；每个清单写明 `v1.destiny`、`v1.port_target`、`v1.sunset_by`，到期未移植即自动降级并开移植卡（[契约](../contract.md) §17）。
- **执行权收回网关**：垫片把 v1 的每次 HTTP 调用匹配到清单端点，未声明主机不发请求；UA、凭证、robots、挑战判定全由网关做（D-055、HC-10、HC-29）。平台模式静态禁用 `fetch_asset`，不绑定 cookie 与用户凭证（D-053）。
- **用户侧不跑 v1 代码**：5 个受限全文 adapter 改写为 `FulltextRecipe`（W3），v1 只作知识与 fixture 来源；`pc_agent` 模式默认不用。
- **测试接缝**：v1 `.http` fixture 转成 (RequestSpec, Response) 对，`PaperStub` 经带版本的适配 mapper 变成 `NormRecord`；移植判据是 v1 fixture 与近 N 天样本上的 shadow 等价。
- **卡片位置**：13 张由目标族承载，本文只写其桥接期条款（§6.1）；本文承载 7 张（§6.2、§6.3）。
- **上游已变**：arXiv 旧 OAI 主机停用、NBER 条款禁止自动访问、OpenReview 匿名 `/notes` 被挑战、OpenAlex 增量过滤改付费；闸门只降不升。

## 1. 本族回答什么与适用边界

`v1_bridge` 只回答"v1 生产 adapter 怎样安全过渡到 v2 族"。与相邻族的分界：

- 与目标族：移植后按目标族规范运行，`connector_id` 不变：桥接是该 id 的 0.x 版（`impl: v1_bridge`），移植即 MAJOR 升 1.0.0、`impl` 改目标级；"桥接转 `CLX`"指 v1_bridge 版本退役（平台包移除 v1 代码，`v1` 块留作来历），并入族实例或拆分的 id 整体转 `CLX`（未决 10）。卡片在目标族（oai-pmh、site-special、platform-family、official-tdm-api）的，本文只列桥接期条款（§6.1）；aggregator-api、crossref-delegated、bulk-snapshot 指向本文的卡片由本文承载。
- 与用户侧族：配方规则归 [official-tdm-api.md](official-tdm-api.md) 与 [platform-family.md](platform-family.md)。

### 1.1 去向六类（`v1.destiny`）

| 值 | 含义 | 桥接模式 | 个数 |
|---|---|---|---|
| `platform_bridge` 平台侧桥接 | 过渡期在平台侧经垫片生产运行 v1 代码，V2 出口前移植 | `platform` | 7 |
| `family_config` 降为族实例配置 | 直接并入族引擎（实例、quirk 旗标或族内 mapper） | `replay_only` 或不加载 | 5 |
| `snapshot_rewrite` 改写为快照 | 在线路径由 `bulk_snapshot` 取代，v1 解析器复用为 mapper | 不加载 | 1 |
| `user_side` 转 pc-agent 用户侧 | 改写为用户侧配方，由扩展或 pc-agent 执行 | `replay_only` | 5 |
| `paused` 暂停 | 书面确认或许可前平台侧零请求，保留清单与 fixture | `replay_only` | 2 |
| `retired` 废止 | 直接 `CLX`；本批只有部分废止（dblp 在线路径、SSRN 浏览器模式、aea 平台 `RENDER_PAGE`），写在 `v1.parts` | — | 0 |

长稿 §14.1 五类与本文六值不一一对应，本文按 D-050…D-053、NBER 条款与 E 清单逐个重归类：arxiv bridge_patch → `family_config`；acl_anthology、openalex port → `platform_bridge`；econsoc port → `user_side`；s2、ssrn bridge → `family_config`；aea bridge → `user_side`；openreview、nber bridge → `paused`；dblp retire_online → `snapshot_rewrite`；`user_side_only` 过渡期的 `pc_agent` 改为 `replay_only`（未决 9）。取值与[契约](../contract.md) §17 一致；site-special 所称"解散"即主去向加 `v1.parts`。

### 1.2 三种桥接模式（`v1.mode`）

- `platform`：平台 worker 在 procrastinate 同步任务线程池中运行 v1 同步代码，出站只经垫片（长稿 02 §2.3.7）；只许 `platform_bridge`。
- `replay_only`：只在离线 CI 加载，传输层是 fixture 回放器；产出作移植件的对拍基准（oracle）。
- `pc_agent`：随 pc-agent 签名发布的 v1 代码在本机运行，平台不下发代码，仍须签名 `RetrievalIntent`（[契约](../contract.md)"全文与配方边界"）；本批默认不用，启用走待拍板。

## 2. 族专有接口（在通用契约之上）

通用类型与 15 个 `error_class` 一律按 [契约](../contract.md)；桥接只多网关垫片、桥接运行器、`PaperStub` 适配层三样。

### 2.1 网关垫片 `EgressShim`（替换 v1 `HttpClient`）

```python
# 设计伪代码 —— EgressShim：实现 v1 HttpClient 的方法签名，内部调用 02 的 EgressClient
TERMINAL = {"challenge", "policy_denied", "needs_confirmation", "budget_exhausted",
            "disabled", "config"}  # 永不交还 v1 处置；auth_expired 只在用户侧判定

class BridgeStop(BaseException):  # 不继承 Exception，v1 的 except Exception 吞不掉
    error_class: str; reason: str

class EgressShim:
    def __init__(self, manifest, egress: EgressClient, ctx: ExecCtx, op: str): ...
    def get_text(self, url, *, accept=None) -> str: return self._call("GET", url, accept).text
    def get_bytes(self, url, *, accept=None) -> bytes: return self._call("GET", url, accept).body
    def post_json(self, url, *, json_body, accept="application/json") -> bytes: ...  # 只许清单声明 method=POST 的端点
    def post_multipart(self, *a, **kw): raise BridgeStop("config", "multipart_not_bridged")
    def stream(self, url): ...  # 只许 endpoints[].stream=true（bulk），平台模式不用于全文

    def _call(self, method, url, accept, body=None):
        ep = self.manifest.match_endpoint(method, url)  # host + path_template 精确匹配
        if ep is None:
            raise BridgeStop("config", "undeclared_host")  # 不发请求，记 config/undeclared_host
        spec = RequestSpec(endpoint_id=ep.endpoint_id, request_class=ep.request_class, method=method,
                           url=strip_query(url), params=checked_params(url, ep),  # 剥 identity_param 哨兵，拒 personal_params
                           headers={"Accept": accept} if accept else {},  # 只放 AllowedHeader
                           auth=ep.auth, expect=ep.expect, idempotency_key=sdk_key(url, body))
        resp = self.egress.execute(EgressEnvelope(ctx=self.ctx, request=spec, ...))  # robots、桶、挑战、FetchLog
        self.signals.append(resp.signals)  # 补回 v1 拿不到的限速头与 response_date
        if resp.error_class in TERMINAL or (resp.error_class and self.op not in ("lookup", "probe")):
            raise BridgeStop(resp.error_class, resp.reason)  # 非 lookup/probe（含 snapshot_import）即停在安全点（契约 §5）
        if resp.error_class:  # 仅 lookup、probe：按 v1 类抛出，让 v1 逐项隔离
            raise CrawlerError(V1_CLASS[resp.error_class], resp.reason, status_code=resp.status)
        return resp
```

要点：

- **分类以网关为准**：v1 把无特征 403 记 `NO_ENTITLEMENT`（S-c），契约要求不明 403 从严记 `challenge`，除非 `status_overrides` 凭证据声明；v1 类只在 lookup、probe 中驱动逐项隔离，其余操作遇非合法结果停在最后安全点（契约 §5、§7），合法空（如 acl raw 404）由 `expect.legit_status` 声明；`TaskOutcome` 与 FetchLog 只记 v2 类。
- **凭证不进 v1 代码**：`set_api_key`、`set_email` 只收哨兵值（v1 只用它们判断"是否已配置"）；真实 key 按 `AuthRef(deployment/*)`、部署联系邮箱按 `identity_param`（[aggregator-api.md](aggregator-api.md) 的提议）由网关注入，垫片先剥掉 v1 拼进 URL 的哨兵值；专属 token client 与 `CookieSupplierConsumer` 在平台模式不调用。
- **不双重限速**：v1 `RateLimiter` 换空实现；`default_rate` 只作上限证据，与 SourceSpec 取更严者进网关令牌桶。
- **断开惰性自建 client**（L17）：worker 不设 v1 的环境变量（v1 为 `PAPER_CRAWLER_CONTACT_EMAIL`；v2 部署联系邮箱由网关注入，变量名 `CONFLUO_CONTACT_EMAIL` 待 V0 定）；垫片注入前的联网调用由网络隔离拒绝，套件断言零次。

### 2.2 桥接运行器与 v1 五方法映射

桥接不实现 `PlatformConnector.plan()`，由专用运行器驱动 v1 生成器；准入判定、盖章、页提交与停机语义同通用执行器。

| v1 方法 | v2 Operation | 平台模式 | 说明 |
|---|---|---|---|
| `discover_timeline(venue, since)` | `enumerate`（`since=None`）、`increment` | 可用 | 产出 `IssueRef`，即提交单元 |
| `enumerate_issue(venue, issue)` | 同上的页 | 可用 | 一期的全部 `PaperStub` 为一页，经 §2.3 转 `RawRecord` |
| `resolve_assets(...)` | `locate_fulltext` | 仅 `resolve_offline=True` | `AssetPlan` → `FulltextOption`：`DIRECT` 且许可在白名单 → `oa_link`；`RENDER_PAGE` → `open_in_tab`；`API_CALL` → `tdm_api`（带 `recipe_ref`，契约 §11） |
| `fetch_asset(...)` | 无 | 静态禁用 | 平台永不代取 |
| `healthcheck(...)` | `probe` | 须重审 | 端点在 `allowed_hosts` 且 robots 允许才登记；arxiv 的 Query API、pmlr 的失配正则（L27）改写 |
| `enrich_batch(dois)`（协议外） | `lookup` | 可用 | openalex、s2、repec（零网络本地 join）；unpaywall 的 v1 联网 resolve（`GET /v2/{doi}`）按 `lookup` 驱动，只产 OA 位置 |
| —（v1 无 `search()`） | `search` | 不声明 | — |

```python
# 设计伪代码 —— 桥接运行器（只在 impl=v1_bridge 且 v1.mode=platform 时由平台 worker 加载）
def run_bridge(task, ctx: PlanCtx, m, adapter, sink, egress) -> TaskOutcome:   # 准入与 ctx 构造同契约 §5 run()
    acct = RunnerAccount(task.budget)   # 与通用执行器同一账本：垫片每次请求前查 max_requests 与 deadline，超限抛 BridgeStop(budget_exhausted)
    shim = EgressShim(m, egress, ExecCtx.from_task(task), task.operation, account=acct)
    bind_v1(adapter, http=shim, rate_limiter=NoopLimiter(), email=SENTINEL, api_key=SENTINEL)
    until = ctx.now  # 运行开始由 PlanCtx 冻结
    cur = task.cursor.cursor if task.cursor else None   # CursorEnvelope 内的类型化游标（契约 §6）
    try:
        if task.operation == "lookup":  # openalex_api、unpaywall_api、repec_redif：v1 类错误已由 v1 逐项隔离
            stubs = adapter.enrich_batch(task.payload.identifiers)  # LookupInput；unpaywall 调 v1 resolve 路径，见 §2.2
            sink.commit_page(task, Page(records=[to_raw(s, m, until, "federated") for s in stubs],
                                         next_cursor=None, signals=shim.drain()))
            return TaskOutcome.completed()
        # snapshot_import（repec_redif，v1 无 timeline 能力）不进本循环：下载由 bulk_snapshot 引擎经网关流式完成，v1 parse.py 作 mapper
        for venue in m.v1.venues_for(task.scope_key):
            since = None if task.operation == "enumerate" else cur.value - m.overlap   # date_watermark
            for issue in adapter.discover_timeline(venue, since=since):
                if task.operation == "enumerate" and cur and issue_key(issue) in cur.completed:   # window_set（按期键，见未决 11）
                    continue
                if acct.exhausted(clock.now()): raise BridgeStop("budget_exhausted")   # 页边界查 max_pages 与 deadline
                stubs = list(adapter.enumerate_issue(venue, issue))
                sink.commit_page(task, Page(records=[to_raw(s, m, until, "harvest") for s in stubs],
                                             next_cursor=after_issue(task, issue),  # enumerate：期键入 window_set；increment：None
                                             signals=shim.drain()))
                acct.count_page_n(len(stubs))
    except BridgeStop as s:  # 结果按契约 §7：budget_exhausted、超 deadline 的 rate_limited 为 partial，其余 stopped
        return TaskOutcome(status=outcome_of(s.error_class), error_class=s.error_class,
                           committed=sink.last_committed(task))
    except CrawlerError as e:  # v1 未处理的错误：停在最后安全点
        return TaskOutcome.failed(V2_CLASS[e.error_class], committed=sink.last_committed(task))
    return TaskOutcome.completed(advance_to=until)  # increment 的水位只在整段完成后推进
```

游标：`enumerate` 用 `window_set`（已完成的 `IssueRef` 键；契约 §6 的 `window_set` 以日期区间记 `completed`，按期键记属扩展，见未决 11），每期完成即安全提交；`increment` 用 `date_watermark`，整段完成后推进到 `until`；期内崩溃整期重跑，重复由 `(source_id, source_key)` 去重吸收。v1 的月桶、年桶、卷号表经纯函数 `migrate_cursor` 转换。

### 2.3 `PaperStub` → `NormRecord` 适配层

```python
# 设计伪代码 —— 适配 mapper：mapper_id = "v1stub.<adapter>"，mapper_version 从 1 起
def to_raw(stub: PaperStub, m, now, provenance) -> RawRecord:
    payload = stub_to_json(stub)  # 键排序；meta 保持原顺序
    return RawRecord(source_id=m.v1.source_for(stub), source_key=first_id(stub.identifiers, m.v1.key_order),
                     kind="upsert", channel=m.v1.channel, provenance=provenance,  # harvest 或 federated（lookup）
                     endpoint_id=f"v1:{m.v1.adapter}", payload=payload, fetched_at=now)  # sha256 由 SDK 算

def normalize_v1stub(raw, ctx: MapCtx) -> NormRecord:
    s = raw.payload
    return NormRecord(
        identifiers=[(SCHEME[k], normalize_id(k, v)) for k, v in s["identifiers"]],  # 粒度查标识符注册表
        title=s["title"], authors=s["authors"], year=s["year"], pub_date=s["pub_date"], abstract=s["abstract"],
        version_claim=VersionClaim(stage=ctx.instance.v1.stage_default, seq=meta_int(s, "version"),
                                   basis="paperstub.meta.version"),
        license=license_claim(meta(s, "license"), basis="paperstub.meta.license"),  # 缺失即 unknown
        extra={k: v for k, v in s["meta"] if k in ctx.instance.v1.meta_keep})
    # 摘要权利与 rights_class、shareable 等由共享 classify_rights() 计算，适配层不给（契约"映射契约"）
```

- DOI 规范化只用 v1 `ids.py::normalize_doi` 的移植版，`aaai_ojs`、`acl_anthology` 里的同名实现不沿用（长稿 §14.2）。
- **语义等价**（迁移回归与移植判据共用）：同一 `source_key` 下，规范化后的标识符集合、`normalize_title` 后标题、年份、作者序列、摘要有无、许可原串逐项相等；差异只许落在 `v1.expected_diffs` 登记的类别（如 arXiv 类目级 set 的新增记录），其余为 0。
- v1 golden 经同一适配层转成黄金 `NormRecord`；`UPDATE_GOLDEN` 写入后仍判失败、人工过目再提交（v1 `tests/fixtures/README.md`）。

### 2.4 第三方客户端库

长稿 §5.6 复用的 `acl-anthology`、`openreview-py` 等自带 HTTP：桥接与移植件只用其解析部分，或把传输层换成垫片，不调用其联网函数（契约待拍板 P-2）。

## 3. 实例与清单字段

桥接件登记为 `family: v1_bridge`、`impl: v1_bridge`。`replay_only` 清单的 `kind`、`exec_side` 取移植目标的值（用户侧去向为 `recipe_provider`、`user`），只在离线 CI 加载：`auth` 恒为 `null`（D-054），`allowed_hosts` 只供回放校验、不生成网关白名单，CL1 上限即生产 deny。本族在契约必填字段之外只加 `v1` 块与端点 `status_overrides`：

```yaml
# 设计伪代码 —— registry/connectors/cvf_open_access_pages.yaml（节选：桥接专有字段）
v1:
  adapter: cvf  # v1 entry point；代码取自 tag v1-final，只读
  destiny: platform_bridge  # 六值，§1.1
  mode: platform  # platform | replay_only | pc_agent
  port_target: {family: site_special, impl: custom_plan}
  sunset_by: V2-exit  # 到期自动降 CL2 并开移植卡
  parts: []  # 拆分去向 [{channel, destiny, to}]
  venues: [cvpr, iccv, wacv]  # v1 VenueSpec 转换器产出
  connector_params: {}  # adapter 私有参数（长稿 §3.7）；cvf_edition_overrides 按该节转 editions 逐届键
  key_order: [doi, cvf_id]  # source_key 取第一个存在的标识符
  stage_default: am  # 适配层 version_claim.stage 默认
  meta_keep: [pdf_url, track]
  expected_diffs: []
  legacy_fixtures: v1:tests/fixtures/cvf/  # provenance=v1_import
  exemptions: [declarative_plan]  # 唯一豁免；同步记入 conformance.rules 的 exempt{reason, approved_by}
endpoints:
  - {endpoint_id: cvf.list_page, request_class: html_page, method: GET,
     path_template: "/{id}", hosts_touched: [openaccess.thecvf.com],  # 占位符只用契约 §15 词表
     expect: {content_types: [text/html], min_bytes: 2048, empty: error},
     status_overrides: [{status: 403, error_class: challenge, fact_ref: cvf_ua_403, fixture: cvf/403.http}]}
```

桥接专用 lint 3 条：`impl: v1_bridge` 必有 `v1.destiny`、`v1.sunset_by`、`v1.port_target`；`mode: platform` 只许 `destiny: platform_bridge`；v1 `domains` 与 `default_rate.source_note` 里出现、却不在 `allowed_hosts` 的主机须在卡片 §13 说明去向。

## 4. 族一致性套件

### 4.1 通用契约测试在桥接上的适用面

[一致性与测试](../conformance-and-testing.md) 的 12 条通用测试中，CT-01…CT-08、CT-10…CT-12 适用：CT-01 传输层换回放器（时钟与环境见 §4.3），CT-02 用冻结时钟夹具，CT-06 经 §2.3，CT-04 游标属性按"期"粒度；CT-01、03、10、12 是红线、不可豁免；CT-09 不适用（不声明 `ordered_by`）。

### 4.2 桥接专有测试

编号 B1…B8 即族套件规则，`conformance.rules` 中按一致性规范的 `FS-<族缩写>-NN` 记法记为 `FS-V1B-01`…`FS-V1B-08`（如 B1 ↔ `FS-V1B-01`）。

| 编号 | 断言 |
|---|---|
| B1 垫片覆盖 | v1 五个 HTTP 方法全部经垫片；`post_multipart` 恒 `config`；未声明主机与路径零请求 |
| B2 终止不可吞 | 在 v1 有 `except Exception` 处注入 `challenge`、`policy_denied`，任务仍以 `stopped` 结束，挑战后重试 0 次 |
| B3 无自建出口 | 平台模式跑全部 fixture，自建 `httpx.Client`、读 v1 环境变量、调用 `fetch_asset` 与 cookie 接口均为 0 次 |
| B4 凭证隔离 | 垫片产出的 `RequestSpec` 无 UA、Cookie、Authorization、已知 key 头与 `personal_params`；key 只以 `AuthRef` 出现 |
| B5 fixture 转换 | v1 `.http`（注释头、`HTTP-STATUS`、头、正文）转成 (RequestSpec, Response) 对，`SYNTHETIC` 标记与原路径进来历字段，往返无丢失 |
| B6 迁移回归 | 每个 adapter 的 v1 fixture 经桥接回放，与 v1 golden 语义等价，作长稿 09 AC-V1.15 的证据 |
| B7 分类对表 | v1 `ErrorClass` ↔ v2 `error_class` 映射与 `status_overrides` 每行有 fixture；v1 默认 403 → `NO_ENTITLEMENT` 的行在 v2 记 `challenge`，有证据声明的除外 |
| B8 移植等价 | 移植件与桥接件在 v1 fixture 与近 N 天 staging 样本（P0 14 天，其余 7 天）上 shadow 等价，桥接版才退役（并入或拆分的 id 转 `CLX`） |

### 4.3 桥接期豁免与满足方式

唯一豁免是"声明式 plan"（契约 §17）；纯函数纪律（CT-01 红线）与 fixture 政策在[一致性文档](../conformance-and-testing.md)中不可豁免，桥接只改满足方式。

| 规则（契约） | 桥接情形 | 处置 |
|---|---|---|
| 声明式 `plan`（豁免） | v1 在生成器内自发请求、自己翻页 | 垫片逐次生成 `RequestSpec`，网关逐请求复核 `decision_id` 与 `inputs_epoch` |
| 纯函数纪律（不豁免） | v1 读系统日期与环境变量 | `bind_v1` 把读时钟处换成冻结的 `ctx.now`；环境读取由垫片模块替换，worker 不设 v1 环境变量，沙箱照样抛错；CT-01 测法调整待确认（未决 12） |
| fixture 政策（不豁免） | v1 fixture 为直连录制或合成 | 来历值 `provenance: v1_import`，只作回放与等价证据，不作 CL2 证据；照常脱敏扫描（CT-12）；移植时经 staging 网关重录 |

依赖禁表不豁免（[契约](../contract.md) §17）：桥接包内 v1 的 `paper_crawler/http.py` 由垫片模块整体替换（惰性自建也只能得到垫片，缺 `ExecCtx` 即 `config`）；直接导入 httpx 或浏览器库的 v1 模块（`oup_silverchair`、`browserfetch`、各专属 token client）不进平台包；B3 与网络隔离（[02 出站网关](../../02-architecture.md#出站网关egress-gateway)、D-055）兜底。

其余同样不豁免：robots 先行、诚实 UA、凭证只在网关、挑战即停并冷却 24 小时、策略判定与漂移降级、`allowed_hosts`、FetchLog、许可闸、P0 的 CL1。

### 4.4 退役时限与等级

| 时点 | 要求 |
|---|---|
| W0（V0） | fixture 转换器与回放传输（B5）就位；`arxiv_oai`、`crossref_rest`（及依赖它的 `crossref_delegated`）按参考连接器直接移植，v1 回放只作 oracle |
| V1 前半（[实施计划](../implementation-plan.md) V1-T4 余项） | 垫片与运行器、B1–B4、B6、B7 就位，先于 W2 桥接卡 |
| W2（V1 后半） | 7 个平台侧桥接经 staging 达 CL2（P0 连续 ≥14 天），V1 出口达 CL3；其余清单回放通过，满足 AC-V1.15（除 dblp 在线通道、SSRN，口径见未决 8） |
| V2 期间 | 7 个平台侧桥接移植并过 B8（实施计划 CN-6）；用户侧 5 个的 v1 fixture 转入配方 fixture 集 |
| V2 出口 | 全部 v1_bridge 版本退役；`sunset_by` 过期未移植者自动降 `cl_effective` 到 CL2 并开移植卡（CL2 生产口径见契约待拍板 P-4） |

桥接件 `connector_version` 从 `0.1.0` 起；移植是 MAJOR 升级，升到 `1.0.0` 并附 `migrate_cursor` 或"重置 + 回填窗口"声明。

## 5. 连接器清单总表

v1 行数与 fixture 数取自第一阶段 C 调研 §2.2（`archive/v1` 代码事实）；人日为 E 清单估值（未核）。模式按 §1.1，只注"不加载"；CL 列为"桥接版目标 / 移植版目标"，当前全部未建清单（—）。`mixed` 为 E 清单口径；契约 `exec_side` 只有 platform / user，`mixed` 解释为两个清单：PlatformConnector 与 RecipeProvider（同一 connector_id 前缀，id 待契约与矩阵定），各自状态见卡片 §2。暂停写法统一为"暂停，CL0，许可前不排波次（待拍板）"；W3u 是用户侧通道的波次记法（依赖 V3 扩展或 pc-agent）。

| connector_id | 来源数 | 优先级 | 波次 | exec_side | 去向 → 目标 | 人日 | v1 行 / fixture | 前置依赖 | CL 目标 |
|---|---|---|---|---|---|---|---|---|---|
| `arxiv_oai` | 1 | P0 | W0 | platform | family_config → `oai_pmh` | 1.5 | 925 / 11 | oai_pmh 引擎 | CL1 / CL3 |
| `crossref_rest` | 1 | P0 | W0（调整） | platform | family_config → `aggregator_api` | 1.5 | 796 / 15 | 无（`crossref_delegated` 依赖它） | CL1 / CL3 |
| `aaai_ojs_oai` | 1 | P0 | W2 | platform | family_config → `oai_pmh` 实例 | 0.5 | 1152 / 12 | oai_pmh 引擎 | CL1 / 实例 CL3 |
| `acl_anthology_xml` | 1 | P0 | W2 | platform | platform_bridge → `site_special` | 1 | 1043 / 11 | 垫片 | CL3 / CL3 |
| `cvf_open_access_pages` | 1 | P0 | W2 | platform | 同上 | 0.5 | 799 / 13 | 垫片 | CL3 / CL3 |
| `neurips_proceedings_pages` | 1 | P0 | W2 | platform | 同上 | 1 | 735 / 12 | 垫片 | CL3 / CL3 |
| `pmlr_volumes` | 1 | P0 | W2 | platform | 同上 | 0.5 | 734 / 11 | 垫片 | CL3 / CL3 |
| `openalex_api` | 1 | P0 ⚑BUDGET | W2 | platform | platform_bridge → `aggregator_api` | 1 | 725 / 8 | 垫片、美元账本 | CL3 / CL3 |
| `repec_redif` | 1 | P0 | W2 | platform | platform_bridge → `bulk_snapshot` | 2 | 879 / 3 | 网关 rsync/FTP（待拍板）；扩 handle 映射（新 ADR，D-036） | CL3 / CL3 |
| `dblp_drops_snapshot` | 1 | P0（快照形态） | W2 | platform | snapshot_rewrite / 不加载 → `bulk_snapshot` | 2 | 663 / 11（不接入） | 流式导入；新 ADR 解除 D-037 出列（D-050） | CL0 / CL3 |
| `openreview_api` | 1 | P0 ⚑ACCT | 平台侧停用；用户侧 W3u（token 只在端侧） | mixed | paused → `site_special` | 1.5 | 1182 / 18 | 书面确认 | CL0 / 待定（用户侧随 P-13） |
| `nber_site` | 2 | P0 | 暂停（平台侧与用户侧），许可前不排波次（待拍板） | mixed | paused → 拆分 | 1.5 | 992 / 8 | NBER 书面许可 | CL0（暂停）/ CLX |
| `aea_fulltext_user` | 1 | P0 | W3 | user | user_side → `atypon_user` 实例（建议） | 1 | 349 / 6 | 扩展 | CL1 / CLX |
| `econsoc_fulltext` | 1 | P0 | W3 | mixed | user_side → 拆分 | 1 | 1075 / 5 | oai_pmh 引擎、扩展 | CL1 / CLX |
| `elsevier_tdm` | 1 | P0 ⚑COMM | W3 | user | user_side → `official_tdm_api` | 1.5 | 527 / 5 | pc-agent | CL1 / CL3（V3） |
| `wiley_tdm` | 1 | P0 ⚑COMM | W3 | user | 同上 | 1.5 | 403 / 4 | pc-agent | CL1 / CL3（V3） |
| `silverchair_user` | 5 | P0 | W3 | user | user_side → `platform_family` | 1.5 | 743 / 4 | 扩展 | CL1 / CL3（V3） |
| `ssrn_crossref` | 1 | metadata-only（P0）⚑DRIFT | W2 | platform | family_config / 不加载 → `crossref_delegated` 实例 | 0.5 | 630 / 6（只转 fixture） | `crossref_delegated` | CL0 / 实例 CL3 |
| `s2_api` | 1 | P1 ⚑COMM | W3 | platform | family_config → `aggregator_api` | 1 | 382 / 7 | 部署 key | CL1 / CL3 |
| `unpaywall_api` | 1 | P1 | W2（调整） | platform | platform_bridge → `aggregator_api` | 0.5 | 692 / 12 | 垫片 | CL3 / CL3 |

波次按框架规则，并采纳[实施计划](../implementation-plan.md)的调整：`crossref_rest` 提到 W0（`crossref_delegated` 依赖其请求声明）；`unpaywall_api` 提到 W2（AC-V1.21 要求 OA 定位有两条同能力通道）；econsoc、openreview 在 W3 只做用户侧（W3u）；`nber_site` 平台侧与用户侧一律暂停（CL0），取得 NBER 书面许可前不排波次（待拍板）。v1 `mock_platform` 不计入，保留为桥接套件夹具。

## 6. 连接器卡片

卡片 13 节标题按 [卡片模板](../connector-card-template.md)。省略处按本族默认：§1 `lifecycle: active`，桥接版到期退役（并入或拆分的 id 转 `retired`，即 CLX）；§4 经垫片生成请求，令牌桶五元组为（来源, 主机, 请求类, 部署身份, 出口 IP）；§5 lookup 与快照类不适用 `late_path`、`window_max`；§7 SCD 只声明 v1 能力对应的 Operation，不声明 `search`；§10 为 v1 fixture 回放（B5–B7）加 §4.1 适用项；§12 owner 与 backup_owner 待指派（P0 两人），`review_every` 为 P0 月看健康、季复核卡片，P1 季复核。上游事实未注日期者为长稿值（2026-09-26/27），未复核。

**6.1 卡片在目标族的桥接连接器（本文只写桥接期条款）**

以下 13 个的卡片在目标族文档（同一 connector_id 只在一处有卡），本表只补桥接期条款；去向、模式、v1 行数与 fixture 数见 §5。

| connector_id（卡片） | v1 adapter | sunset_by | 桥接期要点 |
|---|---|---|---|
| [`arxiv_oai`](oai-pmh.md#arxiv_oai) | arxiv | V1 出口（W0 直接移植） | v1 用已停用的 `export.arxiv.org/oai2` 与 archive 级 set，fixture 转换标 `host_rewrite`；v1 healthcheck 走 Query API（robots 已禁），不登记；`expected_diffs`：类目级 set 新增记录、逐篇 license |
| [`aaai_ojs_oai`](oai-pmh.md#aaai_ojs_oai) | aaai_ojs | V1 出口 | 并入 `oai_pmh` 实例后本 id 转 `CLX`；`quirks.volume_map` 转 `editions.explicit`；首次全量基线（L6：OJS datestamp 滞后近 2 年致当届漏收） |
| [`acl_anthology_xml`](site-special.md#acl_anthology_xml) | acl_anthology | V2 出口 | 沿用 v1 的 `api.github.com` `git/trees`（每次运行 1 次）与 `raw.githubusercontent.com` 卷 XML，两主机分桶；GitHub 403 → `rate_limited` 须有证据行，raw 404 为合法空 |
| [`cvf_open_access_pages`](site-special.md#cvf_open_access_pages) | cvf | V2 出口 | 403 → `challenge`，不换 UA；0 条目且无 `day=all` 链接 → `parse`（L5）；v1 以内置 cadence 零网络推断届次，移植改读 `/menu` |
| [`neurips_proceedings_pages`](site-special.md#neurips_proceedings_pages) | neurips_proceedings | V2 出口 | 补丁：v1 `(era, track)` 与后缀代际闭表改开放枚举加探针；三镜像共桶须附证据（L19） |
| [`pmlr_volumes`](site-special.md#pmlr_volumes) | pmlr | V2 出口 | 补丁：卷发现改读 `feed.xml`，替代首页 diff 与卷号探测；v1 healthcheck 正则失配（L27）不登记；`raw.githubusercontent.com`（2024 年起新卷 PDF）单独一桶 |
| [`openreview_api`](site-special.md#openreview_api) | openreview | V2 出口（未确认即 `CLX`） | v1 的 403 → `AUTH_EXPIRED` 作废，403 `ChallengeRequiredError` → `challenge`；v1 token 以 client 级 Cookie 头承载，平台不得复用；`openreview-py` 只用解析部分 |
| [`nber_site`](site-special.md#nber_site) | nber | V2 出口 → `CLX` | 卡片记 CL0；`v1.parts`：元数据 → `crossref_delegated`（10.3386）+ `repec_redif`；RSS 暂停，`nber/rss.py` 只作 feed 族解析器样本；直取全文废止（18 个月开放规则未核） |
| [`aea_fulltext_user`](site-special.md#aea_fulltext_user) | aea | V2 出口 → `CLX` | 卡片称"解散"；平台 `RENDER_PAGE` 废止（D-053）；DOI 代码表转成用户侧实例的 DOI→路径规则；`pubs.aeaweb.org` 为 Atypon 模板，建议并入 `atypon_user` 实例 |
| [`econsoc_fulltext`](site-special.md#econsoc_fulltext) | econsoc | V2 出口 → `CLX` | 卡片称"解散"；`v1.parts`：TE、QE → `oai_pmh` 实例；ECMA 元数据 → `crossref_delegated`（10.3982，D-028）；ECMA 订阅全文 → 用户侧配方；v1 联网 resolve 不在平台运行 |
| [`silverchair_user`](platform-family.md#silverchair_user) | oup_silverchair | V2 出口（配方 V3 出口达 CL3，未决 7） | 专属 httpx client 与 `CookieSupplier` 不加载；`ChallengeDetector` 四态特征表迁入端侧共用判定库；③④ fixture 为合成（L22） |
| [`elsevier_tdm`](official-tdm-api.md#elsevier_tdm) | elsevier_sd | 同上 | v1 的 403 → `AUTH_EXPIRED`、任意 429 当日熔断迁入配方 `expect`；5 个 fixture 转为配方回放，全文 XML 换等长合成文本；专属 `X-ELS-APIKey` client 平台模式不加载 |
| [`wiley_tdm`](official-tdm-api.md#wiley_tdm) | wiley | 同上 | v1 无 token 时的 `RENDER_PAGE` 兜底改走 `atypon_user`；v1 403 → `NO_ENTITLEMENT` 保留为有证据的覆盖行；v1 曾"已实现却零 venue 引用"（与 L24 同类），配方上线时校验接线 |

**6.2 P0 卡片（本文承载）**

### crossref_rest

**1 身份**：v1 `crossref` → `aggregator_api`（LOOKUP，impl declarative）；两轴参数化枚举与 cursor 深翻移入 [crossref_delegated](crossref-delegated.md) 引擎；contract 1；0.1.0 → 1.0.0；serves `crossref`；W0（实施计划调整，为其前置件）；family_config / replay_only，sunset V1 出口。

**2 通道与操作**：metadata：`lookup`（`/works/{doi}`）、`probe`；`enumerate`、`increment` 归 `crossref_delegated`；platform。

**3 上游接口事实**：按请求类分池：单条 public 5/s、polite 10/s，列表 public 1/s、polite 3/s，并发 public 1、polite 3；按邮箱计限，不得多邮箱扩额 [https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137, 2026-09-30]；分池生效日 F1 记 2026-07-21、G 记 2025-12-01，两说待核；有 `x-api-pool`、`x-rate-limit-limit`，无 `x-rate-limit-type` [实测 https://api.crossref.org/works?rows=0, 2026-09-30]。

**4 请求声明**：`crossref.works_doi`（request_class `single`）；桶（`crossref`, `api.crossref.org`, `single`, 部署 mailto, 出口 IP），与 `crossref_delegated`、`ssrn_crossref` 共用；`identity_param: mailto` 由网关注入；404 记 `PageSignals.not_found`。

**5 游标与增量**：无（lookup）。

**6 映射**：DOI 作品级；`update-to` 撤稿更正进 `status_claims`；多条 `license[]` 带 basis 全留；JATS 摘要版权归出版方，由 `classify_rights` 判定。

**7 SCD**：lookup native；**不声明 `search`**（main 口径，长稿 `works_query` 作废）。

**8 合规**：文档化 API；元数据按事实（CC0 口径），摘要非共享默认；`background`；无闸门标记。

**9 全文**：`link[]` 只作 `oa_link` 候选依据，平台不取。

**10 测试**：v1 15 个 fixture；补单条含 `update-to`、多 `license`、JATS 摘要、429；移植件读限速头（v1 冻结 client 不回传，L16）。

**11 探针与替补**：`x-api-pool` 取值集合、各池 `x-rate-limit-limit`、固定 DOI；替补 OpenAlex、年度公共数据文件。

**12 运维**：交互 lookup 延迟随 04 联邦预算；429 比例告警。

**13 已知坑与待决**：`published` 轴 filter 用缩写 `pub`；v1 静态 300 rpm 在分池后过宽，桥接件不进生产，只作 oracle。

### openalex_api

**1 身份**：v1 `openalex` → `aggregator_api`（mapper）；季度快照归 [`openalex_snapshot`](bulk-snapshot.md#openalex_snapshot)；serves `openalex`；W2；platform_bridge / platform，sunset V2 出口。

**2 通道与操作**：metadata：`lookup`（按 DOI 批量，enrich 舱壁）、`probe`；不做增量；platform。

**3 上游接口事实**：100 req/s，超限或预算用尽返回 429 [https://help.openalex.org/api-reference/authentication, 2026-09-30]；日预算无 key $0.10、免费 key $1；列表 + 过滤 $0.10/千次，单实体免费 [https://help.openalex.org/access/example-costs/, 2026-09-30]；`per_page` 上限 100，200 已弃用 [https://help.openalex.org/api/paging/, 2026-09-30]；`from_created_date` 返回 429"Plan upgrade required"[实测 https://api.openalex.org/works?filter=from_created_date:2026-09-28, 2026-09-30]；key 经 `api_key` 参数或 Bearer 头 [https://help.openalex.org/api-reference/authentication, 2026-09-30]。

**4 请求声明**：`openalex.works_list`（`filter=doi:` 批量，request_class `list`，`hosts_touched: [api.openalex.org]`）；key 为 `AuthRef(deployment/openalex)`，网关按 Bearer 头注入；`budget{account: openalex.usd, unit: usd}`（与 [aggregator-api.md](aggregator-api.md) 目标形态同名）；`status_overrides`：429 且正文含 `Plan upgrade required` → `config`，预算耗尽的 429 → `budget_exhausted`；v1 的 402 → `RATE_LIMITED` 作废，改记 `budget_exhausted`（未核，同 [aggregator-api §2.6](aggregator-api.md#26-状态码覆盖与身份参数)）；两种 429 靠正文区分（未决 2）。

**5 游标与增量**：无；增量由快照 `updated_date` 分区与 Crossref 兜底（见 [openalex_snapshot](bulk-snapshot.md#openalex_snapshot)）。

**6 映射**：OpenAlex W 只作 `work_assertion`；`abstract_inverted_index` 按摘要权利判定；OA 位置与 Unpaywall 同源，不作独立票。

**7 SCD**：lookup native，每批 ≤100 个 OR 值、URL 编码后 ≤2000 字符（后者为工程惯例）；不声明 `search`。

**8 合规**：数据 CC0；`background`；⚑BUDGET 进美元账本。

**9 全文**：`best_oa_location` 只作 `oa_link` 候选；content 下载不作依赖。

**10 测试**：v1 8 个 fixture；补付费门控 429、预算耗尽 429、`corpus` 计数差。

**11 探针与替补**：响应头名与 `cost-usd`、门控错误文案、`meta.count` 日变化；替补快照与 Crossref。

**12 运维**：日预算用量 ≥80% 告警；`budget.py` 熔断并入网关账本。

**13 已知坑与待决**：同一把 key 在 personal 部署的归属（契约待拍板 P-8）。

### repec_redif

**1 身份**：v1 `repec` → `bulk_snapshot`（形态见 [bulk-snapshot.md §6.4](bulk-snapshot.md#64-桥接连接器的本族目标形态主卡在-v1-bridge)）；serves `repec`，经其代收 cepr、iza、mpra、cesifo 等系列；W2；platform_bridge / platform（v1 零网络 join 在生产运行，快照取回改经网关），sunset V2 出口。

**2 通道与操作**：metadata：`snapshot_import`、`lookup`（本地 join）；platform。

**3 上游接口事实**：rsync 模块 `rsync://rsync.repec.org/RePEc-ReDIF/` 等 [http://rsync.repec.org/, 2026-09-30]；OAI 自称"sometimes flaky"，实测 Identify 502；不建议抓网站；"Non-commercial use assumed" [https://ideas.repec.org/getdata.html, 2026-09-30]。

**4 请求声明**：v1 在 `src` 外脚本取快照，改为 `SnapshotSpec` 经网关流式模式，`hosts_touched: [rsync.repec.org]`；rsync/FTP 须网关扩展协议（待拍板）。

**5 游标与增量**：`snapshot_release`（档案文件清单与校验和）；删除以模板消失表示（推断，未核），周期全量对账。

**6 映射**：v1 `parse.py`（462 行）复用为 mapper；句柄 `RePEc:<archive>:<series>:<id>`；DOI→handle 必须单射（D-036，属性测试）；扩映射范围须新 ADR。

**7 SCD**：`snapshot_import` native；lookup 只查本地；成本为 rsync 差量流量。

**8 合规**：官方 bulk 通道；非商用默认，建议补 ⚑COMM（待拍板），经 repec 代收的来源连带。

**9 全文**：无；`File-URL` 只作外链。

**10 测试**：v1 3 个 fixture 与 socket 零网络专测；补各目标系列 ReDIF 模板（多作者、多 `File-URL`、`Publication-Status`）。

**11 探针与替补**：rsync 可达、目标系列模板数周环比、OAI Identify；替补 Crossref（有 DOI 的系列）、EconBiz。

**12 运维**：快照超 30 天告警，文案写明天数与刷新命令（D-035）。

**13 已知坑与待决**：v1 对 robots 仍不可判读的主机（如 `repec.nber.org` TLS 中断）放行 ≤4 次请求，与 RFC 9309 §2.3.1.4"假定全禁"不符（L8），不继承；"核 A 域不外推 B 域"保留；已核句柄 `nbr:nberwo`、`cpr:ceprdp`、`iza:izadps`、`ecb:ecbwps`、`imf:imfwpa` [各 IDEAS 系列页, 2026-09-30]。

### dblp_drops_snapshot

**1 身份**：v1 `dblp`（在线路径，D-037 已出列）→ 新写 `bulk_snapshot`；v1 代码不加载，不计入 AC-V1.15；serves `dblp`；W2；snapshot_rewrite；工作量按新写估。

**2 通道与操作**：metadata：`snapshot_import`；按需小查询归 `dblp_sparql`；platform。

**3 上游接口事实**：月度 XML 快照 DOI `10.4230/dblp.xml.YYYY-MM-01`，2026-09-01 版 12,928,181 条、CC0 [https://api.datacite.org/dois?query=id:10.4230/dblp.xml.*, 2026-09-30]；下载件 1,099,942,087 字节，附 `.md5` [https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/dblp-2026-09-01.xml.gz, 2026-09-30]；`dblp.org` robots `Disallow: /` 且具名禁 Claude 类 UA [https://dblp.org/robots.txt, 2026-09-30]；DROPS robots 未禁 `/storage/` [https://drops.dagstuhl.de/robots.txt, 2026-09-30]。

**4 请求声明**：`dblp.datacite_releases`（发现）、`dblp.drops_xml`（`stream: true`）；hosts `api.datacite.org`、`drops.dagstuhl.de`。

**5 游标与增量**：`snapshot_release`（月），相邻两版 dblp key 差集得增删改。

**6 映射**：`parse_volume_xml` 可复用于子集解析（推断）；dblp key 为作品级辅助标识。

**7 SCD**：`snapshot_import` native；成本为每月约 1.1 GB。

**8 合规**：dblp 三个主站零请求（D-050）；DROPS 按快照周期 `background`。

**9 全文**：无；`ee` 只作外链。

**10 测试**：DataCite 快照列表、快照头部与截断样本、md5 校验失败。

**11 探针与替补**：DataCite 最新快照日期（超 40 天告警）、`Content-Length` 与 `sizes` 一致；替补 RDF 快照或自建 QLever 镜像。

**12 运维**：每月 2–3 日后导入；导入失败次日重试一次。

**13 已知坑与待决**：1.1 GB gz 须流式解析；解除 D-037 出列须新 ADR。

**6.3 metadata-only 与 P1（紧凑卡）**

### ssrn_crossref

**1 身份**：v1 `ssrn` → `crossref_delegated` 的 `ssrn` 实例（`ssrn_abstract_id` 旗标）；v1 模块顶层导入浏览器依赖，不加载（长稿 D-051 第 3 条）；实例上线后本 id 转 `CLX`；W2。

**2 通道与操作**：metadata、latest 经 Crossref 前缀 10.2139；fulltext 只外链；站点零请求。

**3 上游接口事实**：2026-08-01 以来 54,329 个 DOI，75.1% 的 license 指向 USPTO 版权说明页 [https://api.crossref.org/prefixes/10.2139/works?filter=from-created-date:2026-08-01&rows=0&facet=license:*,type-name:*, 2026-09-30]；Data Feeds 等商业产品 2026-12 关闭（二手）。

**4 请求声明**：只经 `crossref_delegated` 的 prefix 端点（single 池），共用 Crossref 桶；`*.ssrn.com` 不进 `allowed_hosts`。

**5 游标与增量**：同 `crossref_delegated`（created 轴；`from-posted-date` 为 0，长稿）。

**6 映射**：`ssrn_abstract_id` 抽 `abstract_id`，DOI 中缀不是 `ssrn.` 时只计观测；`version_claim` wp。

**7 SCD**：继承实例；不声明 `search`。

**8 合规**：USPTO 链接映射为保留所有权利、不共享；CC 许可也不解除 ToU，全文仍只外链；⚑DRIFT。

**9 全文**：`open_in_tab`（落地页外链），`Delivery.cfm` 等易失 URL 不入库。

**10 测试**：v1 6 个 fixture 转为实例 fixture；每种 license URL 各一条。

**11 探针与替补**：license 分面比例、日新增量；替补 OpenAlex。

**12 运维**：随 `crossref_delegated` 实例。

**13 已知坑与待决**：`facet=created:*` 返回 400 的 v1 教训保留（L23）；实例细节以 [crossref-delegated.md](crossref-delegated.md) 为准。

### s2_api

**1 身份**：v1 `s2` → `aggregator_api`（mapper）；Datasets 归 `s2_datasets`；serves `s2`；W3；family_config / replay_only。

**2 通道与操作**：metadata：`lookup`（`POST /graph/v1/paper/batch`）；platform。

**3 上游接口事实**：有 key 1 RPS（全端点），key 不得共享 [https://www.semanticscholar.org/product/api, 2026-09-30]；API 许可须署名、不得再分发，商用未明文 [https://www.semanticscholar.org/product/api/license, 2026-09-30]；batch ≤500 id、`fields` 为查询参数（长稿与 swagger）。

**5 游标与增量**：无。

**8 合规**：⚑COMM；署名由来源字段渲染（HC-24）；无 key 时运行器短路为 `config`、不发请求（与 v1 同）。

**10 测试**：v1 7 个 fixture（契约原 skip）；补 null 元素、429、匿名 404。

**11 探针与替补**：swagger 路径数、许可页日期；替补 OpenAlex。

### unpaywall_api

**1 身份**：v1 `unpaywall` → `aggregator_api` 兼容层；serves `unpaywall`；W2（实施计划调整）；platform_bridge / platform，sunset V2 出口。

**2 通道与操作**：OA 定位：`lookup`（按 DOI）；platform。

**3 上游接口事实**：`https://api.unpaywall.org/v2/{DOI}?email=`，email 必填，非 Crossref DOI 返回 404；已并入 OpenAlex 数据库，官方称不退役 [https://help.openalex.org/access/unpaywall/, 2026-09-30]；10 万次/日（二手）。

**5 游标与增量**：无。

**8 合规**：`email` 为部署联系邮箱，走 `identity_param` 由网关注入（aggregator-api U-2 待契约确认）；与 OpenAlex 同源，不作独立票。

**10 测试**：v1 12 个 fixture；404 记未找到、422 → `config`。

**11 探针与替补**：固定 DOI 的 `best_oa_location`；替补 OpenAlex。

## 7. 本族风险、坑与待决

### 7.1 v1 教训与 v2 落点

编号取第一阶段 C 调研 §6（L1–L30，出处为 `archive/v1` 代码与 ADR）。

| 教训 | v2 落点 |
|---|---|
| L1–L4 域名、slug、迁域、页面分代 | 不拼猜测 key；资产 URL 只取带内值；分代走"解析分支 + quirk 逃生"，未知组合记 `config` 或 `parse` |
| L5 合法空与解析失效混淆 | `Expectation.empty` 按端点声明；探针盯 200 空体与计数骤降 |
| L6 OAI datestamp ≠ 发表日 | 游标声明语义；首次全量基线；冷启动进契约测试 |
| L7–L10 robots 读法与不可读处置 | RFC 9309 最长匹配、4xx 无限制、5xx 与网络错误全禁；v1 对不可判读主机放行 ≤4 次的做法不继承 |
| L11–L14 挑战与冷却 | 头级挑战判定先于状态映射；特征库单一源；冷却按主机、先于族分支 |
| L15–L16 状态语义因源而异、头不回传 | `status_overrides` 数据化配 fixture；垫片补回 `PageSignals` |
| L17、L28 执行与协议耦合、duck-typed 接口堆积 | 执行权收回网关，可选能力在清单声明（本族垫片） |
| L20–L22 凭证隔离靠自律、缺凭证两种语义 | 凭证只由网关或端侧按作用域注入；"未配置"与"失效"分成两个 UI 状态 |
| L24 实现完整却零接入（dblp、wiley） | 注册表接线检查：启用的连接器至少被一条通道引用 |
| L27 v1 healthcheck 的探测样本用合成锚点 | `canary_query` 样本须先实测存在 |

### 7.2 风险

- 7 个平台桥接集中在 W2 且须在 V2 出口前移植；过期降 CL2 后能否继续后台收割取决于契约 P-4，计划代理应把移植排在 V2 前半。
- v1 同步代码占 worker 线程池，须独立舱壁（容量未核）。
- v1 fixture 录于 2026-07，移植时按新政策重录。

## 怎么验收

- 20 个 connector_id 都有卡片（本文 7 张，目标族 13 张），与 E 清单一一对应，各写明 `destiny`、`port_target`、`sunset_by`。
- B1–B8 与 §4.1 适用项在离线 CI 全绿；AC-V1.15（除 dblp 在线通道、SSRN 外全部经桥接通过契约测试）以 B6 报告为证据。
- 7 个平台侧桥接 V1 出口达 CL3；V2 出口全部 `impl: v1_bridge` 版本退役（并入族实例或拆分的 id 为 `CLX`），移植件过 B8。
- 静态检查：平台模式清单无 `fetch_asset` 路径、无 cookie 与用户凭证绑定，`allowed_hosts` 不含 `export.arxiv.org`、`dblp.org`、nber.org 各主机；`replay_only` 清单 `auth` 为 `null`、不进网关白名单；`conformance.rules` 中 `exempt` 只出现 `declarative_plan`。

## 未决事项

1. 卡片归属：13 张在目标族、7 张在本文（aggregator-api、crossref-delegated、bulk-snapshot 指向本文）；移植完成后本文的卡迁往目标族，矩阵锚点随之更新。
2. 新增字段（须契约确认）：契约 §17 已含 `v1{adapter, destiny, mode, port_target, sunset_by, parts[]}`，本文另补 `v1` 的 `venues`、`connector_params`、`expected_diffs`、`key_order`、`stage_default`、`meta_keep`、`legacy_fixtures`、`exemptions`（只许 `declarative_plan`）与 `endpoints[].stream`；去向值已统一为契约 §17 的 `user_side`（旧稿 `to_pc_agent`、`user_side_only` 作废，目标族卡片已改）；openalex 两种 429 须按正文区分，`status_overrides` 须补正文匹配字段。
3. NBER 条款：`nber_site`（及 site_special 的 `nber_conference_pages`）平台侧与用户侧一律暂停（CL0），取得 NBER 书面许可前不排波次（待拍板）；RSS 增量取消，影响 `nber_wp` 的 v2-P0 验收口径与名录"RSS 增量"写法。
4. OpenReview 用户侧"本人 token 查询"没有契约载体（同 site-special 未决 4）：随待拍板 P-13（`QueryRecipe`）定，拍板前停在 CL0，只给 `open_in_tab`。
5. RePEc 快照要 rsync/FTP，网关只定义了 HTTP(S) 流式；另建议补 ⚑COMM。
6. connector_id 修正：`aea_fulltext_user` 建议并入 `atypon_user` 实例；`aaai_ojs_oai`、`ssrn_crossref`、`econsoc_fulltext`、`nber_site` 并入或拆分后转 `CLX`；E 清单把 aea、econsoc、nber 的目标族记为 `site_special`，与该族平台侧定义不符。
7. 用户侧桥接的 `sunset_by`（已统一）：桥接版只回放，`sunset_by` 取 V2 出口，届时退役；同一 id 的配方 V3 出口达 CL3。platform-family（PF-Q5）与 official-tdm-api（OT-Q1）已按此改写；实施计划未决中的"待统一"一句可撤。
8. `ssrn_crossref` 不加载 v1 代码（长稿 D-051 第 3 条）与 AC-V1.15"只排除 SSRN 全文模式"的措辞待统一。
9. `pc_agent` 模式是否保留（长稿 §14.1 让 `user_side_only` 过渡期以 `pc_agent` 运行，本文与契约改为 `replay_only`）；PMLR 改用 feed 发现、arXiv 平台侧不用查询 API 与长稿不同，列入名录复勘。
10. 同一 `connector_id` 的 0.x 桥接版与 1.0.0 移植版：本文按"MAJOR 升级、桥接版退役"处理，与契约 §14、§17"bridge 转 CLX、id 永不复用"的衔接待契约确认（同 aggregator-api U-3）。
11. `window_set` 按期键（`IssueRef`）记完成单元，契约 §6 只有日期区间；须补"期键"形态，或改用 `seq`（卷号）与 `repo_commit`（ACL）。
12. v1 读时钟处的 CT-01 测法（夹具替换而非抛错）待一致性文档确认；不获确认则桥接补丁改读注入时钟。
13. [实施计划](../implementation-plan.md)口径待统一：其 CN-6 记 `repec_redif`、`unpaywall_api` 在 W2 直接写成快照或族实例（本文为平台侧桥接）；其 CN-7 仍把 `nber_site` 列入 W3u 用户侧 11 个（1.5 人日暂列），本文按暂停口径不排波次。
14. 卡片小节标签本文已统一为 `**1 身份**：` 形式（原 `1. **身份**：` 编号列表）；按[卡片模板](../connector-card-template.md)，V0 起以 `card render` 的输出为准；§6 的三级标题只写 connector_id，分组用粗体行。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–5.4 `V1Bridge`、§14.1–14.2 去向与模块复用、§15.1 fixture 复用）；v1 协议与代码见 `git show v1-final:src/paper_crawler/adapter.py` 与 `src/paper_crawler/adapters/`；归档说明见 [docs/archive.md](../../../../archive.md)；通用协议见 [契约](../contract.md)，里程碑见 [09](../../09-roadmap-and-milestones.md#v1-语料底座与-p0-来源)。
