---
title: 连接器一致性等级与测试规范
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 连接器一致性等级与测试规范

> 本文回答：连接器怎样证明合格、合格到什么程度可上生产、证明失效怎么办，测试、fixture、评审与 CI 各守哪一道。结论：一致性等级 CL0–CL3/CLX 是会过期的证明，每级有进入门和保持条件，失效由控制面自动降级，晋级只经 PR；CL 同时是策略上限，CL0/CL1 在生产为 deny。离线层（12 条通用契约测试、按"实例 × fixture"参数化的族套件、属性测试、黄金 NormRecord）全在无网沙箱里跑。fixture 只经 staging 网关录制并脱敏，受版权正文与个人数据不入库。第二人合规复核是 CL0 出口，除取合规证据外的任何真实请求（含 dry-run 录制）都在它之后。

## 要点

- **五级**：CL0 登记 → CL1 离线一致 → CL2 灰度 → CL3 生产，另有 CLX 退役；声明等级 `conformance.declared` 在清单，生效等级 `cl_effective` 只在 ops 层。
- **`declared` 只经 PR 升；`cl_effective` 自动降，人经管理 CLI 恢复且不超过 `declared`**（§11）；CL 同时是策略上限 `cap_conformance`，只收紧、不放宽。
- **CT-01…CT-12** 是 CL1 的核心，其中 4 条硬边界项永不可豁免；P0 连接器的 CL1 规则一律不可豁免。
- **fixture** 只经 staging 网关 `record` 模式录制、脱敏、带来历，满 12 个月或上游结构变化时重录。
- **三道评审门** G1 合规、G2 技术、G3 上线，分别对应 CL0 出口、CL1→CL2、CL2→CL3。
- **在线测试显式门控**，失败不阻断合并；生产由探针与 `canary_query` 持续核对。

## 1. 一致性等级

### 1.1 进入门与保持条件

保持条件逐级累积（高一级也须满足低各级的保持条件）。

| 等级 | 进入门（经 PR 声明） | 保持条件 | 生产上限 |
|---|---|---|---|
| CL0 登记 | SourceSpec、ConnectorManifest、卡片与证据齐全；注册表 lint 13 条与连接器 lint LC-01…LC-06 通过。**出口 G1**：第二人合规复核签字写入 `conformance.compliance_signoff`，作者不兼任 | lint 通过；签字与现行合规结论匹配 | deny；签字前只许经网关取证据的自描述请求（robots.txt、OAI `Identify`；用户申请的来源先过 O7 审核，通过前连 robots.txt 也不取，见 03），签字后放行小额度 dry-run |
| CL1 离线一致 | G1 签字有效；CT-01…CT-12 与族套件全过；四类 fixture 与黄金齐全；卡片由清单重新生成且一致 | 所部署版本的每日回放为绿 | deny（只许回放与 dry-run） |
| CL2 灰度 | G2 通过；staging 按当前策略许可的模式真实运行，P0 连续 ≥14 天、其余 ≥7 天；探针全绿；零 robots 违例、零挑战、零未声明主机、零 needs_confirmation 通道后台批量；FetchLog 每行有 `decision_id`；新鲜度、错误率与 shadow 差异（有可比对象时）达标；合规复核仍有效 | 探针连续红灯 ≤72 小时 | 待拍板 P-4：`on_demand` 或 deny |
| CL3 生产 | G3 通过；替补链与急停演练；runbook（含游标迁移、"重置 + 回填"、合规预案）；SLO 与告警；`owner` 与 `backup_owner` 在岗（P0 两人） | 复核未超 `review_every`；v1_bridge 未过 `sunset_by`；owner 在岗 | 不设限 |
| CLX 退役 | `lifecycle: retired`；移出路由，停止调度 | — | deny；保留清单、fixture、黄金与来历，id 不复用 |

