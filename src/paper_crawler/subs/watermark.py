"""per-source watermark 增量语义（Phase 6 T4；design/09 §5 权威规格）。

一次 watch 运行要回答两个问题：**这次该拉哪个窗**、**拉完水位推到哪**。本模块把
这两问按源封装成三类策略，并把"推进"与"提交"**刻意分成两步**。

## 三类策略（design/09 §5 逐条）

| 策略 | 源 | 语义 |
|---|---|---|
| `DateUpperBound` | arxiv | `submittedDate` 上界推进 + **重叠 1 天窗**防 announce 延迟 |
| `DateCursor` | crossref / openalex / s2 / ssrn | `from_*_date` 游标（含端，边界日天然重扫） |
| `IdSetDiff` | nber | 最近 N 个 id 集合差分（RSS 通道无日期轴，唯一适用者） |

**含端与 `overlap_days` 的分工**：游标参数是**含端**的（`from-pub-date:D` 含 D 当天），
把游标停在"已见最大日期 D"本身就重扫整个 D 日——这已经是**一天的迟到容忍**。
`overlap_days` 是在此之上**再额外**回退的天数，按各源迟到分布单独定（见下表），
不是用来"补齐"含端的：

- arxiv `overlap_days=1`：announce 延迟常跨日，提交日 = D 的论文可能 D+1/D+2 才出现在
  API 结果里；若下界已随其他论文推到 D+1，那篇就永远进不了任何窗。
- crossref `overlap_days=2`：`pub-date` 是**刊期**而非入库时刻，同一刊期的记录会陆续
  沉积数日（online-first 尤甚）——含端只保住 D 当天，故再宽两天。
- ssrn `overlap_days=1`：`created` ≈ 新投稿入 crossref 时刻，**~1 日延迟**（ssrn.md §4.2）。
- openalex / s2 `overlap_days=0`：含端重扫已足；两者都无已知的系统性入库滞后。

## 窗口参数的宿主形态（`window_params` 产出 → T5 合成）

产出与 `types.PlanStep.pushdown` 同构（有序 k-v 串），键取自
`types.DATE_WINDOW_PARAMS`（**单一同源**，本模块产出恒 ⊆ 该源的槽位名，有自断言测试），
但**键的宿主因源而异**，T5 按源分派合成（本模块只负责语义正确的键值对，不拼 URL）：

| 源 | 键 | 值形态 | 宿主 |
|---|---|---|---|
| arxiv | `submittedDate` | `[A TO B]` 闭区间 | `search_query` 字段前缀（AND 进布尔式） |
| crossref | `from-pub-date` | `YYYY-MM-DD` | `filter=` 逗号串的一项 |
| openalex | `from_publication_date` | `YYYY-MM-DD` | `filter=` 逗号串的一项 |
| s2 | `publicationDateOrYear` | `YYYY-MM-DD:` 开区间 | 真 URL 查询参数 |
| ssrn | `from-created-date` + `until-created-date` | `YYYY-MM-DD` ×2 | `filter=` 逗号串**成对** |
| nber | —（恒空） | — | 无日期轴，增量靠 RSS id 差分 |

arxiv 的 `A`/`B` 是 `YYYYMMDDHHMM`（GMT），两端分别钉 `0000`/`2359` 覆盖整日。

**s2 用 `publicationDateOrYear` 而非 `year`**（两者 site-survey/metadata-apis.md 同列，
前者是首列项）：`year=` 只有**年**粒度，会把 7 天保守初窗放大成**整年窗**——首跑必然
超护栏 → 熔断 → 不推进 → 永久死循环（且订阅级熔断连带冻结其他源）。
`publicationDateOrYear` 保住日粒度，开区间上界写作 `<起>:`（单参数区间语法）。
⚠ **该值语法未经在线确认**——site-survey 只列了参数名；`<起>:` 形态待 T9 在线冒烟
（plan §3 T9-online）实测捕获后回填确认或订正。

**ssrn 的 until 端必须成对产出**：ssrn 元数据枚举经 `CrossrefAdapter` 的 prefix 模式
（D-029），而 `_works_url` 无条件拼 `from-…,until-…` 两端——只给 from 就是半截 filter。
其余走 `filter=` 的源（crossref/openalex）由各自枚举路径给上界，本层只推下界。

## 首跑（无 watermark）= **保守初窗**，不是全量首拉

design/09 §5 未给首跑口径，本卡裁决为"回看 `initial_lookback_days`（默认 7）天"，
理由三条：

1. **全量首拉会把订阅卡死在熔断循环里**：空窗 → 一次拉回全史 → 必然超
   `guard.max_new_per_run`（缺省 200）→ 熔断 → 按推进纪律**不推进水位** → 下次仍是
   空窗……永远出不去。保守初窗让第一次就能正常收敛并落下水位。
2. **watch 不是回填通道**：全量回填走 `crawler pull`（design/05）；design/09 §1 的
   watch 语义是"新增清单"。arxiv Query API 翻页总量硬上限 30000（site-survey/arxiv.md）
   也不支持"一窗拉全史"。
3. **有先例**：ssrn.md §增量 watch 即 `from-created-date:{今-N}` 整窗收割。

`IdSetDiff`（nber）的首跑是空 id 集（最近一轮 RSS 全算新增）——它本来就没有日期轴
可收窄，拉取面由 T5 的 feed 预算限定（19 个 program feed × 周更 ~39 item），入库面
由护栏限定。

## 稳态窗宽 cap（审计 P1-24：熔断自我放大）

首跑那半边（上一段）解决了"空窗 → 全量首拉 → 熔断死循环"；**稳态这半边是同型缺陷的
另一半**，此前没做：熔断/失败/零新增轮按推进纪律**不推进水位**，于是查询窗的下界钉在
旧水位不动、上界随 `today` 天天往前走——窗**单调变宽**，请求量逐日线性上涨，下一轮更
容易再次超护栏。熔断因此**自我放大且无自愈**，只能靠人发现。

修法与首跑同源：窗宽封顶在**同一个** `initial_lookback_days`（缺省
`DEFAULT_INITIAL_LOOKBACK_DAYS`）——

```
查询窗下界 = max(旧水位 − overlap_days, today − initial_lookback_days)
```

即"窗永远不会比首跑那一次更宽"。地板另取 `max(initial_lookback_days, overlap_days)`
兜底，保证 cap 绝不会比该源自己声明的重叠窗还紧（把 `initial_lookback_days` 配成 0 的
病态取值不会反过来把重叠窗吃掉）。

**水位推进语义本身不动**（失败轮仍不推进——那是防丢数据的正确设计），所以 cap 生效时
`[旧水位, today − cap]` 这一段确实**在本轮查询范围之外**：cap 换来的是"请求量有界"，
代价是"这段可能漏收"。故 `WindowReport.capped` 把截断如实报给调用方
（`watch._run_source` 打 WARNING 点明"可能漏收、水位仍未推进、需人工 backfill 或等熔断
解除"），**不静默**。注意后果是延后的：等熔断解除、某一轮真的成功了，`advance` 取
`max(旧水位, 已见最大日期)` 会把水位从 `旧水位` 直接跳到窗内的新日期，那段缺口就此
"合法"跳过——所以警报必须在**还能补救的时候**（cap 正在生效的每一轮）响，而不是等
跳过之后。

## 连续熔断轮计数（同上，可观测面）

光有每轮一条 WARNING 不够：一个天天熔断的源和一个偶发熔断的源在日志里长得一样。故
每个源状态带一个 `stalls` 计数——熔断轮由调用方 `bump_stalls` +1（**只碰计数，日期/id
一个字节不动**，故"熔断不推进水位"的纪律不受影响），成功推进轮由 `advance` 产出的
新状态天然归零（新 `DateState`/`IdSetState` 的 `stalls` 缺省 0）。连续 ≥
`STALL_ALERT_ROUNDS` 轮时调用方把 WARNING 升格为 ERROR（obslog 最响的一档）。

`stalls` 走**可选字段**语义：值为 0 时不出现在序列化文档里（既有文档与 golden 逐字
不变），故不需要 bump `schema_ver`——旧文档读进来 `stalls=0`，正是它的真实含义。

## 推进纪律：候选生成与提交**分离**（design/09 §5 + plan §4 T4）

`advance()` 只产出**候选** `Watermark`（纯函数，不碰 DB）；真正落库是调用方在 run
成功后自己调 `SubscriptionRepo.write_watermark(name, wm.to_dict())`。熔断/失败路径
只要**不调**那一行，水位自然停在旧值——不需要回滚，也不可能"推进了一半"。

**dry-run 亦不提交**：`crawler watch --dry-run` 只报数不动库（design/09 §6.2，plan §4
T5 已裁决"不入库、不派生任务、不推 watermark、不写 run 记录"）。它是**成功路径**，
却不在"run 成功才提交"的覆盖面内——三条不提交的理由各自独立（失败、熔断、dry-run），
调用方须逐条判，别把"没熔断没失败"当成"该提交"。

方向性偏好是**反的**（宁可重看不可漏看）：

- 已见日期里的**未来日期不参与推进**（crossref online-first 的下期封面日等）——它们
  不证明"我们已经扫到那一天"，采信只会把水位顶到未来造成永久漏看；忽略只让水位更保守。
- 上界推进取 `max(已见日期)` 而**不取 `today`**：虽然我们确实查了到今天的窗，但
  announce/收录延迟意味着靠近今天的条目尚未可见，取已见最大值更保守。
- 零新增**不推进**（保持旧水位，下次窗更宽）；乱序到达取 `max` 故**永不回退**。
- 重叠窗必然产生重复——**本层不去重、如实返回**；去重归 T3 护栏
  （`dedupe_against_library`）与入库层 identifier `(scheme, value)` 主键（design/09 §5 末）。

## 序列化（plan §4 T4 已裁决：带 `schema_ver` 演进缝）

```json
{"schema_ver": 1, "sources": {"arxiv": {"kind": "date_upper_bound", "date": "2026-07-25"}}}
```

`{}`（`read_watermark` 对 NULL 的返回）= 首跑。其余任何偏差——未知 `schema_ver`、
未知源名、`kind` 与该源当前策略不符、日期非 ISO、ids 非字符串列表、多余字段——一律
`WatermarkInvalid` **fail-loud**（沿 T1 订阅 DSL 的拒载纪律；损坏游标被当成首跑会静默
重刷全窗）。`kind` 存进文档是为了人读得懂，也让"某源换了策略"这件事被逼成显式迁移
（bump `schema_ver` 或人工重置），而不是拿旧语义的值去喂新策略。

本模块**不依赖 storage**（只依赖 `errors` 与 `subs.model` 的源词表）：提交面是调用方
的事，纯函数才好做 property 测试。
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import ClassVar, NoReturn

from paper_crawler.errors import WatermarkInvalid
from paper_crawler.subs.model import SOURCE_FIELDS

# 文档 schema 版本（plan §4 T4 演进缝）。格式不兼容变更必须 bump，并在此处记迁移口径。
SCHEMA_VERSION = 1

# 首跑保守初窗（模块 docstring "首跑"段）——日期类策略共用。
DEFAULT_INITIAL_LOOKBACK_DAYS = 7

# arxiv 重叠窗宽度（design/09 §5 字面"重叠 1 天窗口"）。
DEFAULT_OVERLAP_DAYS = 1

# id 集合差分的保留上限（design/09 §5"最近 N 个"的 N，防 watermark_json 无限膨胀）。
#
# 取值依据：集合必须**覆盖住一次拉取面**，否则旧 id 掉出集合后会被当成新增重报。
# 上界侧——nber 19 个 program feed × 每 feed ~39 item（周更，nber.md §3.4）≈ 741；
# ssrn 收窄到具体 network/eJournal 后的周量同数量级。2000 给到约 2–3 个运行周期的
# 余量，序列化后 ~40 KB 量级（sqlite TEXT 列毫无压力）。真溢出（单次 seen > 2000）
# 时最旧的 id 掉出→下次重报→去重兜底，且缺省护栏 200 早在此之前就熔断了。
DEFAULT_MAX_IDS = 2000

# 连续熔断轮的告警升级阈值（模块 docstring "连续熔断轮计数"段）：连续 ≥ 本值轮没能推进
# 水位时，调用方把"窗已截断"的 WARNING 升格为 ERROR。3 = "偶发两轮还能自愈，第三轮就
# 不是偶发了"的经验值；与护栏阈值无关，纯观测面。
#
# 时点注记：告警读的是**本轮开始时**的存量 `stalls` 计数（本轮若也熔断，`bump_stalls`
# 对它的 +1 发生在告警判定之后才落库），故 ERROR 首次响是第 4 个连续熔断轮，而非第 3 个
# （测试锚 `test_consecutive_stalls_escalate_the_warning_to_error`：
# `["WARNING"] * STALL_ALERT_ROUNDS + ["ERROR"]`）。
STALL_ALERT_ROUNDS = 3

# 序列化里的策略标记（人读 + 策略变更逼成显式迁移，模块 docstring "序列化"段）。
KIND_DATE_UPPER_BOUND = "date_upper_bound"
KIND_DATE_CURSOR = "date_cursor"
KIND_ID_SET = "id_set"

_STATE_FIELD_DATE = "date"
_STATE_FIELD_IDS = "ids"
_STATE_FIELD_STALLS = "stalls"
_DOC_FIELD_SCHEMA_VER = "schema_ver"
_DOC_FIELD_SOURCES = "sources"
_KIND = "kind"


# --- 报错与取值原语（形态同 model.py，报错一律带字段路径）--------------------


def _fail(path: str, message: str) -> NoReturn:
    """统一拒载出口：消息带字段路径定位，`detail` 存同一定位串。"""
    raise WatermarkInvalid(f"watermark:{path} —— {message}", detail=path)


def _today() -> date:
    """当前 UTC 日期（全模块唯一时钟入口；测试与 T5 经 `now=` 注入假时钟）。"""
    return datetime.now(UTC).date()


def _try_parse_date(text: str) -> date | None:
    """ISO 日期文本 → `date`；**解析不了返回 `None`**（不抛）。

    接受面 = `date.fromisoformat` 对首段（`T`/空格之前）的接受面，逐条如实列出：

    | 形态 | 例 | 结果 |
    |---|---|---|
    | 完整 ISO 日 | `'2026-07-24'` | 2026-07-24 |
    | 带时间戳（取日期部分） | `'2026-07-24T10:00:00Z'` / `'2026-07-24 10:00'` | 2026-07-24 |
    | 紧凑日 | `'20260724'` | 2026-07-24 |
    | **ISO 周日期** | `'2026-W30'` / `'2026-W30-1'` | **2026-07-20**（该周周一） |
    | partial 年 / 年月 | `'2026'` / `'2026-07'` | `None` |
    | 非日期 | `'昨天'` / `''` | `None` |

    周日期那行是 Python 3.11+ `date.fromisoformat` 扩展接受面的**顺带产物**，不是本
    模块的设计意图：`'2026-W30'` 会被当成该周周一收下并**参与水位推进**。之所以只在
    此如实记录而不去拦——上游结构性产不出这种值（crossref 走 `_format_date_parts` 的
    date-parts 拼接，只可能是 `'YYYY'`/`'YYYY-MM'`/`'YYYY-MM-DD'`；arxiv 走 OAI
    时间戳），拦它属于给不存在的输入加代码；且真出现了，取周一是**保守侧**（周内更早
    的一天 → 下轮窗更宽），与本模块的方向性偏好一致。改了会动缺陷 A 的行为面，故不改。

    源侧日期字段五花八门（arxiv Atom 给完整时间戳、crossref 给 date-parts 拼出的
    `YYYY-MM-DD`），此处统一收口。

    **本函数是"宽松面"，只给本轮 `seen` 用**；存储侧水位走 `_parse_date`（fail-loud）。
    两条路径刻意分开——见 `_parse_date` 的 docstring。
    """
    head = text.strip().replace(" ", "T").split("T", 1)[0]
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def _parse_date(text: str, *, path: str) -> date:
    """ISO 日期文本 → `date`；**无法解析 → 拒载**（`_try_parse_date` 的 fail-loud 版）。

    **只用于"我们自己写出去的值"**——存储的水位文档（`DateState.date`、
    `_parse_date_payload`）。那里出现坏值意味着游标损坏或被外部改坏，静默接受会让
    "重刷全窗"或"被当成已推进而永久漏看"无从察觉，故必须响亮拒载
    （模块 docstring "序列化"段的拒载纪律）。

    ⚠ **不要拿它解析本轮 `seen`**（P0 2026-07-27 的教训）：`seen` 是**上游源侧**数据，
    partial 日期是 crossref 的**合法产物**（`crossref/parse.py::_format_date_parts`
    的 docstring 明文容 `'YYYY'`/`'YYYY-MM'`），一条坏日期不该炸掉整轮 watch。
    那条路径用 `_try_parse_date` + 计数跳过。
    """
    parsed = _try_parse_date(text)
    if parsed is None:
        _fail(path, f"无法解析为 ISO 日期: {text!r}")
    return parsed


def _require_mapping(value: object, *, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        kind = "空" if value is None else type(value).__name__
        _fail(path, f"必须是映射（object），实际是 {kind}")
    return {str(key): item for key, item in value.items()}


def _reject_unknown(raw: Mapping[str, object], allowed: tuple[str, ...], *, path: str) -> None:
    for key in raw:
        if key not in allowed:
            child = f"{path}.{key}" if path else key
            _fail(child, f"未知字段（允许: {', '.join(allowed)}）")


def _require_str(value: object, *, path: str) -> str:
    if not isinstance(value, str):
        _fail(path, f"必须是字符串，实际是 {type(value).__name__}")
    text = value.strip()
    if not text:
        _fail(path, "不得为空字符串")
    return text


def _parse_stalls(payload: Mapping[str, object], *, path: str) -> int:
    """读**可选**的 `stalls` 计数：缺失 → 0；非非负整数 → 拒载（同存储侧 fail-loud 纪律）。"""
    if _STATE_FIELD_STALLS not in payload:
        return 0
    raw = payload[_STATE_FIELD_STALLS]
    if isinstance(raw, bool) or not isinstance(raw, int):
        _fail(f"{path}.{_STATE_FIELD_STALLS}", f"必须是整数，实际是 {type(raw).__name__}")
    if raw < 0:
        _fail(f"{path}.{_STATE_FIELD_STALLS}", f"不得为负: {raw}")
    return raw


def _stalls_payload(stalls: int) -> dict[str, object]:
    """`stalls` 的序列化片段：0 **不落字段**（既有文档/golden 逐字不变，无需 bump 版本）。"""
    return {_STATE_FIELD_STALLS: stalls} if stalls else {}


def _dedupe(values: Iterable[str]) -> list[str]:
    """保序去重（同 `types.CompiledPlan.all_local_predicates` 手法）。"""
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


# --- 状态值对象 -------------------------------------------------------------


@dataclass(frozen=True)
class DateState:
    """日期类策略的状态：已推进到的日期水位（UTC `YYYY-MM-DD`）+ 连续熔断轮计数。

    语义随策略而异——`DateUpperBound` 下是"已见提交日上界"，`DateCursor` 下是
    "下次 from_date 的起点"；两者的 `advance` 算法一致（取 max，不回退），差别只在
    `window_params` 是否再回退重叠天。

    `stalls` 见模块 docstring "连续熔断轮计数"段：0 = 上一轮正常推进过（也是缺省与
    旧文档的读入值），序列化时为 0 则**不落字段**。
    """

    date: str
    stalls: int = 0


@dataclass(frozen=True)
class IdSetState:
    """id 集合差分策略的状态：最近见过的 id（**新→旧**序，长度 ≤ `max_ids`）。

    用 tuple 而非 set：既保 frozen dataclass 可哈希（模块约定），又让"最近"这个
    时间序在截断时有意义——截断永远砍掉最旧的一段。

    `stalls` 同 `DateState`（两类状态共用同一套熔断计数语义，故字段同名同义）。
    """

    ids: tuple[str, ...] = ()
    stalls: int = 0


SourceState = DateState | IdSetState


def _as_date_state(state: SourceState, *, path: str) -> DateState:
    """状态必须是日期类（喂错策略是编程错误，响亮拒绝而非 silently 当首跑）。"""
    if isinstance(state, DateState):
        return state
    _fail(path, f"状态类型不符：该源为日期类策略，实际拿到 {type(state).__name__}")


def _as_id_set_state(state: SourceState, *, path: str) -> IdSetState:
    if isinstance(state, IdSetState):
        return state
    _fail(path, f"状态类型不符：该源为 id 差分策略，实际拿到 {type(state).__name__}")


def _opt_date_state(state: SourceState | None, *, path: str) -> DateState | None:
    return None if state is None else _as_date_state(state, path=path)


def _opt_id_set_state(state: SourceState | None, *, path: str) -> IdSetState | None:
    return None if state is None else _as_id_set_state(state, path=path)


def _require_non_negative(value: int, *, field: str, source: str) -> None:
    """策略构造参数的取值域把关（负天数 = 水位往回走，静默生效会长期多拉窗）。"""
    if value < 0:
        _fail(f"strategy.{source}.{field}", f"不得为负: {value}")


# 跳过样例的记录上限（日志里够定位就行，不必全量——一个坏源可能刷出成千上万条）。
_MAX_SKIPPED_SAMPLES = 3


def _advance_date(base: date, seen: Sequence[str], *, today: date) -> tuple[date, tuple[str, ...]]:
    """日期水位推进的公共算法（两个日期类策略共用）→ `(新水位, 不可解析样例)`。

    `max(base, max(可解析的已见日期 ∩ (-∞, today]))`——四条纪律在这里：取 max 故乱序
    到达不回退；未来日期先被剔除故坏数据顶不动水位；`seen` 空则恒等返回 `base`
    （零新增不推进）；**解析不了的条目跳过**（不抛）。

    跳过而非抛，是因为 `seen` 是**上游源侧**数据而非我们自己的存储：crossref 的
    partial 日期（`'YYYY'`/`'YYYY-MM'`）是其 parse 层的**合法产物**，让它炸掉整轮
    watch 等于把"一条元数据不全"升级成"所有源都别跑了"（P0 2026-07-27）。跳过的
    方向性也是对的——水位不推进 = 下次窗更宽 = 保守侧，与本模块"缺日期时不推进"
    同口径（`watch._run_source` 对 `pub_date` 为空的处置）。

    返回的样例串**仅供调用方打日志**（截到 `_MAX_SKIPPED_SAMPLES` 条）：跳过必须
    可观测，否则"这批没推进水位"确实会无从察觉——那正是旧 fail-loud 契约的正当关切，
    这里用计数 + 日志满足它，而不是用"炸掉整轮"满足它。
    """
    candidates: list[date] = []
    skipped: list[str] = []
    for text in seen:
        parsed = _try_parse_date(text)
        if parsed is None:
            skipped.append(text)
            continue
        if parsed <= today:
            candidates.append(parsed)
    return max([base, *candidates]), tuple(skipped)


def _initial_lower_bound(lookback_days: int, today: date) -> date:
    """首跑保守初窗的下界（模块 docstring "首跑"段）。"""
    return today - timedelta(days=lookback_days)


@dataclass(frozen=True)
class WindowReport:
    """某源本次增量窗的完整交代：参数 + 下界 + **是否被 cap 截断** + 连续熔断轮数。

    `window_params` 只给参数，够 T5 合成请求，但不足以让调用方把"这个窗已经不是它本
    该有的样子了"告诉用户——`capped` 与 `stalls` 就是补上的那半边（模块 docstring
    "稳态窗宽 cap" / "连续熔断轮计数"两段）。

    - `lower`：窗下界（已含 cap）；无日期轴的源（nber/`IdSetDiff`）恒 None。
    - `capped`：True = 下界被 `today − initial_lookback_days` 的地板抬高过，即
      `[旧水位, 下界)` 这段**不在本轮查询范围内**（可能漏收，需人工 backfill）。
    - `stalls`：该源存量状态里的连续熔断轮数（首跑无状态 → 0）。
    """

    params: tuple[tuple[str, str], ...] = ()
    lower: date | None = None
    capped: bool = False
    stalls: int = 0


def _capped_lower_bound(
    current: DateState | None, *, today: date, lookback_days: int, overlap_days: int, path: str
) -> tuple[date, bool, int]:
    """日期类策略的窗下界 → `(下界, 是否被 cap 截断, 连续熔断轮数)`（两个策略共用）。

    首跑（无状态）= 保守初窗，恒不算截断（那本来就是 cap 的宽度）。有状态时下界 =
    `max(水位 − overlap, 地板)`，地板 = `today − max(lookback, overlap)`——取 max 是为
    了让 cap 绝不比该源自己声明的重叠窗还紧（模块 docstring "稳态窗宽 cap"段）。
    """
    if current is None:
        return _initial_lower_bound(lookback_days, today), False, 0
    floor = _initial_lower_bound(max(lookback_days, overlap_days), today)
    raw = _parse_date(current.date, path=f"{path}.{_STATE_FIELD_DATE}") - timedelta(
        days=overlap_days
    )
    if raw < floor:
        return floor, True, current.stalls
    return raw, False, current.stalls


# --- 三类策略 ---------------------------------------------------------------


@dataclass(frozen=True)
class DateUpperBound:
    """arxiv：`submittedDate` 上界推进 + 重叠 1 天窗（design/09 §5 第一条）。

    窗是闭区间 `[下界 00:00, 今天 23:59]`（GMT，arxiv 字段语法
    `submittedDate:[YYYYMMDDHHMM TO YYYYMMDDHHMM]`，site-survey/arxiv.md）；下界 =
    水位 − `overlap_days`（首跑 = 今天 − `initial_lookback_days`）。
    """

    source: str
    param: str
    overlap_days: int = DEFAULT_OVERLAP_DAYS
    initial_lookback_days: int = DEFAULT_INITIAL_LOOKBACK_DAYS
    kind: ClassVar[str] = KIND_DATE_UPPER_BOUND

    def __post_init__(self) -> None:
        _require_non_negative(self.overlap_days, field="overlap_days", source=self.source)
        _require_non_negative(
            self.initial_lookback_days, field="initial_lookback_days", source=self.source
        )

    def _bounds(self, state: SourceState | None, today: date) -> tuple[date, bool, int]:
        path = f"sources.{self.source}"
        return _capped_lower_bound(
            _opt_date_state(state, path=path),
            today=today,
            lookback_days=self.initial_lookback_days,
            overlap_days=self.overlap_days,
            path=path,
        )

    def lower_bound(self, state: SourceState | None, *, now: date | None = None) -> date:
        """本次窗的下界（诊断/日报可读；`window_params` 的取值来源，**已含 cap**）。"""
        return self._bounds(state, now if now is not None else _today())[0]

    def window_report(self, state: SourceState | None, *, now: date | None = None) -> WindowReport:
        """窗参数 + 截断/熔断计数的完整交代（`WindowReport` docstring）。"""
        today = now if now is not None else _today()
        lower, capped, stalls = self._bounds(state, today)
        params = ((self.param, f"[{lower:%Y%m%d}0000 TO {today:%Y%m%d}2359]"),)
        return WindowReport(params=params, lower=lower, capped=capped, stalls=stalls)

    def window_params(
        self, state: SourceState | None, *, now: date | None = None
    ) -> tuple[tuple[str, str], ...]:
        """`(("submittedDate", "[YYYYMMDD0000 TO YYYYMMDD2359]"),)`（T5 AND 进 search_query）。"""
        return self.window_report(state, now=now).params

    def advance(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> DateState:
        """候选新水位（**未提交**）；`seen` = 本次已见条目的提交日期文本。"""
        return self.advance_with_report(state, seen, now=now)[0]

    def advance_with_report(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> tuple[DateState, tuple[str, ...]]:
        """`advance` + 被跳过的不可解析日期样例（`_advance_date` 的可观测面）。"""
        today = now if now is not None else _today()
        path = f"sources.{self.source}"
        current = _opt_date_state(state, path=path)
        base = (
            _initial_lower_bound(self.initial_lookback_days, today)
            if current is None
            else _parse_date(current.date, path=f"{path}.date")
        )
        advanced, skipped = _advance_date(base, seen, today=today)
        return DateState(advanced.isoformat()), skipped

    def to_payload(self, state: SourceState) -> dict[str, object]:
        current = _as_date_state(state, path=f"sources.{self.source}")
        return {
            _KIND: self.kind,
            _STATE_FIELD_DATE: current.date,
            **_stalls_payload(current.stalls),
        }

    def parse_state(self, payload: Mapping[str, object], *, path: str) -> DateState:
        return _parse_date_payload(payload, kind=self.kind, path=path)


@dataclass(frozen=True)
class DateCursor:
    """crossref / openalex / s2 / ssrn：`from_*_date` 游标（design/09 §5 第三条）。

    与 `DateUpperBound` 的差别只在**上界怎么写**：本策略的 from 参数含端，下界 =
    水位 − `overlap_days`（缺省 0 = 只靠含端天然重扫那一天），上界形态三选一：

    - `until_param=None` + `range_suffix=""`（crossref/openalex）：只推下界，上界由
      各自枚举路径给（openalex `to_publication_date` / crossref `until-pub-date`）；
    - `until_param="until-created-date"`（ssrn）：**成对**产出，上界 = 今天——
      `CrossrefAdapter._works_url` 无条件拼两端，缺 until 就是半截 filter（D-029）；
    - `range_suffix=":"`（s2）：单参数区间语法 `publicationDateOrYear=<起>:`，上界留空
       表示开区间（⚠ 值语法待 T9 在线冒烟确认，模块 docstring s2 段）。

    三者互斥（`__post_init__` 拒同时设 `until_param` 与 `range_suffix`）。
    """

    source: str
    param: str
    overlap_days: int = 0
    until_param: str | None = None
    range_suffix: str = ""
    initial_lookback_days: int = DEFAULT_INITIAL_LOOKBACK_DAYS
    kind: ClassVar[str] = KIND_DATE_CURSOR

    def __post_init__(self) -> None:
        _require_non_negative(self.overlap_days, field="overlap_days", source=self.source)
        _require_non_negative(
            self.initial_lookback_days, field="initial_lookback_days", source=self.source
        )
        if self.until_param is not None and self.range_suffix:
            _fail(
                f"strategy.{self.source}",
                "`until_param` 与 `range_suffix` 互斥（独立 until 参数 vs 单参数区间语法）",
            )

    def _bounds(self, state: SourceState | None, today: date) -> tuple[date, bool, int]:
        path = f"sources.{self.source}"
        return _capped_lower_bound(
            _opt_date_state(state, path=path),
            today=today,
            lookback_days=self.initial_lookback_days,
            overlap_days=self.overlap_days,
            path=path,
        )

    def lower_bound(self, state: SourceState | None, *, now: date | None = None) -> date:
        """本次窗下界 = 水位 − `overlap_days`（含端，**已含 cap**）；首跑 = 今天 − 初窗回看天数。"""
        return self._bounds(state, now if now is not None else _today())[0]

    def window_report(self, state: SourceState | None, *, now: date | None = None) -> WindowReport:
        """窗参数 + 截断/熔断计数的完整交代（`WindowReport` docstring）。"""
        today = now if now is not None else _today()
        lower, capped, stalls = self._bounds(state, today)
        params = [(self.param, f"{lower.isoformat()}{self.range_suffix}")]
        if self.until_param is not None:
            params.append((self.until_param, today.isoformat()))
        return WindowReport(params=tuple(params), lower=lower, capped=capped, stalls=stalls)

    def window_params(
        self, state: SourceState | None, *, now: date | None = None
    ) -> tuple[tuple[str, str], ...]:
        """`((param, "YYYY-MM-DD"),)`，另按 `until_param`/`range_suffix` 补上界形态。"""
        return self.window_report(state, now=now).params

    def advance(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> DateState:
        """候选新游标（**未提交**）；`seen` = 本次已见条目的发表/登记日期文本。"""
        return self.advance_with_report(state, seen, now=now)[0]

    def advance_with_report(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> tuple[DateState, tuple[str, ...]]:
        """`advance` + 被跳过的不可解析日期样例（`_advance_date` 的可观测面）。"""
        today = now if now is not None else _today()
        path = f"sources.{self.source}"
        current = _opt_date_state(state, path=path)
        base = (
            _initial_lower_bound(self.initial_lookback_days, today)
            if current is None
            else _parse_date(current.date, path=f"{path}.date")
        )
        advanced, skipped = _advance_date(base, seen, today=today)
        return DateState(advanced.isoformat()), skipped

    def to_payload(self, state: SourceState) -> dict[str, object]:
        current = _as_date_state(state, path=f"sources.{self.source}")
        return {
            _KIND: self.kind,
            _STATE_FIELD_DATE: current.date,
            **_stalls_payload(current.stalls),
        }

    def parse_state(self, payload: Mapping[str, object], *, path: str) -> DateState:
        return _parse_date_payload(payload, kind=self.kind, path=path)


@dataclass(frozen=True)
class IdSetDiff:
    """nber：最近 N 个 id 集合差分（[nber.md §3.4] 权威规格——"无可靠时间过滤"场景通用法；
    design/09 §5 现有独立 NBER 条目引用同一权威出处，T10 终审订正：此前误引"design/09 §5
    第二条"实指已加删除线的 SSRN 旧文，非本策略的真实权威来源）。

    **当前唯一适用者是 nber**：其增量通道是 program RSS（`back.nber.org/rss/new{code}.xml`，
    nber.md §3.4），feed 只给"最近一批"，没有任何日期轴可下推。ssrn 曾用本策略，
    D-029 后其元数据主路径改经 crossref prefix 枚举、created 轴时间过滤已可靠，故改判
    `DateCursor`（design/09 §5 联动修订 2026-07-26）——"最近 N 页"的前提本身消失了。

    `new_ids()` 是策略层**唯一**做去重语义的地方（日期类一概不去重）——但它去的只是
    "与上次窗的重叠"，与护栏 `dedupe_against_library`（对全库）、入库层 identifier
    主键（最终防线）是三道独立的网，谁都不替代谁。

    `max_ids` 上限见 `DEFAULT_MAX_IDS` 的取值依据注释。
    """

    source: str
    max_ids: int = DEFAULT_MAX_IDS
    kind: ClassVar[str] = KIND_ID_SET

    def __post_init__(self) -> None:
        if self.max_ids < 1:
            _fail(f"strategy.{self.source}.max_ids", f"须 ≥ 1（实际 {self.max_ids}）")

    def window_report(self, state: SourceState | None, *, now: date | None = None) -> WindowReport:
        """无日期轴 → 参数恒空、`lower` 恒 None、`capped` 恒 False（没有窗可放大，也就无从截断）。

        `stalls` 照常带出、落库——熔断计数是**源级**语义，与"有没有日期窗"无关。但如实
        订正：本策略 `capped` 恒 False，而 `watch._warn_if_window_capped` 只在
        `capped=True` 时才告警，故本源（当前唯一使用者 nber）的 `stalls` 目前**没有任何
        日志消费方**——连续熔断再多轮也不会触发 WARNING/ERROR，只在 watermark 文档里
        计数留痕。无窗源告警路径待后续需求出现时另立卡。
        """
        current = _opt_id_set_state(state, path=f"sources.{self.source}")
        return WindowReport(stalls=0 if current is None else current.stalls)

    def window_params(
        self, state: SourceState | None, *, now: date | None = None
    ) -> tuple[tuple[str, str], ...]:
        """恒空：本策略无日期下推面（拉取范围 = T5 的 feed 预算，非查询参数）。"""
        return self.window_report(state, now=now).params

    def new_ids(self, state: SourceState | None, candidates: Sequence[str]) -> tuple[str, ...]:
        """差分：`candidates` 里**上次没见过**的部分（保序去重）。首跑 = 全是新的。"""
        current = _opt_id_set_state(state, path=f"sources.{self.source}")
        known = frozenset(current.ids) if current is not None else frozenset()
        return tuple(value for value in _dedupe(candidates) if value not in known)

    def advance(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> IdSetState:
        """候选新 id 集（**未提交**）：本次 `seen` 置前 + 旧集合补后，截到 `max_ids`。

        置前是因为截断只该砍最旧的：本次见到的一定比上次的新。`seen` 传**本次窗内
        见到的全部 id**（不是 `new_ids` 的差分结果）——否则重叠部分会掉出集合。
        """
        current = _opt_id_set_state(state, path=f"sources.{self.source}")
        merged = _dedupe([*seen, *(current.ids if current is not None else ())])
        return IdSetState(tuple(merged[: self.max_ids]))

    def advance_with_report(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> tuple[IdSetState, tuple[str, ...]]:
        """与日期类同构的可观测面；id 是任意字符串，**恒无**"解析不了"一说 → 样例恒空。"""
        return self.advance(state, seen, now=now), ()

    def to_payload(self, state: SourceState) -> dict[str, object]:
        current = _as_id_set_state(state, path=f"sources.{self.source}")
        return {
            _KIND: self.kind,
            _STATE_FIELD_IDS: list(current.ids),
            **_stalls_payload(current.stalls),
        }

    def parse_state(self, payload: Mapping[str, object], *, path: str) -> IdSetState:
        # kind 先判：策略不符时给"换策略须显式迁移"而不是"未知字段 ids"这种误导消息。
        _require_kind(payload, expected=self.kind, path=path)
        _reject_unknown(payload, (_KIND, _STATE_FIELD_IDS, _STATE_FIELD_STALLS), path=path)
        if _STATE_FIELD_IDS not in payload:
            _fail(f"{path}.{_STATE_FIELD_IDS}", "必填字段缺失")
        raw = payload[_STATE_FIELD_IDS]
        if not isinstance(raw, list):
            _fail(f"{path}.{_STATE_FIELD_IDS}", f"必须是列表，实际是 {type(raw).__name__}")
        ids = tuple(
            _require_str(item, path=f"{path}.{_STATE_FIELD_IDS}[{index}]")
            for index, item in enumerate(raw)
        )
        if len(ids) > self.max_ids:
            _fail(
                f"{path}.{_STATE_FIELD_IDS}",
                f"id 数 {len(ids)} 超出上限 {self.max_ids}（文档被外部改坏？）",
            )
        return IdSetState(ids, _parse_stalls(payload, path=path))


WatermarkStrategy = DateUpperBound | DateCursor | IdSetDiff


def _require_kind(payload: Mapping[str, object], *, expected: str, path: str) -> None:
    if _KIND not in payload:
        _fail(f"{path}.{_KIND}", "必填字段缺失")
    actual = _require_str(payload[_KIND], path=f"{path}.{_KIND}")
    if actual != expected:
        _fail(
            f"{path}.{_KIND}",
            f"策略标记 {actual!r} 与该源当前策略 {expected!r} 不符"
            "（换策略须显式迁移：bump schema_ver 或人工重置水位）",
        )


def _parse_date_payload(payload: Mapping[str, object], *, kind: str, path: str) -> DateState:
    _require_kind(payload, expected=kind, path=path)  # kind 先判，同 `IdSetDiff.parse_state`
    _reject_unknown(payload, (_KIND, _STATE_FIELD_DATE, _STATE_FIELD_STALLS), path=path)
    if _STATE_FIELD_DATE not in payload:
        _fail(f"{path}.{_STATE_FIELD_DATE}", "必填字段缺失")
    text = _require_str(payload[_STATE_FIELD_DATE], path=f"{path}.{_STATE_FIELD_DATE}")
    # 归一为 `YYYY-MM-DD`：文档里写 `2026-07-25T10:00:00Z` 也认，但存回去是日期。
    return DateState(
        _parse_date(text, path=f"{path}.{_STATE_FIELD_DATE}").isoformat(),
        _parse_stalls(payload, path=path),
    )


# --- 源 → 策略注册表（design/09 §3/§5 能力表）--------------------------------

# 键与值的参数名恒 ⊆ `types.DATE_WINDOW_PARAMS`（自断言测试锁），`overlap_days` 的逐源
# 依据见模块 docstring "含端与 overlap_days 的分工"段。
STRATEGIES: dict[str, WatermarkStrategy] = {
    "arxiv": DateUpperBound(source="arxiv", param="submittedDate"),
    "ssrn": DateCursor(
        source="ssrn",
        param="from-created-date",
        until_param="until-created-date",  # crossref `_works_url` 强制两端成对
        overlap_days=1,  # created ≈ 入 crossref 时刻，~1 日延迟（ssrn.md §4.2）
    ),
    "openalex": DateCursor(source="openalex", param="from_publication_date"),
    "s2": DateCursor(source="s2", param="publicationDateOrYear", range_suffix=":"),
    "nber": IdSetDiff(source="nber"),
    "crossref": DateCursor(
        source="crossref",
        param="from-pub-date",
        overlap_days=2,  # pub-date 是刊期非入库时刻，记录陆续沉积
    ),
}


def strategy_for(source: str) -> WatermarkStrategy:
    """取某源的 watermark 策略；未知源 → 拒载（源词表与 `model.SOURCE_FIELDS` 同集）。"""
    strategy = STRATEGIES.get(source)
    if strategy is None:
        _fail(
            f"sources.{source}",
            f"未知源（支持: {', '.join(sorted(SOURCE_FIELDS))}；design/09 §3 能力表）",
        )
    return strategy


# --- watermark 文档 ---------------------------------------------------------


@dataclass(frozen=True)
class Watermark:
    """一份订阅的全部源水位（= `subscription.watermark_json` 的对象形态）。

    `states` 是**有序** k-v 对而非 dict：frozen dataclass 需可哈希（同 `types.PlanStep`
    的 `pushdown` 约定），顺序也让序列化结果确定性可 golden。空 `states` = 首跑。
    """

    states: tuple[tuple[str, SourceState], ...] = ()
    schema_ver: int = SCHEMA_VERSION

    def is_empty(self) -> bool:
        """无任何源水位（首跑，或全部源刚被 `restrict_to` 摘掉）。"""
        return not self.states

    def state_for(self, source: str) -> SourceState | None:
        """取某源的状态；该源尚无水位（首跑）→ None。"""
        return next((state for name, state in self.states if name == source), None)

    def with_state(self, source: str, state: SourceState) -> "Watermark":
        """写入/替换某源的状态，返回**新**文档（原地不改；已存在则保持原位置）。"""
        strategy_for(source)  # 未知源在此响亮拒绝，不等到序列化才炸
        if self.state_for(source) is None:
            updated = (*self.states, (source, state))
        else:
            updated = tuple((n, state if n == source else old) for n, old in self.states)
        return Watermark(states=updated, schema_ver=self.schema_ver)

    def restrict_to(self, sources: Iterable[str]) -> "Watermark":
        """只保留 `sources` 内的源——退订的源不留幽灵游标。

        `SubscriptionRepo.write_watermark` 是整体覆盖并把"留谁删谁"显式交给本层
        （其 docstring 原话），本方法就是那个交接点：T5 提交前按订阅当前 `sources`
        过一道。**副作用是重新订阅某源 = 首跑**——这是保守方向（重看，不漏看）。
        """
        keep = frozenset(sources)
        return Watermark(
            states=tuple((name, state) for name, state in self.states if name in keep),
            schema_ver=self.schema_ver,
        )

    def to_dict(self) -> dict[str, object]:
        """→ `SubscriptionRepo.write_watermark` 的入参（模块 docstring "序列化"段）。"""
        return {
            _DOC_FIELD_SCHEMA_VER: self.schema_ver,
            _DOC_FIELD_SOURCES: {
                name: strategy_for(name).to_payload(state) for name, state in self.states
            },
        }

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> "Watermark":
        """← `SubscriptionRepo.read_watermark` 的返回；`{}` = 首跑，其余偏差一律拒载。"""
        document = _require_mapping(dict(raw), path="")
        if not document:
            return cls()
        _reject_unknown(document, (_DOC_FIELD_SCHEMA_VER, _DOC_FIELD_SOURCES), path="")

        if _DOC_FIELD_SCHEMA_VER not in document:
            _fail(_DOC_FIELD_SCHEMA_VER, "必填字段缺失（非空 watermark 文档必须自述版本）")
        version = document[_DOC_FIELD_SCHEMA_VER]
        if isinstance(version, bool) or not isinstance(version, int):
            _fail(_DOC_FIELD_SCHEMA_VER, f"必须是整数，实际是 {type(version).__name__}")
        if version != SCHEMA_VERSION:
            _fail(
                _DOC_FIELD_SCHEMA_VER,
                f"未知 schema_ver {version}（本版只认 {SCHEMA_VERSION}）"
                "——不猜旧/新格式语义，请人工迁移或重置水位",
            )

        if _DOC_FIELD_SOURCES not in document:
            _fail(_DOC_FIELD_SOURCES, "必填字段缺失")
        sources = _require_mapping(document[_DOC_FIELD_SOURCES], path=_DOC_FIELD_SOURCES)

        states: list[tuple[str, SourceState]] = []
        for name, payload in sources.items():
            path = f"{_DOC_FIELD_SOURCES}.{name}"
            body = _require_mapping(payload, path=path)
            states.append((name, strategy_for(name).parse_state(body, path=path)))
        return cls(states=tuple(states), schema_ver=version)


# --- 文档级便捷面（T5 的主消费入口）-----------------------------------------


def window_params(
    watermark: Watermark, source: str, *, now: date | None = None
) -> tuple[tuple[str, str], ...]:
    """某源本次的增量窗参数（与 `PlanStep.pushdown` 同构，T5 与 T2 静态参数合成）。"""
    strategy = strategy_for(source)
    return strategy.window_params(watermark.state_for(source), now=now)


def window_report(watermark: Watermark, source: str, *, now: date | None = None) -> WindowReport:
    """`window_params` 的可观测版：另带回窗是否被 cap 截断、该源连续熔断了几轮。

    T5（`watch._run_source`）用它取窗——参数与 `window_params` 逐字相同，只是多了
    "这个窗有没有被削过"这条调用方必须转达给用户的信息（模块 docstring "稳态窗宽
    cap"段）。
    """
    return strategy_for(source).window_report(watermark.state_for(source), now=now)


def bump_stalls(watermark: Watermark, sources: Iterable[str]) -> tuple[Watermark, bool]:
    """给 `sources` 里**已有状态**的源各 +1 连续熔断计数 → `(新文档, 是否有变化)`。

    **只碰计数**：日期水位 / id 集合一个字节不动，故"熔断轮不推进水位"的纪律原样成立
    （模块 docstring "连续熔断轮计数"段）。这是调用方在熔断路径上唯一该写的东西。

    **不给"尚无状态"的源凭空造状态**（首跑轮熔断 → 文档仍是 `{}`）：首跑窗宽恒等于
    cap、没有自我放大也没有"跳过的缺口"，此时造一条状态只会把"这个订阅还没成功跑过
    任何一轮"这个事实抹掉（存量断言 `read_watermark(...) == {}` 正是在锁这条）。

    返回的 `changed` 让调用方在"一条都没变"时**跳过写库**——否则空文档会被覆写成
    `{"schema_ver": 1, "sources": {}}`，语义等价却不再是"没跑过"的那个字面值。
    """
    wanted = frozenset(sources)
    changed = False
    updated: list[tuple[str, SourceState]] = []
    for name, state in watermark.states:
        if name in wanted:
            changed = True
            state = replace(state, stalls=state.stalls + 1)
        updated.append((name, state))
    return Watermark(states=tuple(updated), schema_ver=watermark.schema_ver), changed


def advance(
    watermark: Watermark, source: str, seen: Sequence[str], *, now: date | None = None
) -> Watermark:
    """产出推进后的**候选**文档——纯函数，**不提交**。

    提交是调用方的事：run 成功才 `repo.write_watermark(name, candidate.to_dict())`。
    **三条不提交的理由各自独立**——失败、熔断、以及 `--dry-run`（只报数不动库，
    design/09 §6.2；它是成功路径却同样不提交）——调用方须逐条判，别把"没熔断没失败"
    当成"该提交"（模块 docstring "推进纪律"段）。

    `seen` 取 `Sequence` 而非 `Iterable`：本函数会**多次遍历**（解析 + 取 max / 去重
    合并），传生成器会被一次性消耗，第二遍拿到空序列 → 水位静默不推进或 id 静默丢失。
    调用方先物化成 list/tuple，类型上就挡住这条陷阱。

    `seen` 的含义随策略而异：日期类 = 本次已见条目的日期文本；id 差分类 = 本次窗内
    见到的**全部** id。

    解析不了的日期（含 crossref 合法 partial `'YYYY'`/`'YYYY-MM'`）**跳过不抛**；要拿
    到跳过计数做可观测，用 `advance_with_report`。
    """
    return advance_with_report(watermark, source, seen, now=now).watermark


@dataclass(frozen=True)
class AdvanceReport:
    """`advance` 的结果 + 本次跳过了多少条不可解析日期（可观测面）。

    `samples` 截到 `_MAX_SKIPPED_SAMPLES` 条，只为日志定位（一个坏源可能刷出成千上万
    条，全量既无用又会撑爆日志行）。`skipped` 是**全量**计数，不受样例上限影响。
    """

    watermark: Watermark
    skipped: int = 0
    samples: tuple[str, ...] = ()


def advance_with_report(
    watermark: Watermark, source: str, seen: Sequence[str], *, now: date | None = None
) -> AdvanceReport:
    """`advance` 的可观测版：额外带回被跳过的不可解析日期计数与样例。

    调用方（`watch._advance_source`）据此打 WARNING——"跳过必须可观测"是旧 fail-loud
    契约的正当关切，本函数就是承接它的地方（P0 2026-07-27 改判：用日志满足该关切，
    而不是用"炸掉整轮"满足）。

    与策略层的同名方法 `WatermarkStrategy.advance_with_report` 是**同一概念的两层**
    （文档级 vs 单源状态级），故取同名——此前策略层叫 `advance_report`，同概念两个名字
    （审查 P2 命名统一 2026-07-27）。
    """
    strategy = strategy_for(source)
    state, skipped = strategy.advance_with_report(watermark.state_for(source), seen, now=now)
    return AdvanceReport(
        watermark=watermark.with_state(source, state),
        skipped=len(skipped),
        samples=skipped[:_MAX_SKIPPED_SAMPLES],
    )


__all__ = [
    "DEFAULT_INITIAL_LOOKBACK_DAYS",
    "DEFAULT_MAX_IDS",
    "DEFAULT_OVERLAP_DAYS",
    "KIND_DATE_CURSOR",
    "KIND_DATE_UPPER_BOUND",
    "KIND_ID_SET",
    "SCHEMA_VERSION",
    "STALL_ALERT_ROUNDS",
    "STRATEGIES",
    "AdvanceReport",
    "DateCursor",
    "DateState",
    "DateUpperBound",
    "IdSetDiff",
    "IdSetState",
    "SourceState",
    "Watermark",
    "WatermarkStrategy",
    "WindowReport",
    "advance",
    "advance_with_report",
    "bump_stalls",
    "strategy_for",
    "window_params",
    "window_report",
]
