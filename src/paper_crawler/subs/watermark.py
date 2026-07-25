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
from dataclasses import dataclass
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

# 序列化里的策略标记（人读 + 策略变更逼成显式迁移，模块 docstring "序列化"段）。
KIND_DATE_UPPER_BOUND = "date_upper_bound"
KIND_DATE_CURSOR = "date_cursor"
KIND_ID_SET = "id_set"

_STATE_FIELD_DATE = "date"
_STATE_FIELD_IDS = "ids"
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


def _parse_date(text: str, *, path: str) -> date:
    """ISO 日期文本 → `date`；同时接受 `YYYY-MM-DDTHH:MM:SSZ` 形态（取日期部分）。

    源侧日期字段五花八门（arxiv Atom 给完整时间戳、crossref 给 date-parts 拼出的
    `YYYY-MM-DD`），此处统一收口；无法解析 → 拒载（不静默跳过：静默会让"这批数据
    没推进水位"变得无从察觉）。
    """
    head = text.strip().replace(" ", "T").split("T", 1)[0]
    try:
        return date.fromisoformat(head)
    except ValueError:
        _fail(path, f"无法解析为 ISO 日期: {text!r}")


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


def _dedupe(values: Iterable[str]) -> list[str]:
    """保序去重（同 `types.CompiledPlan.all_local_predicates` 手法）。"""
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


# --- 状态值对象 -------------------------------------------------------------


@dataclass(frozen=True)
class DateState:
    """日期类策略的状态：已推进到的日期水位（UTC `YYYY-MM-DD`）。

    语义随策略而异——`DateUpperBound` 下是"已见提交日上界"，`DateCursor` 下是
    "下次 from_date 的起点"；两者的 `advance` 算法一致（取 max，不回退），差别只在
    `window_params` 是否再回退重叠天。
    """

    date: str


@dataclass(frozen=True)
class IdSetState:
    """id 集合差分策略的状态：最近见过的 id（**新→旧**序，长度 ≤ `max_ids`）。

    用 tuple 而非 set：既保 frozen dataclass 可哈希（模块约定），又让"最近"这个
    时间序在截断时有意义——截断永远砍掉最旧的一段。
    """

    ids: tuple[str, ...] = ()


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


def _advance_date(base: date, seen: Sequence[str], *, today: date, path: str) -> date:
    """日期水位推进的公共算法（两个日期类策略共用）。

    `max(base, max(已见日期 ∩ (-∞, today]))`——三条纪律都在这一行里：取 max 故乱序
    到达不回退；未来日期先被剔除故坏数据顶不动水位；`seen` 空则恒等返回 `base`
    （零新增不推进）。
    """
    candidates = [
        parsed
        for index, text in enumerate(seen)
        if (parsed := _parse_date(text, path=f"{path}.seen[{index}]")) <= today
    ]
    return max([base, *candidates])