- **staging 不是生产**：G1 签字有效的 CL1 连接器可进 staging 观察，CL2 证据由此而来；staging 与生产共用策略引擎与网关，`cap_conformance` 只管生产。只许按需的通道（如 ⚑ROBOTS）按 `on_demand` 跑满天数即可，不必后台批量（HC-31）。
- **签字随合规结论走**：改动 SourceSpec 合规结论的 PR 须带新签字（CI 校验），签字因此不会在生产中静默失效；`verified_at` 续期不算改动。
- **族引擎与实例**：实例继承引擎的 CL1 证明，只补自己的 fixture 与 `canary_query`；CL3 引擎的新增实例在 staging 跑几天，待拍板 P-11（建议 ≥3 天）。实例带来新来源或新主机时仍须过 G1 才 dry-run；SOP A、B 的 ≤30 分钟只计作者工时。
- **用户侧 RecipeProvider**：CL1 另加配方 schema 与解释器对抗测试（长稿 §15.9）；CL2/CL3 的证据来自维护者合成检查（P-7，待 08 认可）与用户自愿工单；回执不进任何跨用户统计。

### 1.2 计算口径

- **规则化**：条件拆成带编号的规则，记在 `conformance.rules{<rule_id>: done | exempt{reason, approved_by} | todo}`。编号：注册表 lint `L1`…`L13`；连接器 lint `LC-01`…`LC-06`，依次对应 [contract](contract.md) 的连接器 lint ①–⑥；契约测试 `CT-01`…`CT-12`；族套件 `FS-<族缩写>-NN`（各族文档 §4，个别族前缀不一，见未决）；staging 条件 `ST-NN`；上线条件 `OP-NN`。
- **CI 推导**：CI 推出可达的最高级，与 `declared` 不符即失败。规则是否适用、严格度高低，都由 CI 按清单、`serves` 的 `v2_status` 与替补链推导，不另设字段；对不适用的规则写 `exempt` 算 lint 错误。
- **运行态不进 YAML**（contract §2）：`cl_effective`、rollout、health、急停只在 ops 层，与策略模式合成 `EffectiveStatus`。
- **上限取最小值**：`cap_conformance` 与五类信号上限、其他结构性上限一起取最小值（[03 策略引擎](../03-sources-and-corpus-pipeline.md#策略引擎与漂移探针)）。被它拦下的任务记 `TaskOutcome.status=denied` 与 `policy_denied`，零请求。

### 1.3 与 `v2_status`、`support_tier` 的对应

`v2_status` 是产品承诺，决定目标与时点；CL 是证明状态。未达目标只在进度与[实施计划](implementation-plan.md)里报告，不自动改名录。连接器服务多个来源时取最高一档。

| 名录口径 | 目标 CL | 时点 | 严格度 |
|---|---|---|---|
| `v2-P0`（支持） | CL3 | 平台侧 V1 出口，用户侧 V3 出口 | high |
| `v2-P1`（支持） | CL3 | V3、V5 两批（[实施计划](implementation-plan.md)） | low；P0 替补链上的为 high |
| `v2-P2`（支持） | 按需 ≥CL2 | W4，用户需求触发 | low |
| `metadata-only（Px）`（支持） | 只要求元数据通道达所属优先级的目标 | 按登记优先级 | 同所属优先级 |
| `support_tier=登记` | CL0，通道全部不启用 | 不排波次 | — |
| 不接入（`excluded`、`link-only`、`user-import-only`） | 无连接器；已有的转 CLX | — | — |

登记来源证据过期只标 `review_overdue`、不降级，lint 的证据时效规则只对"支持"生效（细化 D-073，待拍板）。逐行对应见[连接器矩阵](../../../catalog/connector-matrix.md)。

## 2. 测试分层与严格度

### 2.1 分层

沿用 v1 六类测试（T1–T6）与"离线全绿才合并、在线失败只开工单"的纪律，按网关架构重排：

| 层 | 内容 | 网络 | 运行与阻断 |
|---|---|---|---|
| S0 静态（CL0） | JSON Schema、注册表与连接器 lint、依赖禁表与 import 规则、卡片一致 | 无 | 每个 PR，阻断 |
| S1 离线（CL1） | 单元（`parse`、`normalize`、quirk、标识符规范化）；CT-01…CT-12；族套件；属性测试；全量回放；黄金与版本门 | 无网沙箱 | 每个 PR 与 main 每日，阻断；引擎改动全实例回放 |
| S2 平台不变式 | 网关 robots 先行、令牌桶键、挑战冷却、同键串行、幂等提交、六段回放（长稿 §15.4、§15.6） | 本地 mock 与 PG | 平台 PR 阻断；是连接器 CL1 的前提 |
| S3 staging 观察（CL2） | 真实上游，经 staging 网关 | 真网 | 持续，不阻断 |
| S4 探针（CL2、CL3） | ProbeSpec 与 `canary_query` | 真网 | 按 schedule，驱动降级 |
| S5 在线 smoke | 显式任务（§7） | 真网，经 staging 网关 | 手动，失败开工单 |
| S6 合规审计 | FetchLog 抽查、robots 快照先于请求、许可闸抽样 | 查询 | 每周 |

### 2.2 严格度与豁免

借 Airbyte 的 `test_strictness_level` 与 `bypass_reason`：GA 连接器须 `high`，跳过须写理由 [https://docs.airbyte.com/platform/connector-development/testing-connectors/connector-acceptance-tests-reference, 2026-09-30]。

- **硬边界项永不可豁免**（守 03、08 硬边界；与"红线"禁表不同义）：LC-01…LC-06、CT-01、CT-03、CT-10、CT-12 与 §4 的 fixture 政策。
- **high**：适用规则全部 `done`，CL1 规则不得 `exempt`；CL2、CL3 条件的 `exempt` 须部署方负责人批准。
- **low**：硬边界项以外的 CL1 规则可以 `exempt`，如罕见权利类暂无真实样本（CT-06 部分覆盖）。
- **每条 `exempt`**：写明为何不能做、何时补；`approved_by` 不是作者；随 `review_every` 复核，G2 逐条过目。`todo` 只能出现在高于 `declared` 的等级。

## 3. 通用契约测试（CL1）

PlatformConnector 全部必过；RecipeProvider 适用 CT-01、02、03、05、08、10、11、12 与配方专项（CT-10 按 contract §11 占位符规则判）。族文档的 ①–⑫ 即 CT-01…CT-12。★ 为硬边界项。

| rule_id | 断言 | 手段与所需 fixture |
|---|---|---|
| CT-01 ★ 零 I/O | `plan`、`parse`、`normalize`、`describe`（RecipeProvider 为 `recipes`、`locate_fulltext`）不碰 socket、系统时钟、环境变量、文件、随机源；包内不导入 HTTP、浏览器自动化、TLS 指纹、验证码类库 | 沙箱把入口换成抛错；依赖禁表 |
| CT-02 确定性 | 同一 fixture、同一 `ctx.now` 跑两次，RequestSpec 序列与 NormRecord（RecipeProvider 为 `FulltextRecipe` 与 `FulltextOption`）逐字节相同；`idempotency_key`、`payload_sha256` 稳定，`volatile_fields` 不入哈希 | 全部 fixture 双跑 |
| CT-03 ★ 用户无关 | 不同用户上下文下 RequestSpec 序列相同，RecipeProvider 的 `recipes`、`locate_fulltext` 输出相同；`ConnectorTask` 无 `user_id` | 两个合成用户上下文对跑 |
| CT-04 游标属性 | 页内页间乱序、每个 Step 边界注入崩溃、每页注入令牌过期：并集等于真值，已提交游标不越过未落库数据；`cursor_expired` 重启 ≤2 次后 stopped；`stale_decision` 与预算耗尽停在页边界；剩余请求额度为 1 时网关遇 `transient` 不再重试，总尝试数不超 `max_requests`；远未来游标零记录、不崩；`bounds` 开闭边界日各有样例 | 属性测试 + 乱序、过期、边界 fixture |
| CT-05 矩阵覆盖 | `endpoints[].status_overrides` 每行、`Expectation` 七个字段的每个分支各至少一个 fixture；可能产出的每个 `error_class` 都有触发路径 | fixture `covers` 与清单求差为空 |
| CT-06 黄金覆盖 | 黄金覆盖每个 `identifiers_emitted` 方案、每种权利类、tombstone 与撤稿；许可、权利、版本、关系字段带 `basis`；mapper 不直接给 `shareable` 等 HC-07 字段 | 逐字段比对 |
| CT-07 SCD 一致 | `describe()` 重生成差异为 0，`derived_from` 哈希匹配 | CI 重生成 |
| CT-08 版本门 | 黄金变而 `mapper_version` 未升、游标 kind 或编码变而 MAJOR 未升、RecipeProvider 的配方内容变而 `(recipe_id, version)` 未升，一律失败；MAJOR 游标变更须有以旧 CursorEnvelope 测过的 `migrate_cursor`，或声明"重置 + 回填窗口" | 与上一版清单、黄金对比 |
| CT-09 有序声明 | 声明 `ordered_by` 须有 `ordered_fixture` 与乱序反例，回放按序检查；`Page.next_cursor` 只在安全提交点非空 | 有序件 + 反例 |
| CT-10 ★ 边界纪律 | 请求头只含 `AllowedHeader`，无 UA、Cookie、Authorization、`personal_params`；`auth` 只有 `deployment/*`；请求主机与重定向落点 ⊆ `allowed_hosts`；robots 例外只来自 decision；挑战即终止、正文不交 `parse`、重试 0；伪成功与空体归类正确 | mock 网关双向断言（请求都被期望，期望都被命中） |
| CT-11 黄金决策行 | 每个"来源 × 通道 × 操作"在策略引擎黄金决策表中有期望决定，含闸门与 `cap_conformance` | 长稿 §15.3 表驱动 |
| CT-12 ★ fixture 扫描 | 无 key、cookie、邮箱、JWT、签名参数；受版权正文与 B 类摘要已换合成文本；无个人数据 | §4.4 扫描器 |

## 4. fixture 政策

### 4.1 四类与必备件

按长稿 §15.1：① 正常页；② 空页或 200 空体；③ 限流或错误，含 arXiv"HTTP 200 + `Rate exceeded.`"、bioRxiv `/details` 200 空体等伪成功；④ 边界：最后一页、resumptionToken 或 cursor 过期、删除记录、版本变化、DOI 前缀归属变化。必备件另有：`ordered_fixture` 与乱序反例、CT-05 覆盖件、每个 quirk 旗标、tombstone 与撤稿。

### 4.2 形态

fixture 是 (RequestSpec, Response) 对，不是连接器进程里的 HTTP 录像，连接器侧不 monkeypatch HTTP 库。

```yaml
# 设计伪代码 —— fixture 元数据（路径与格式由 V0 冻结）
fixture_id: epmc.empty_legit     # 与 contract 清单示例同名
class: empty                  # normal | empty | error | boundary
covers: [expect.empty, cursor.bounds.until]
provenance: staging_gateway   # staging_gateway | handwritten_synthetic | v1_import
recorded_at: 2026-10-02T03:00:00Z
decision_id: dec_0001
connector_version: 0.1.0
request: {endpoint_id: europe_pmc.search, params_digest: "sha256:…"}
response: {status: 200, headers: {Content-Type: application/json}, body_file: epmc.empty_legit.body.json}
redactions: []                # 空页无可替换；有记录页如 [body.abstractText]
```

前两个 `provenance` 值与清单 `fixture_policy.recorded_via` 相同；`v1_import` 用于 v1_bridge 回放与移植对拍。合成件须写明原因（v1 的 `SYNTHETIC` 注释改为机读字段）；用户侧 fixture 一律手写合成。

### 4.3 录制

- **只经 staging 网关 `record` 模式**：与生产请求同走 robots 先行、策略引擎、令牌桶与挑战检测，被拒的来源不录；不在开发者机器上直连上游。录制器进 V0 SDK（v1 的录制器计划了却没实现）。
- **前提**：G1 签字有效；小额度 dry-run 预算计入全局配额账本。
- **落盘**：先进不入库的暂存区，过目后提交；重录整组替换，不追加 [https://github.com/kiwicom/pytest-recording, 2026-09-30]。

### 4.4 脱敏与扫描

- **响应头**只留 `Content-Type`、`Content-Encoding`、`ETag`、`Last-Modified`、`Retry-After`、`Date` 与清单声明的限速头；`Set-Cookie`、`Authorization`、会话与追踪头删除。
- **查询参数** `api_key`、`apikey`、`key`、`token`、`mailto`、`email` 与签名参数（`signature`、`sig`、`key-pair-id`）换占位；敏感键表复用 v1 `sensitive.py`。
- **正文**：受版权全文与 B 类摘要换成等长合成文本，保留结构，`min_bytes`、`root` 照常可测；二进制只用合成最小件。
- **个人数据**：联系邮箱、电话、会话与用户数据不入库。作者姓名、ORCID 属公开书目元数据，来源元数据许可允许再分发（如 CC0）时保留，否则换合成值。
- **入库前扫描**（CT-12）：命中 key、cookie、邮箱、JWT、签名参数或超长正文即阻断；全文类端点的正文必须带合成标记。

### 4.5 存放、过期与黄金

- **存放**：按 `connector_id`（实例再分 `<instance>`）分目录，元数据、正文、黄金并列，路径由 V0 定；清单 `fixtures[]` 列 id，卡片 §10 由此生成。fixture 随仓库分发，只含可再分发的元数据与合成文本。
- **过期**：满 12 个月重录；结构探针报警、出现 parse 隔离页或 deprecation 公告时提前重录。过期只冻结晋级并开工单，不改 `cl_effective`；结构真变了，由探针红灯走 CL2 保持条件。
- **黄金纪律**：沿用 v1，`UPDATE_GOLDEN` 写入后本次测试仍判失败，须人工看 diff 再提交。黄金任一变化即递增 `mapper_version`，PR 附新旧 mapper 的字段级 diff。
- **`canary_query` 样本**须先经真网核实存在，合成锚点不能当判据（v1 教训 L27）。

## 5. 族一致性套件

- **自动发现与参数化**：从注册表发现实例，不维护手写花名册（v1 教训 L30）；按"实例 × fixture"参数化。新增实例只交 YAML、fixture 与黄金，不写测试代码；引擎改动全实例回放，每实例目标 <2 秒（未核）。
- **quirk 旗标**：实例只能打开引擎已登记的旗标，每个旗标至少一个 fixture；新怪癖进引擎或升 `site_special`。
- **零代码实例内嵌用例**：借 Zotero 译者的内嵌测试用例 [https://www.zotero.org/support/dev/translators/testing, 2026-09-30]，SOP A、B 的实例在 YAML 旁放最小 `tests`（窗口、计数下限、关键字段），由 dry-run 生成、人工审定。
- **族专有测试**写在各族文档 §4，例如 [oai-pmh](families/oai-pmh.md) 的 Identify 结构基线与 `noRecordsMatch` 作合法空，[bulk-snapshot](families/bulk-snapshot.md) 的 manifest 闸，[crossref-delegated](families/crossref-delegated.md) 的请求类与 `x-api-pool` 对账。

## 6. 属性测试与回放

- **游标**：随机生成页序列、乱序、崩溃点与过期点，断言中断续拉等于一次跑完、无重复、提交游标不越界（CT-04）；有序声明的校验借 Meltano 的 `is_sorted`/`check_sorted` [https://sdk.meltano.com/en/latest/incremental_replication.html, 2026-09-30]。
- **规范化**：标识符规范化幂等；快照族的标识映射必须是单射（v1 RePEc `w{n}`/`t{n}` 塌缩教训）。
- **可复现**：记录随机种子，失败样例固化为 fixture。
- **回放**：全部 fixture 每日回放（CL1 保持条件）；v1_bridge 另以 v1 fixture 回放，须与 v1 产出语义等价。

## 7. 在线测试的显式门控

- **显式任务**：带 `online` 标记，默认排除；需要部署联系邮箱 `CONFLUO_CONTACT_EMAIL`（命名待 V0 定；v1 为 `PAPER_CRAWLER_CONTACT_EMAIL`）；浏览器路径另设门控 `CONFLUO_BROWSER_TESTS`（命名待 V0 定；v1 为 `PC_BROWSER_TESTS`）。
- **经 staging 网关**：前提同 §4.3（G1 签字有效）；计入全局配额账本（v1 教训 L29），只对 `on_demand` 或 `background` 模式的通道运行。
- **限量交叉核验**：G1 之后的评审可授权每个连接器 ≤5 次真网请求核对真实结构（v1 pmlr 审查做法）。
- **失败不阻断合并**，但必须开工单：站点漂移不等于代码错误。

## 8. 探针、`canary_query` 与发布

- **ProbeSpec**：`kind ∈ robots | tos_hash | tdmrep | structure | deprecation | canary_query | count`；每条 `upstream_facts` 至少对应一个探针；探针同样经网关、在调度时取 decision，结果只写 ops。
- **`expectation` 按 kind**（contract 交本文定义；设计伪代码，字段待 V0 冻结）：`robots`、`tos_hash`、`tdmrep`、`structure`、`deprecation` 比对上次快照（哈希、判定、字段集合、版本号或弃用信号）；`canary_query` 取 `{query, n_min, sample_fields}`；`count` 取 `{baseline, max_drop}`；放宽类变化只告警，不自动放宽。
- **`canary_query`**：用真网核实的已知答案，断言计数不低于基线、抽样字段完整、venue 解析命中；P0 通道每日一次。HTML 类 `site_special` 另须结构契约探针与按会期的期望计数。计数骤降（`canary_query` 或 `count` 探针，contract §7、§10）判 `empty_body/count_drop`，端点降级并切替补链。
- **过期**：技术事实过期只冻结晋级并告警；合规证据过期走 03 的 `review_overdue`（改策略模式），不经 CL。
- **发布阶段**（`canary` 一词只指这里）：已上线连接器的版本或 mapper 变更依次 `shadow → canary（≤10% 实例或 WatchKey）→ full`（contract §14）；阈值与停留时长待 V0 校准，回退即退回上一段。
- **急停**：运维急停置 `disabled`（owner 可解除），合规 kill switch 走 `policy_denied/kill_switch`（恢复须双人），语义见 contract §7；两者都在 ops 层切换、不改 YAML；CL3 须有两类演练记录。

## 9. DoD 与三道评审门

### 9.1 写一个新连接器的步骤

命令链 `scaffold → record → replay → conformance → card render → promote`（命令名待 V0 定），每步对应一道门：

1. **登记（CL0）**：先查[矩阵](../../../catalog/connector-matrix.md)与族文档，能用族实例的只写 YAML（SOP A、B）；需要代码时按 `impl` 阶梯取最低级。写 SourceSpec 证据与 ConnectorManifest（`upstream_facts` 每条带 URL 与核对日期），`scaffold` 生成清单骨架与卡片草稿，注册表 lint L1…L13 与连接器 lint LC-01…LC-06 通过。
2. **合规签核（G1）**：第二人复核后把签字写入 `conformance.compliance_signoff`；签字前只许经网关取 robots.txt、OAI `Identify` 等自描述证据，不发其他请求。
3. **录制与实现（CL1）**：经 staging 网关 `record` 模式录四类 fixture 与必备件（§4）；写 `normalize`，必要时写 `plan`、`parse`；`replay` 回放，`conformance` 跑 CT-01…CT-12 与族套件（本文 §3、§5）；填卡片的三个手写节（上游事实、合规、已知坑），`card render` 生成其余节；PR 记起止时间，SOP D 的 ≤2 人日止于此（§9.2）。
4. **灰度与上线（CL2、CL3）**：G2 后 `promote` 到 CL2，在 staging 按当前策略许可的模式计天（§1.1），探针与 `canary_query` 就位（§8）；G3 后声明 CL3，替补链、runbook、SLO 与两名维护人到位。保持条件失效自动降级（§11），晋级只经 PR。

### 9.2 新 connector 的两日拆分（SOP D）

| 时段 | 产物 | 对应 |
|---|---|---|
| 第 1 天上午 | 证据（官方文档、限额、ToS、逐主机 robots、TDMRep）写入 SourceSpec 与 `upstream_facts`；`scaffold` 生成清单与卡片草稿；lint 通过 | CL0，提交 G1 |
| 日历等待 | 第二人合规复核签字 | G1，不计入 2 人日 |
| 第 1 天下午 | 经 staging 网关录四类 fixture 与必备件；写 mapper | CT-05、06、09、12 |
| 第 2 天上午 | `plan`、`parse`；`replay` 与 `conformance`；策略引擎集成（被拒时零请求） | CT-01…CT-12、族套件 |
| 第 2 天下午 | ProbeSpec 与 `canary_query`；`card render`；PR 记起止时间 | 声明 CL1，≤2 人日止于此 |
| 之后 | staging 观察 → G2 → CL2；演练与 runbook → G3 → CL3 | 按日历另计 |

前提沿用长稿 §13.3：族核心已就绪，端点语义不超出通用协议；全新认证形态单独估算。

### 9.3 DoD 清单

- 卡片 §5 写全游标声明与重启语义，§6 写粒度表、Version 依据与权利默认值，§10 列 fixture id；卡片重新生成（[卡片模板](connector-card-template.md)）。
- 作者不兼任合规复核人；`exempt` 附理由与批准人；`mapper_version` 递增附黄金 diff；引擎改动附全实例回放报告。
- 每条 `upstream_facts` 有探针；P0 声明替补链；v1_bridge 写 `v1.{destiny, mode, port_target, sunset_by}`。

### 9.4 三道门

| 门 | 检查 | 通过标准 | 评审人 |
|---|---|---|---|
| G1 合规（CL0 出口） | 逐主机 robots（RFC 9309 口径见 contract §4）；ToS 自动化条款、TDMRep、Content-Signal、具名 AI 爬虫规则；许可与署名；商用门控；证据与 `verified_at`；`allowed_hosts` ⊆ SourceSpec 通道主机 | 注册表 lint L3、L4、L7、L8、L9、L12 与 LC-01…LC-06 全过；签字写入清单 | 第二人，非作者 |
| G2 技术（CL1→CL2） | S0–S1 全绿；`exempt` 逐条；黄金 diff；SCD 与标识符粒度；P0 替补链；staging 观察报告 | CL2 进入门的其余各项（天数、零违例、探针、达标项）齐全 | 技术评审人 |
| G3 上线（CL2→CL3） | 策略决定与黄金决策行一致；探针完成第一个周期；`canary_query` 绿；替补与急停演练；runbook、SLO、告警、维护人 | 演练记录齐全；首发灰度证据按 P-4 口径；`shadow → canary → full` 只管后续变更（§8） | 部署方负责人与 owner |

长稿 G3 的 `planned → active` 在本文即声明 CL3。

## 10. CI 门禁

- **每个 PR 阻断**：S0、S1（改动涉及的连接器跑 CT-01…CT-12，引擎改动跑全实例回放）；平台 PR 另跑 S2。测试进程封 socket，只许回放。
- **等级与版本**：可达最高级与 `declared` 不符即失败；CT-08 版本门；runner 对契约版本 N 与 N−1 都跑套件；`card render` 重生成无差异。
- **覆盖率**：行覆盖 ≥80%（沿用 v1 门禁）；`parse` 与 mapper ≥90%（v1 只是目标，本文改为门禁）。
- **main 每日**：全量回放，fixture 年龄与 `exempt` 到期报告。在线 smoke、staging 与探针不阻断合并。

## 11. 自动降级与恢复

- **降级**：保持条件失效，控制面把 `cl_effective` 降到仍满足条件的最高一级，开工单并通知 owner；路由按 `EffectiveStatus` 切替补链，用户面按 U7 透明提示（[connector-ui](connector-ui.md)）。典型触发：所部署版本回放变红 → CL0；探针连续红灯超过 72 小时 → CL1；复核超期或 bridge 过期 → CL2。
- **复核超期**的宽限同 03 `review_overdue`：宽限期内维持并提示，期满仍未复核才降；复核日期按 `connector_id` 哈希错开，避免主干通道同日集体降级。
- **恢复**：条件重新满足后，由人经管理 CLI 恢复到不高于 `declared` 的等级并记审计；技术原因由 owner 或 backup_owner 确认，合规原因须双人。策略模式另按 03"只降不升、恢复须人工"。

## 12. 度量

- **接入成本**：零代码接入中位 ≤30 分钟，新 connector 到 CL1 加卡片中位 ≤2 人日（长稿 AC-V1.17、AC-V1.18，PR 记起止时间）。
- **fixture 覆盖**：覆盖表行、Expectation 分支、标识符方案、权利类、quirk 旗标的覆盖率；fixture 年龄；`exempt` 数。
- **漂移检出时间**：上游变化到告警的时长，目标一个探针周期内（长稿 AC-V1.10）。
- **维护负担**：维护点数与复核积压（P-12）。

## 怎么验收

- **文档**：与 [contract](contract.md)、[README](README.md)、[卡片模板](connector-card-template.md) 及各族文档 §4 用同一套名称与编号；与 [03](../03-sources-and-corpus-pipeline.md) SOP、[08](../08-compliance-security-privacy.md) 硬约束、[09](../09-roadmap-and-milestones.md) 里程碑不矛盾。
- **V0（W0）**：三个参考连接器及前置件 `crossref_rest`、`oai_pmh` 以 high 严格度在 CI 达 CL1，并各经网关完成一次 dry-run（09）。以下注入违规各有反例被 CI 拒绝：fixture 带 Cookie 头、连接器（含 RecipeProvider）导入 HTTP 库、黄金变而 `mapper_version` 未升、`ordered_by` 缺反例、请求落到未声明主机；可达等级与 `declared` 不符时失败。
- **V1、V3**：`v2-P0` 平台侧连接器在 V1、用户侧在 V3 达 CL3（闸门未开的停在 CL1，同 09），并满足长稿 AC-V1.5、AC-V1.10、AC-V1.24、AC-V3.18、AC-V3.19；AC 编号以 09 定稿为准，本文不新增。

## 未决事项

- **P-4** CL2 生产口径；**P-11** CL3 引擎新增实例的 staging 天数；**P-12** 维护点数与复核节奏（未核）；**P-7** 用户侧合成检查须 08 认可。
- **P-13** 用户侧元数据查询配方 `QueryRecipe`：契约 v1 不新增协议，`nasa_ads_api`、`orcid_api`、`lens_api`、`alphaxiv_mcp` 停在 CL0，§1.3 的 P1、P2 目标对它们暂不生效（[contract](contract.md#待拍板)）。
- **登记来源不复核、不降级**：细化 D-073，待拍板。
- **`cap_conformance` 拒绝的记账**：沿用 `policy_denied` 还是另设子码（如 `policy_denied/conformance`），待与 contract 统一。
- **本文补充**：G1 等待不计入 2 人日；G1 前只许取证据的自描述请求；带新主机的零代码实例同样过 G1；只有所部署版本回放变红才降级；fixture 来历值 `v1_import`。
- **robots 403 口径**：已按 contract §4 统一：robots.txt 4xx 视为无限制，被挑战（unreachable）视为全禁；对本 UA 返回带挑战特征 403 的主机（如 ScienceDirect）按被挑战处理。
- **桥接的 CT-01 测法**：v1-bridge 族 §4.3 以替换时钟与环境读取、沙箱照样抛错来满足 CT-01（★），测法变化须本文 G2 评审确认。
- **族套件编号**：各族已统一为 `FS-<族缩写>-NN`；platform-family 用 `FS-PF-H*`、`FS-PF-R*` 区分托管与仓储两半，V0 定稿时确认。
- **非 CC0 元数据的 fixture** 从严换合成值，是否过严待法务意见。
- **待 V0 校准**：覆盖率门禁、回放时长、交叉核验次数、发布阶段阈值与停留时长、在线测试变量名。长稿 §15.10 的 canary 查询统一称 `canary_query`。
- **篇幅**：约 28 KB，略超设计类 ≤25 KB 目标；本轮接受，实现期把 §3 契约测试表与 §4 fixture 政策拆为附录。

---

更细的材料：[contract](contract.md)、[卡片模板](connector-card-template.md)、各族文档 §4；长稿 `git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§13 SOP 与评审门，§15 测试方法，§16 测试类型，§17 AC 草案）。