def _initial_lower_bound(lookback_days: int, today: date) -> date:
    """首跑保守初窗的下界（模块 docstring "首跑"段）。"""
    return today - timedelta(days=lookback_days)


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

    def lower_bound(self, state: SourceState | None, *, now: date | None = None) -> date:
        """本次窗的下界（诊断/日报可读；`window_params` 的取值来源）。"""
        today = now if now is not None else _today()
        current = _opt_date_state(state, path=f"sources.{self.source}")
        if current is None:
            return _initial_lower_bound(self.initial_lookback_days, today)
        return _parse_date(current.date, path=f"sources.{self.source}.date") - timedelta(
            days=self.overlap_days
        )

    def window_params(
        self, state: SourceState | None, *, now: date | None = None
    ) -> tuple[tuple[str, str], ...]:
        """`(("submittedDate", "[YYYYMMDD0000 TO YYYYMMDD2359]"),)`（T5 AND 进 search_query）。"""
        today = now if now is not None else _today()
        lower = self.lower_bound(state, now=today)
        return ((self.param, f"[{lower:%Y%m%d}0000 TO {today:%Y%m%d}2359]"),)

    def advance(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> DateState:
        """候选新水位（**未提交**）；`seen` = 本次已见条目的提交日期文本。"""
        today = now if now is not None else _today()
        path = f"sources.{self.source}"
        current = _opt_date_state(state, path=path)
        base = (
            _initial_lower_bound(self.initial_lookback_days, today)
            if current is None
            else _parse_date(current.date, path=f"{path}.date")
        )
        return DateState(_advance_date(base, seen, today=today, path=path).isoformat())

    def to_payload(self, state: SourceState) -> dict[str, object]:
        current = _as_date_state(state, path=f"sources.{self.source}")
        return {_KIND: self.kind, _STATE_FIELD_DATE: current.date}

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

    def lower_bound(self, state: SourceState | None, *, now: date | None = None) -> date:
        """本次窗的下界 = 水位 − `overlap_days`（含端）；首跑 = 今天 − 初窗回看天数。"""
        today = now if now is not None else _today()
        current = _opt_date_state(state, path=f"sources.{self.source}")
        if current is None:
            return _initial_lower_bound(self.initial_lookback_days, today)
        return _parse_date(current.date, path=f"sources.{self.source}.date") - timedelta(
            days=self.overlap_days
        )

    def window_params(
        self, state: SourceState | None, *, now: date | None = None
    ) -> tuple[tuple[str, str], ...]:
        """`((param, "YYYY-MM-DD"),)`，另按 `until_param`/`range_suffix` 补上界形态。"""
        today = now if now is not None else _today()
        lower = self.lower_bound(state, now=today)
        params = [(self.param, f"{lower.isoformat()}{self.range_suffix}")]
        if self.until_param is not None:
            params.append((self.until_param, today.isoformat()))
        return tuple(params)

    def advance(
        self, state: SourceState | None, seen: Sequence[str], *, now: date | None = None
    ) -> DateState:
        """候选新游标（**未提交**）；`seen` = 本次已见条目的发表/登记日期文本。"""
        today = now if now is not None else _today()
        path = f"sources.{self.source}"
        current = _opt_date_state(state, path=path)
        base = (
            _initial_lower_bound(self.initial_lookback_days, today)
            if current is None
            else _parse_date(current.date, path=f"{path}.date")
        )
        return DateState(_advance_date(base, seen, today=today, path=path).isoformat())

    def to_payload(self, state: SourceState) -> dict[str, object]:
        current = _as_date_state(state, path=f"sources.{self.source}")
        return {_KIND: self.kind, _STATE_FIELD_DATE: current.date}

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

    def window_params(
        self, state: SourceState | None, *, now: date | None = None
    ) -> tuple[tuple[str, str], ...]:
        """恒空：本策略无日期下推面（拉取范围 = T5 的 feed 预算，非查询参数）。"""
        _opt_id_set_state(state, path=f"sources.{self.source}")
        return ()

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

    def to_payload(self, state: SourceState) -> dict[str, object]:
        current = _as_id_set_state(state, path=f"sources.{self.source}")
        return {_KIND: self.kind, _STATE_FIELD_IDS: list(current.ids)}

    def parse_state(self, payload: Mapping[str, object], *, path: str) -> IdSetState:
        # kind 先判：策略不符时给"换策略须显式迁移"而不是"未知字段 ids"这种误导消息。
        _require_kind(payload, expected=self.kind, path=path)
        _reject_unknown(payload, (_KIND, _STATE_FIELD_IDS), path=path)
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
        return IdSetState(ids)


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
    _reject_unknown(payload, (_KIND, _STATE_FIELD_DATE), path=path)
    if _STATE_FIELD_DATE not in payload:
        _fail(f"{path}.{_STATE_FIELD_DATE}", "必填字段缺失")
    text = _require_str(payload[_STATE_FIELD_DATE], path=f"{path}.{_STATE_FIELD_DATE}")
    # 归一为 `YYYY-MM-DD`：文档里写 `2026-07-25T10:00:00Z` 也认，但存回去是日期。
    return DateState(_parse_date(text, path=f"{path}.{_STATE_FIELD_DATE}").isoformat())


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
    """
    strategy = strategy_for(source)
    return watermark.with_state(
        source, strategy.advance(watermark.state_for(source), seen, now=now)
    )


__all__ = [
    "DEFAULT_INITIAL_LOOKBACK_DAYS",
    "DEFAULT_MAX_IDS",
    "DEFAULT_OVERLAP_DAYS",
    "KIND_DATE_CURSOR",
    "KIND_DATE_UPPER_BOUND",
    "KIND_ID_SET",
    "SCHEMA_VERSION",
    "STRATEGIES",
    "DateCursor",
    "DateState",
    "DateUpperBound",
    "IdSetDiff",
    "IdSetState",
    "SourceState",
    "Watermark",
    "WatermarkStrategy",
    "advance",
    "strategy_for",
    "window_params",
]
