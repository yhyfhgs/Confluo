---
title: 全文抽取（stage 5 extract）实现级详设
status: review
owner: fable5
updated: 2026-07-27
---

# 12 · 全文抽取（stage 5 extract）实现级详设

> **状态**：`review`（P7-T1 起草 2026-07-27 → 独立审查 NEEDS_FIX → **修订 r2 已吸收 7 必修 + 7 P2**；
> 终签权在 fable，签署后转 `approved`）。落 [D-033](../plan/decision-log.md)。
> **已由 fable 正式裁决的两项**（原 proposed → **approved 2026-07-27**）：`HttpClient.post_multipart`
> 纯附加扩展（§7.1）、空口令加密 PDF 姿态（§2.3，实现约束加严至五条）。
> **本文交付设计，不含实现**——落地是 T7 卡（[phase7-implementation-plan §4](../plan/phase7-implementation-plan.md)）。
> **承接**：[phase7 计划 §2 冻结件表 D-033 行 + §4 T1 卡](../plan/phase7-implementation-plan.md)、
> [design/05 §1 阶段表 stage 5 行](05-pipeline.md)（幂等键注记「asset 级键随 Phase 7 真实抽取启用」）、
> [design/06 §2 `fulltext` 表 + §4 文件存储布局](06-data-model.md)。
> **接缝**：`pipeline/stages.py::_stage_extract`（现 noop）、`_asset_final_path`（落位函数族）、
> `pipeline/runner.py::_fetched_pdf_assets`（extract 子任务圈选）、`config.py::_FIELD_SPECS`、
> `http.py::HttpClient`（GROBID 客户端复用）、`verify.py`（T14 消费）。
> **红线**：[AC-0](../testing/acceptance-criteria.md) 五条 —— 本文 §2 为硬约束段，先于一切方案；
> 尤其 **AC-0.3「PDF 不出现在 git 历史」直接否决了「仓库内小样本 PDF」的 fixture 形态**（§8）。
> **决策依据**：D-001（技术栈/依赖姿态）、D-004（六阶段幂等不变式）、D-007（双条 paper 双份全文）、
> D-014（诚实 UA / 不绕软门）、D-023（可选依赖分界线）、D-031（顺序无关的全序取 max 纪律，本文 §5.3 直接沿用）、
> D-032（config-home 可迁移 ⇒ 落盘路径形态，§5.4）。

## 0. 本文定位与交付边界

本文冻结 Phase 7 `extract` 阶段的**语义面**，不冻结实现细节。冻结项六条（对应 T1 卡必须裁决的六问）：
抽取器选型（§3）、`TextExtractor` Protocol（§4）、asset 级幂等键与重跑/断点语义（§5）、
失败态与 `ingest_state` 机（§6）、GROBID 降级链（§7）、离线 fixture 策略（§8）。
另附**下游卡消费面**（§9）：T14 `verify` 扩展所需的三类对账口径（含 si 孤儿判定粒度，T14 卡指名由本卡裁决）。

**明确不在本文范围**：正文全文索引（FTS/向量）——归 D-034（T2 卡）与 [phase7 计划 §8](../plan/phase7-implementation-plan.md)
的 defer 条目；正文入 DB 已被 controller **否决**（只落文件 + `fulltext.text_path`）。

**五要素索引**（[doc-conventions §3](../process/doc-conventions.md)）：功能说明 §1 · 实现方案 §3–§9 ·
测试方法 §10 · 测试类型 §11 · 验收标准 §12。

## 1. 功能说明

### 1.1 现状与目标差

`stages.py::_stage_extract`（Phase 1 语义）对每个 `state='fetched'` 的 pdf asset 写一行
`fulltext(extractor='noop', extractor_ver='1', text_path=NULL, char_count=0)`，并把
`paper.ingest_state` 推到 `extracted`。幂等键实际是 **paper 级**（`fulltext` 表 PK = `paper_id`），
与 design/05 §1 表中登记的「(asset, extractor_ver)」不符——该表已自注「asset 级键随 Phase 7 真实抽取启用」。

目标差三项：① 真实抽取产物（文本落盘 + 字段落库）；② 幂等键落到 asset 级并给出重跑/断点语义；
③ 失败与降级两条非快乐路径的确定性行为。

### 1.2 两条路径的分工（controller 已裁，本文只做工程化）

| 路径 | 触发 | 产物 | 定位 |
|---|---|---|---|
| **纯文本（基线）** | 恒可用，无配置即生效 | `data/fulltext/{venue}/{year}/{ulid}.txt` | **基线路径**：AC-7.1 的达标载体；零外部服务依赖 |
| **GROBID（可选增强）** | `[extract] grobid_url` 已配置且服务在线 | `…/{ulid}.tei.xml`（TEI，含 header 结构化字段） | **可选增强**：不可用即降级为基线路径且不报错（AC-7.2） |

两条路径产出同一张 `fulltext` 行，靠 `extractor` 列区分；取代关系由 §5.3 的全序裁定，**不由到达顺序裁定**。

## 2. 合规段（硬约束，先于一切方案）

1. **AC-0.1/0.2 不触及**：extract 是本地纯计算（GROBID 亦为本机 REST 服务），不发起任何站点请求、
   不解风控、不绕付费墙。GROBID **零外网请求**是硬要求 → `consolidateHeader` / `consolidateCitations` /
   `consolidateFunders` **三者一律硬编码 0**（不设 config 槽）：GROBID 的 consolidation 会代为访问
   biblio-glutton/Crossref，开启即在用户不知情下从 extract 阶段发出外网请求，越过本项目的限速/预算/
   FetchLog 全部记账面。**三个参数必须逐一显式置 0**——漏写一个就漏一条外网通道，且不得依赖 GROBID
   的默认值（其默认值随版本变动过）。
2. **AC-0.3（PDF 不入 git 历史）是本文 §8 fixture 裁决的支配约束**：仓库 `.gitignore` 现有 `*.pdf`
   全局条目（任意层级），提交 fixture PDF 需 `git add -f` 强推——形式与实质都违反红线。
3. **加密 PDF 姿态**（**fable 已裁决 approve，2026-07-27**；实现约束按审查建议加严至五条）：
   - **允许空口令打开**（`decrypt("")`）——等价于任何阅读器打开该文件的常规行为，不涉及口令猜测；
     本项目持有的 PDF 均来自已授权通道（订阅/OA/开放窗），对已合法持有的文件做本地文本抽取属正常研究使用。
   - **只试一次空串**：`decrypt("")` 调用**至多一次**，失败即止——不重试、不变形（不试 `" "`、
     不试 `None`、不试 doi/标题等文档相关串）。
   - **禁止任何回退口令列表**：代码里不得出现候选口令常量、口令文件读取、或「常见 owner password」
     之类的集合——**存在这样的数据结构本身即违规**，与它是否被执行无关。
   - **不实现权限位改写/绕过代码**：抽取器默认行为如何即如何，不为「禁止提取」权限位单独写旁路。
   - **`note` 不泄露口令强度信息**：非空口令一律记 `note='encrypted'` 这一个 token，
     **不得**分化出 `weak_password`/`password_length_n`/`rc4_vs_aes` 等携带破解线索的取值，
     obslog 同样只记该 token（一个「哪些文件的口令更好猜」的清单，本身就是破解辅助面）。
   - 红线在「绕过保护措施获取本无权访问的内容」，不在「对已持有文件做本地处理」——本条是该边界的显式落点。

## 3. 裁决①：纯文本基线抽取器 = **pypdf**

### 3.1 三轴对比

| 轴 | **pypdf**（选中） | pdfminer.six | PyMuPDF（参照） |
|---|---|---|---|
| **依赖纯度** | 纯 Python，运行时**零传递依赖**（Py≥3.11）；BSD-3 | 纯 Python 但拖 `charset-normalizer` + **`cryptography`**（Rust/二进制轮子）| C 扩展（MuPDF 二进制）+ **AGPL-3.0** |
| **维护活跃度** | py-pdf 组织维护，发布节奏密、issue 响应活跃 | 维护中但节奏明显慢；上游 pdfminer 原作已停更，`.six` 为社区续命分支 | 活跃，但商业双授权 |
| **抽取质量** | 文本层直取（含 `extraction_mode="layout"`）；对**数字原生学术 PDF**（本项目 100% 目标形态）足够，多栏阅读序不保证 | 真正版面分析（LAParams），多栏/表格阅读序更优；速度约慢一个数量级 | 最优 |

> ⚠ 未核验（离线设计卡）：上表的版本/依赖/许可事实取自设计期认知，**T7 装依赖时以 `uv pip show pypdf` +
> `uv.lock` + PyPI 元数据实测复核并回填本节**；若复核证伪「零传递依赖」，本裁决须重开（复核结果入 §14 修订记录）。

### 3.2 决定性理由（非「质量更高」）

1. **pdfminer.six 在本架构里是被两侧夹住的支配劣势项**：它相对 pypdf 的唯一实质优势是版面分析
   （多栏阅读序、块结构），而这**恰好是 GROBID 覆盖的那一格**（GROBID 走 pdfalto + CRF 序列标注，
   结构化质量远在 pdfminer 之上）。要结构化就该走 GROBID；只要基线，pypdf 已达标。
2. **它换来的代价正好踩本仓已划定的依赖分界线**：`pyproject.toml` 现有注释明写「核心 dependencies
   不含加密/浏览器件」，`cryptography` 是 `[auth]` extra 的成员（D-023）。为一个被 GROBID 支配的
   质量增量，把 `cryptography` 从 opt-in extra 提升为**核心必装**，是净负收益。
3. **PyMuPDF 直接因许可出局**：AGPL-3.0 与本仓 `license = { text = "Proprietary" }` 冲突，无需进入质量比较。

### 3.3 依赖落位：**核心 `dependencies`，不做 extra**

pypdf 进 `[project] dependencies`（而非 `[project.optional-dependencies]`）。理由：extra 的既有分界线是
「重/二进制/浏览器件」（D-023：`cryptography`、`keyring`、`playwright`），pypdf 三项皆不沾；做成 extra 会
凭空造出「stage 5 不可用」这一降级态，而该态**无验收载体**（AC-7.1 无条件要求抽取产出），且与 AC-7.2
的「GROBID 关闭时降级为纯文本」形成两级嵌套降级，语义面复杂度远超收益。

**回滚触发条件**（写死备查）：若 T7 复核发现 pypdf 引入非纯 Python 传递依赖，或安装体积超 5 MB，
则降级为 `[extract]` extra + 惰性 import，且 AC-7.1 载体同步声明「需 `--extra extract`」。

### 3.4 已知能力缺口（如实入档，不修）

- **AES 加密 PDF**：pypdf 无 `cryptography` 时不能解 AES-256 → `extract_failed(note='encrypted')`。
  这恰是我们**不愿为之拖依赖**的场景（学术 PDF 极少 AES 加密，且加密面常带 DRM 气味，见 §2.3）。
- **纯图像扫描件**：无文本层 → 抽出空串 → `extract_failed(note='image_only')`。**不引入 OCR**（重依赖 +
  质量不可控 + 无消费场景，YAGNI）；目标 venue 全为数字原生投稿，扫描件属长尾。
- **多栏阅读序**：基线路径不保证；需要正确阅读序的消费方走 GROBID 路径。

## 4. 裁决②：`TextExtractor` Protocol 与 `ExtractedText`

```python
# 设计伪代码 —— pipeline/extract.py（新模块）

@dataclass(frozen=True)
class ExtractedText:
    """一次抽取的全部产物（纯值对象，无 DB/文件副作用）。"""
    text: str                      # 落盘正文（.txt 全文 / .tei.xml 的 XML 源）
    extractor: str                 # "pypdf" | "grobid"（落 fulltext.extractor）
    extractor_ver: str             # 抽取器版本串（库版本 / GROBID 服务版本）
    suffix: str                    # ".txt" | ".tei.xml" —— 决定落位文件名
    char_count: int                # **可见文本**字符数（TEI 路径取 itertext，不含标签，§7.3）
    lang: str | None = None        # TEI @xml:lang；纯文本路径恒 None（§4.2）
    title: str | None = None       # TEI titleStmt/title；纯文本路径 None（AC-7.1 判据分叉，§12）
    note: str | None = None        # **判别信息**（非判决）：'encrypted'|'image_only'|'corrupt'|'empty_text'
                                   # 抽取器答"看到的是什么"，handler 才决"算不算失败"（§4.1 末条）

class TextExtractor(Protocol):
    """抽取器契约：路径进、值对象出。无 DB、无 Config、无网络语义泄漏。"""
    name: str                      # 与 ExtractedText.extractor 同值（登记进 _EXTRACTOR_RANK）
    version: str                   # 同 extractor_ver；**构造期即可知**（§5.2 幂等键前置可判性的前提）
    def extract(self, source: Path) -> ExtractedText: ...
```

### 4.1 签名裁决要点

- **输入 = `Path` 单参**，不是 asset 行/paper 行/`StageContext`。抽取器不该知道 DB 的存在——
  这让「构造 fake extractor 注入」成为一行测试代码，也让抽取器可在 T19 的一次性脚本里裸用。
- **输出 = 值对象**，不是 `(str, dict)` 元组：`char_count`/`lang`/`title`/`suffix` 四项都是
  **抽取器才知道**的信息，让 handler 去猜（例如从 suffix 反推 extractor）必然出现口径漂移。
- **`suffix` 由抽取器给**（而非 handler 按 extractor 名查表）：落位后缀是产物形态的一部分，
  第三方抽取器（如未来的 OCR/JATS 路径）可自带后缀而不改 handler。
- **`version` 在构造期可知**（属性，非 `extract()` 的返回派生）：这是 §5.2「幂等键抽取前可判」
  的硬前提——若版本只能在抽完后知道，「幂等跳过」就退化成「抽完再比」，白烧 CPU。
- **失败语义**：`extract()` 对「文件在、但抽不出」**不抛异常**，返回 `char_count == 0` 的
  `ExtractedText`；判失败与落 `extract_failed` 是 handler 的职责（§6）。对「文件不存在/不可读」抛
  `CrawlerError(ErrorClass.INTEGRITY)`（§6.1 第 1 类）。抽取器不做错误分类学决策。
  **判据取 `char_count == 0` 而非 `text == ""`**：纯文本路径二者等价，但 GROBID 路径的 `text` 是 TEI
  **XML 源码**（header-only 空产物时 XML 非空而可见文本为零）——用 `text == ""` 会漏判 §6.1 的
  header-only 反例。`char_count` 是两条路径唯一同口径的量（§7.3），故它是**唯一**的零输出判据。
- **`note` 是判别信息、不是判决**（审查 P0-1 修正）：只有抽取器能分辨「加密 / 无文本层 / 结构损坏 /
  有文本层但抽出空」——这是**观测**，不是分类学决策；handler 拿到 `text==""` 却无从复原是哪一种，
  §6.1 的四元 `note` 闭集就无法生产。分工线因此精确化为：**抽取器报「看到的是什么」，handler 决
  「算不算失败、落哪个 `state`」**。抽取器**不得**据此自行落库、自行抛异常或自行降级。
  成功抽取（`char_count > 0`）时 `note` 恒 `None`；`char_count == 0` 时 `note` **必须**非空（T7 加断言锁定）。

### 4.2 `lang` 恒 None（纯文本路径）的理由

不引入语言识别依赖（`langdetect`/`fasttext` 皆为新依赖，后者还是重件）。**错误的 `lang` 比 NULL 更坏**：
NULL 的语义是「未知」，下游可正确地不过滤；错值会让下游静默漏掉论文。当前 `lang` 无任何消费方
（D-034 的 FTS 范围是 title+abstract，不读 fulltext），故本 Phase 保持诚实 NULL；GROBID 路径顺带
从 TEI 取到就填。出现真实消费方时再评估（YAGNI）。

## 5. 裁决③：asset 级幂等键 + 重跑/断点语义

### 5.1 schema 增量（**纯附加 5 列**，无破坏性变更）

```sql
-- 设计伪代码 —— migrations/000N_fulltext_asset.sql（编号见下方注记）
ALTER TABLE fulltext ADD COLUMN asset_id      TEXT REFERENCES asset;  -- 产物来自哪个 asset
ALTER TABLE fulltext ADD COLUMN source_sha256 TEXT;   -- 抽取时源文件的 sha256（陈旧判据）
ALTER TABLE fulltext ADD COLUMN text_sha256   TEXT;   -- 落盘产物的 sha256（T14 hash_mismatch 依据）
ALTER TABLE fulltext ADD COLUMN state         TEXT;   -- 'extracted' | 'extract_failed' | 'noop'
ALTER TABLE fulltext ADD COLUMN note          TEXT;   -- 失败原因短 token（成功行 NULL）
UPDATE fulltext SET state = 'noop' WHERE extractor = 'noop' AND state IS NULL;  -- 存量回填
```

- **PK 保持 `paper_id`（1-1 不变）**：`design/06 §1` 的 ER 语义「Paper 1─1 Fulltext」不动。asset 级的是
  **幂等键**（§5.2），不是表的基数——把表改成 1-N 才叫改 ER 模型，本文不做（升级触发条件见 §5.6）。
- **迁移编号**：T2 卡（D-034）并行产出 FTS 迁移，两卡都要占下一个空号。**T7 实现时按
  `migrations/` 目录当时的最大编号 +1 取号**，本文一律以 `000N_fulltext_asset.sql` 占位，不写死数字。
- **存量 `noop` 行不删不改语义**：`state='noop'` 是第三个合法值，rank −1（§5.3，**低于
  `extract_failed`**）保证任何真实抽取结论——含「抽不出」这一结论——都取代它。
  存量 `paper.ingest_state='extracted'`（P1 noop 造成）**不回滚**（「只前进不回退」不破坏），但
  `verify`（T14）须把 `state='noop' AND text_path IS NULL` 如实报为「未真实抽取」，而非 orphan/missing。
- **方言中性**：五条 `ADD COLUMN` + 一条 `UPDATE`，SQLite/PostgreSQL 同构（design/06 §6 迁移纪律）。

### 5.2 幂等键 = `(asset_id, source_sha256, extractor, extractor_ver)`

**跳过判据**（handler 在**调用抽取器之前**求值 → 命中即返回 `"skipped"`，零 CPU、零写入、零 `updated_at` 抖动）：

1. 存量 `fulltext` 行的四元组与本次待抽的四元组**全等**；且
2. 成功行还需 `text_path` 指向的文件存在且其 sha256 == `text_sha256`
   （与 fetch 的 §5.3 `fetched_file_ok` 判据同构：DB 说有、盘上真有且没被改）；
   失败行（`state='extract_failed'`，`text_path IS NULL`）无文件可校，仅需条件 1。

四元组**抽取前全部可知**：`asset_id`/`source_sha256` 取自 asset 行（不重算文件哈希）；
`extractor`/`extractor_ver` 取自抽取器的构造期属性（§4.1）——GROBID 版本由每轮一次的前置探活取得（§7.2）。

**支配预判**（审查 P1-2 增补，与跳过判据同一次求值内完成）：四元组不全等、但存量行的
`(rank, ver_key)` 在 §5.3 全序下**严格大于**本次候选的 `(rank, ver_key)` ⇒ 本次注定是败者
（`char_count`/`asset_id` 两个低位维度不可能翻盘）⇒ **直接返回 `"skipped"`：不打开源文件、
不调抽取器、不向 GROBID 发一个请求**。典型命中：库里已有 GROBID TEI，而本轮 GROBID 关闭/不可用，
纯文本抽取器注定败在 rank ——若无此预判，每轮 pull 都会把全库 PDF 重抽一遍纯文本再全部丢弃。
预判只用 `(rank, ver_key)` 两个**抽取前可知**的维度，故不引入「先抽后判」；且它与全序取 max 同向
（跳过的恰是必败者），不改变终态，顺序无关性不受影响。**残余成本如实入档**：`(rank, ver_key)` 平局
时（同抽取器同版本、不同 asset）仍须实抽才能比 `char_count` —— 见 §5.6。

### 5.3 取代规则 = **全序取 max**（顺序无关，沿 D-031 纪律）

未命中跳过判据时，抽取产物与存量行按下列**全序**比较，取 max 写入；本次为败者则**不写文件、不改 DB**
（handler 返回 `"done"` 并落 obslog 说明被既有更优产物压制）。

```
key(row) = (rank, ver_key, char_count, asset_id)

rank:  grobid = 2 | pypdf = 1 | extract_failed = 0 | noop = -1 | **陈旧行 = -2**
       （未登记的 extractor 名 → rank -1（与 noop 同档）并 WARN：不得压制已登记的真实抽取器）
ver_key: 版本串中前三段数字，不足补 0（"5.1.0" → (5,1,0)；无数字 → (0,0,0)）
char_count: 可见文本字符数（§7.3 统一口径——跨 extractor 必须同口径，否则该维度无意义）
asset_id: ULID 字典序，最终 tie-break（保证全序，无并列）；**legacy 行 `asset_id IS NULL` 归一为 ""**
       （空串排在一切 ULID 之前 ⇒ 同 rank 同 ver 同 char_count 时 legacy 行必败，语义正确）
```

- **`extract_failed`(0) 必须高于 `noop`(-1)**（审查 P1-1 修正，原稿把二者写反）：`noop` 是 Phase 1 的
  **占位空行**（无任何抽取事实），`extract_failed` 是**已判定的抽取结论**（真的抽过、真的抽不出）。
  若 noop 更高，存量 noop 行会永久压制真实失败行 ⇒ 失败结论写不进库 ⇒ §5.2 的幂等键永远命不中 ⇒
  **每轮 pull 对同一批长尾扫描件重抽一次**（审查实测反例）。修正后：首次抽取失败即落 `extract_failed`
  取代 noop，此后重跑命中幂等键 `"skipped"`。
- **陈旧判据（rank -2）**：存量行的 `source_sha256` ≠ 其 `asset_id` 所指 asset 行的**当前** `sha256`
  ⇒ 该产物出自一份已被替换的源文件，作废。**这不破坏顺序无关性**：陈旧与否是 DB 当前状态的函数，
  不是到达顺序的函数。**legacy 归一**（P2-③）：`asset_id IS NULL` 的存量行（P1 noop 行必然如此）
  无从取 asset 的当前 `sha256`，**一律不判陈旧**（走 rank -1 的 noop 档），避免 `NULL` 比较把
  「未知」误判成「陈旧」；该分支实际不可达（noop 行 rank 已最低），仍写死以免 T7 实现时按 SQL
  三值逻辑自由发挥。
- **`ver_key` 优先于 `char_count`**：版本是抽取器能力的显式声明，`char_count` 只是启发式。
  同版本内才用 `char_count` 分胜负——典型场景是同 paper 的两个 pdf asset（正刊版 vs OA 兜底版），
  文本更长者通常是完整版（与 D-031 §2「更长者胜」的取舍同源：截断版不该恒压制完整版）。
- **为什么必须是全序取 max**：max 是幂等 + 交换 + 结合的半格运算 ⇒ 终态是**输入集合**的函数、与注入
  顺序无关。这是 D-031（AC-3.4）已经付过一次学费的纪律，extract 面不重犯：否则「先跑 GROBID 后跑
  纯文本」与反序会得到不同的库状态。

### 5.4 落盘布局与路径契约

沿 design/06 §4：`data/fulltext/{venue_id}/{year}/{paper_ulid}.txt|.tei.xml`。

- **新增 `_fulltext_final_path(config, venue_id, paper, suffix)`，与 `_asset_final_path` 并列**，
  二者共用 `{venue}/{year}/{ulid}` 键构造小件。
  **裁决：不往 `AssetKind` 加 `fulltext` 枚举值**（T1 卡文本的「`_asset_final_path` 扩 fulltext kind」
  按此读法执行，列入偏离清单）。理由：`AssetKind` 是 **resolve 契约的上游资产类型**（adapter 声明什么
  可取回），fulltext 是**本地派生产物**；混入会污染 `asset` 表的 `UNIQUE(paper,kind,version)` 语义、
  adapter 能力声明面与 fetch 落位分支，换来的只是一个函数的复用。`_asset_final_path` 对
  html/bibtex/source 响亮抛 CONFIG 的既有行为**不变**。
- **`venue_id` 取 `_task_venue(task)`**（与产生该 pdf 的 fetch 落位同源），保证
  `pdf/{v}/{y}/{ulid}.pdf` 与 `fulltext/{v}/{y}/{ulid}.txt` **同 v/y 对位**——verify 对账与人肉查阅都依赖它。
  `paper.year` 为 NULL 时落 `unknown` 子目录（与 `_asset_final_path` 同规则）。
- **`fulltext.text_path` 落「相对 `data_dir` 的相对路径」，且写死为不含 `data/` 前缀的形态**
  （审查 P1-4 修正）：

  ```
  text_path = "fulltext/{venue_id}/{year}/{paper_ulid}{suffix}"      ← 正确（无 data/ 前缀）
  text_path = "data/fulltext/{venue_id}/{year}/{paper_ulid}{suffix}" ← 错误（全库 missing_file）
  ```

  `verify.py::_resolve` 把相对路径挂在 `Config.data_dir` 下，而 `data_dir` **本身就指向 `…/data`**；
  照抄带前缀的写法会解析成 `…/data/data/fulltext/…`，使**全库每一行都报 `missing_file`**。
  三条选择理由：① config-home 可整体迁移（D-032 刚发生过一次），绝对路径迁移后全库失效，相对形态免疫；
  ② `verify._resolve` 已支持相对形态，T14 零改造消费；③ 与 §5.4 的落位纯函数同源，可反解。
  **T7 必须同步改两处列注释**（审查实地核证，现均含 `data/` 前缀，照抄即踩坑）：
  `docs/design/06-data-model.md:136` 与 `src/paper_crawler/storage/migrations/0001_init.sql:113`
  的 `-- data/fulltext/{...}.txt|.tei.xml` → `-- fulltext/{...}.txt|.tei.xml（相对 data_dir）`。
  **如实入档的债务**：`asset.file_path` 现存**绝对**形态（`stages.py:518/627` 写 `str(final_path)`），
  与本列形态不一致；本卡**不改** asset 侧（改动会使存量库路径全失效、需数据迁移，且属独立清账面），
  `verify` 的双形态兼容已覆盖两者。登记为 P8 清账候选。
- **换 extractor 导致的旧产物孤儿**：`.txt` → `.tei.xml` 升级时旧文件必须删。顺序见 §5.5 第 4 步；
  删除加路径护栏（仅当旧路径位于 `data_dir/fulltext/` 下且 ≠ 新路径）。

### 5.5 重跑 / 断点 / 崩溃语义

写入序（沿 design/05 §5.2 的 fetch 先例，复用 `PartFileIO`）：

1. 求值幂等键 → 命中则 `"skipped"`（§5.2），**流程到此为止**；
2. 抽取 → 得 `ExtractedText`；与存量行比全序（§5.3），败者 `"done"` 且零写入；
3. 写 `data/tmp/*.part` → 校验 → **原子 rename** 到 `_fulltext_final_path()`；
4. DB `upsert fulltext`（含 `text_sha256`）→ **最后**删被取代的旧产物文件。

崩溃点逐一：

| 崩溃于 | 残留 | 恢复 |
|---|---|---|
| **窗 1**：步 3 之前/之中 | `data/tmp/*.part` | 启动期既有 `.part` 清理机制（design/05 §5.2）；重跑重抽，无副作用叠加 |
| **窗 2**：步 3 与步 4 之间 | 新产物文件已就位、DB 未更新 | 重跑：幂等键不命中 → 重抽 → **落位路径是纯函数**，同内容覆写同一路径，不产生第二份垃圾。verify 侧分两种（P2-② 修正）：**换后缀**时新文件无人引用 → `orphan_file`；**同后缀覆写**时旧行仍引用该路径、但盘上已是新内容 → **`hash_mismatch`**（`text_sha256` 是旧的），**不是** `orphan_file` |
| **窗 3**：步 4 与旧文件删除之间 | 旧后缀产物成孤儿 | `verify` 报 `orphan_file` + suggestion `prune`；重跑 extract 命中幂等键跳过，**不会自愈**——由 verify 处置（如实入档） |

**排序依赖如实入档**（P2-②）：窗 2/3 的检出工具是 `verify` 的 fulltext 维度，而它归 **T14（W2 波次）**；
T7 落地在 **W1**。故 **T7 合并后到 T14 合并前的窗口内，这两类残留无自动检出手段**——可接受
（发生概率＝恰在两步之间崩溃，且后果限于一份多余文件/一次哈希不符，无数据丢失），但 T7 的报告须
显式登记该缺口，T14 合并后由一次全库 `verify` 亲跑收口（T19 已含全库 verify）。

`--force`（既有 runner 语义）绕过**任务级** fresh_skip，但**写入判据仍走 §5.3 全序**——故 force
**不降偏序**（P2-① 措辞修正）：它不可能用 pypdf 覆盖已有的 GROBID TEI（rank 更低）。但**「不降偏序」
不等于「产物只会变好」**——同 rank 下版本升级（`ver_key` 更高）即使 `char_count` 腰斩也会取胜，
因为 `ver_key` 位序高于 `char_count`（§5.3）。这是有意的取舍（版本是能力的显式声明，字数只是启发式），
但代价必须如实说出来：抽取器版本回归（新版反而抽得更差）会静默覆盖更完整的旧产物，唯一取证面是
obslog 里前后两行的 `char_count`。`--force` 的语义是「重做这次运算」，不是「无视偏序改写库」。

### 5.6 圈选范围与升级触发条件

- **只对 `kind='pdf' AND state='fetched'` 的 asset 建 extract 任务**（`runner.py::_fetched_pdf_assets`
  现状即如此，不改）。si/html/bibtex/source **不抽**（AC-7.1 只关乎主全文；SI 形态过散，无消费方）。
- **1-1 模型的已知代价（两项，缺一不可）**：
  1. **信息丢失**：同 paper 多 pdf asset 时只有全序胜者的产物入库；败者/失败者的信息只留 obslog
     （WARN 含 asset_id 与原因），DB 无痕。
  2. **重复算力**（审查 P1-2 补记，原稿漏列）：§5.2 的支配预判只能挡住 `(rank, ver_key)` **严格劣势**
     的候选；**平局**时（同抽取器同版本、不同 asset——正是「一 paper 两个 pdf asset」这一最常见形态）
     仍须**实抽**才能比 `char_count`，抽完再丢弃败者。即：每轮 pull 对多 asset paper 的次要 asset
     恒有一次无效抽取。量级可控（纯文本抽取是本地 CPU、单篇亚秒级；GROBID 路径因预判挡不住而**会真的
     发请求**，但仍是本机服务、零在线预算），**不做优化**——要根治须记「每个 asset 各自的 char_count」，
     那就是下面的 1-N 升级，不值得为此提前付表结构代价。
  **升级触发条件**：出现「需要 per-asset 抽取产物矩阵」的真实消费方（例如正刊版 vs preprint 版逐版本
  比对），或上述重复抽取在实测中成为可观成本时——建 1-N `fulltext_asset` 表并把本表降为视图，挂 P8 评估。

## 6. 裁决④：失败态 `extract_failed` 与 `ingest_state` 机

### 6.1 失败三分（抛 / 不抛的分界）

| 类 | 判据 | 处置 |
|---|---|---|
| **1. 库↔文件不一致** | asset 行称 `fetched`，但 `file_path` 文件缺失 / sha256 不符 | **抛 `CrawlerError(INTEGRITY)`** → 任务 FAILED。理由：这是可修复的**库缺陷**（re-fetch / verify 的正管辖区），静默记 `extract_failed` 会把它伪装成「这篇抽不出来」，永久掩盖 |
| **2. 源文件在、但抽不出** | 抽取器返回 `char_count == 0`（加密（非空口令）/ 纯图像 / 结构损坏 / 有文本层但抽出空）——**两条路径同判据** | **不抛、不失败任务**：落 `fulltext(state='extract_failed', text_path=NULL, char_count=0, note=<token>)`，obslog WARN，handler 返回 `"done"` |
| **3. 编程/配置错误** | asset 行不存在 / `state != 'fetched'` | **抛 `CrawlerError(CONFIG)`**（现状行为，保留） |

`note` token 闭集：`encrypted` / `image_only` / `corrupt` / `empty_text`（未来新增须同步本表）；
token 由抽取器作为**判别信息**给出（§4.1 末条 P0-1），handler 只做「算不算失败」的判决。

**GROBID 产物的零输出必须走同一判据 + 触发纯文本兜底**（审查 P0-2 修正，本节最关键的一条）：
GROBID 对一份 image-only PDF 会返回**语法合法但只有 header 的 TEI**（HTTP 200、XML 合法、
`<text>` 可见文本近乎为零）。若只按「200 且 XML 合法」就判成功，该产物会以 rank 2 **压制**同 paper
已有的 pypdf 五万字正文（审查实测反例）——一次「增强」反而抹掉了基线成果。故：

- **判据统一**：`char_count == 0`（§7.3 的可见文本口径）⇒ 该次 GROBID **无有效产出**，等同「服务
  没给出可用结果」，与 §7.2 矩阵里的一切降级同类；
- **处置统一**：**立即以纯文本抽取器兜底重抽同一份 PDF**（走 §7.2 已有的降级路径，不是新路径），
  再按 §5.3 全序比较入库。语义因此收敛成一句话：**「GROBID 无有效产出 → 纯文本」**——不区分
  成因是服务不可用、超时、非法 TEI、还是 header-only 空产物；
- 兜底后纯文本仍 `char_count == 0` ⇒ 才落第 2 类 `extract_failed`（`note` 取纯文本抽取器给的 token）；
- obslog 记 `grobid_empty_tei` reason token（与 §7.2 的其余 token 同一取证面）。

### 6.1a `char_count == 0` 判据的边界说明

极短但真实的全文（例如一页勘误、单页 comment）不会命中：判据是**严格等于 0**，不设经验阈值。
设阈值需要一个未经标定的魔数，且会把真实短文误判成失败（fail-closed 方向错）；零字符则是无歧义的
「没有任何可见文本」。若 T19 实测发现 GROBID 存在「输出个位数字符的伪产物」形态，再以实测数据提出
阈值修订（同 §12 的阈值标定纪律），不在本卡预设。

**第 2 类不失败任务的理由**（本文最容易被质疑的一条，故完整给出）：extract 是本地纯计算，第 2 类失败的
唯一成因是**源文件本身的性质**——既非瞬态（重试零收益）、也非 adapter 腐化（§4 错误分类学里 `parse` 类的
升级路径是「canary 标红」，语义是「解析器与站点漂移了」）。把一张扫描版 PDF 判成 `FAILED(parse)` 会让
`pull --extract` 在长尾数据上批量飘红，淹没真信号，且这些任务会永久占据 retry 队列却永不可能成功。
`extract_failed` 行就是它们的终态记录，可查询、可统计、可被后续更强抽取器（§5.3 rank -1）自动取代。

**幂等**：第 2 类失败行同样受 §5.2 保护——同 `(asset, sha256, extractor, ver)` 重跑命中四元组 → `"skipped"`，
不重复抽取一个已知抽不出的文件。

### 6.2 `ingest_state` 机：**不加第五值**

`paper.ingest_state` 保持四值 `metadata_only|resolved|fetched|extracted`，**`extract_failed` 不进这个阶梯**。

理由：该阶梯是**单调前进**的进度轴（design/06 §2 + `_stage_ingest` 的「只前进不回退」），而
「失败」不是「fetched 之后的一站」——把它塞进去会立刻破坏单调性（失败后再成功要从 `extract_failed`
跳回 `extracted`，一个本该无环的轴上出现回边），并污染所有按 `ingest_state IN (...)` 取范围的既有查询。

于是：**成功 → `set_paper_state(paper, 'extracted')`（现状行为）；失败 → 不动 `ingest_state`（停在 `fetched`）**。
「这篇 fetched 了但没有全文」的事实由 `fulltext.state` 列承载，语义精确且可与 `note` 联查。

状态机（设计伪代码）：

```
paper.ingest_state:  metadata_only → resolved → fetched → extracted      （单调，无回边）
                                                    │  ▲
                                                    │  └── 仅当本轮全序胜者 state='extracted'
                                                    └───── 失败/被压制：原地不动

fulltext.state:      noop ──┐
                            ├──→ extracted  ⇄  extract_failed   （由 §5.3 全序裁定，非时序）
                     (缺行) ─┘
```

## 7. 裁决⑤：GROBID 降级链

### 7.1 config 槽与客户端接缝

```python
# 设计伪代码 —— config.py::_FIELD_SPECS 追加两项（纯附加，与 T6 的 [browserfetch] 槽同区域）
_FieldSpec("extract.grobid_url", ("extract",), "grobid_url", "str",
           env="PAPER_CRAWLER_GROBID_URL", default=None)          # None = 关闭（默认形态）
_FieldSpec("extract.grobid_timeout_s", ("extract",), "grobid_timeout_s", "int",
           env="PAPER_CRAWLER_GROBID_TIMEOUT_S", default=60)
```

**只两槽**：开/关由 `grobid_url` 是否为空表达（无需第三个 `mode` 槽）；`consolidateHeader` /
`consolidateCitations` / `consolidateFunders` 三者一律硬编码 0（§2.1 + §7.2 末段）。
两槽皆非敏感（不进 `config show` 脱敏面）。**CLI 零改动**——extract 已可经 `crawler run extract` 与
`pull --extract` 驱动，本卡不碰 `cli.py`（该文件在 phase7 §5 已是 T3/T6/T12/T13 四卡的冲突面）。

**客户端 = 复用 `http.HttpClient`**，构造参数 `rate_limiter=None`、`timeout_s=grobid_timeout_s`、诚实 UA：

- **不注册 RateLimiter 桶、不写 FetchLog**：GROBID 是本机服务不是站点，限速无意义；更要紧的是
  **FetchLog 是在线预算的唯一事实源**（D-030 §7.2），把本地调用记进去会直接污染预算派生口径。
- 复用 `HttpClient` 而非裸 `httpx.Client` 的收益：既有 `transport=` 注入缝 ⇒ mock GROBID 两模式测试
  **零新基建**；错误映射与 obslog 记账沿用同一套；UA 诚实（D-014）全库一致。
- **对 `HttpClient` 做一处纯附加扩展**：新增 `post_multipart(url, *, files, data) -> bytes`
  （GROBID 走 `multipart/form-data`，现有 `post_json` 不覆盖）。这是**接口冻结件 §2.1 的纯附加扩展**
  （不改任何既有签名），先例＝`extra_headers` 参数（P4 plan §7-4）与 `CrawlerError.status_code`（P4）。
  **fable 已裁决 approve（2026-07-27）**：纯附加 + 两处成文先例，且退路（自建 `httpx.Client`）的
  双份维护代价更大。T7 落地时须与 `post_json` 同构地走 `_request`（同一限速闸/obslog/错误映射路径），
  不得另起一条绕过既有记账的请求通路。

### 7.2 前置探活 + 逐篇处置矩阵

**每轮运行一次前置探活**（不是每篇）：`GET {grobid_url}/api/isalive` + `GET {grobid_url}/api/version`。
结果（可用性 + 服务版本）惰性构造并缓存在 `StageContext` 的**新增可选字段**上
（纯附加，先例＝P4 的 `ctx.unpaywall_adapter`）。

前置探活是本节的结构性选择，理由有二：① 「服务根本没起」是最常见的关闭形态，一次判定即可，
避免 N 篇 × 连接超时的空转；② 它把「服务不可用」与「本篇处理失败」在**信号层面**分开，
handler 无需从 `CrawlerError` 的类型去反推是哪种（连接失败与读超时在错误分类学里同为 `TRANSIENT`，
不可区分）。版本串同时供 `extractor_ver`（探活成功但版本端点失败 → `"unknown"`）。

| 条件 | 行为 | 记忆本轮 | 理由 |
|---|---|---|---|
| `grobid_url` 为空 | 直接走纯文本 | — | **默认形态，非降级**：只在首篇落一条 INFO，不刷 WARN |
| 探活失败（连接拒绝/DNS/超时/非 200） | 整轮降级纯文本，WARN 一条 | **是** | 服务未起是持久态，逐篇重试是纯空转 |
| 逐篇 **读超时**（> `grobid_timeout_s`） | 本篇降级纯文本，WARN | **否** | 超时是 per-文档 的（大 PDF 慢），不代表服务不可用 |
| 逐篇 **503** | **退避重试一次**（经 `ctx.sleeper`，默认 5 s），再 503 则降级 | 否 | 503 是 GROBID 的队列背压信号（其文档明示），一次重试常能过；不做指数三退（本地批量堆积无意义） |
| 逐篇 **404** | 本篇降级 + WARN 明示「检查 `grobid_url` 是否指向服务根」 | **是** | 路径配错是持久的配置错误 |
| 逐篇 **连接失败/连接重置**（探活通过后服务挂掉、被 kill、容器重启） | 整轮降级纯文本，WARN 一条 | **是** | 审查 P1-3 补行：与「探活失败」**同类**（服务不在了），逐篇重连是纯空转；探活只证明**那一刻**在线，中途挂掉是真实且常见的形态（本机 GROBID 常跑在会被随手关掉的容器里） |
| 逐篇 **其它非 200**（4xx/5xx） | 本篇降级纯文本，WARN 带 status | 否 | 单文档特异性问题居多 |
| 200 但响应体非合法 TEI（空/非 XML） | 本篇降级纯文本，WARN | 否 | GROBID 产物不可用 ≠ 该文件不可抽 |
| 200 且 TEI 合法，但 **`char_count == 0`**（header-only 空产物） | 本篇降级纯文本，WARN | 否 | 审查 P0-2：**必须**与上面各行同路径处置，否则空 TEI 会以 rank 2 压制既有 pypdf 正文（§6.1） |

**不变式（AC-7.2 的形式化）**：上表每一行的 handler 出口都是 `"done"` 或 `"skipped"`——
**GROBID 相关的任何异常都不得逃逸出 extract handler**，也不得使任务 FAILED。降级只在 obslog 留痕
（WARN + reason token：`grobid_unreachable` / `grobid_timeout` / `grobid_http_<code>` /
`grobid_bad_tei` / `grobid_empty_tei`），**DB 无痕**（`extractor='pypdf'` 本身即事实）。
T19 的真实批从 obslog 取证。

**记忆的统一表述**：「记忆本轮」＝本次运行内此后不再调用 GROBID（含探活），全部走纯文本；
记忆只活在进程内（`StageContext` 缓存字段），**不落库、不跨运行**——下一次 `pull` 会重新探活，
故用户起好服务后无需清任何状态。

请求形态：`POST {grobid_url}/api/processFulltextDocument`，multipart 字段 `input=<pdf 字节>`，
form 参数 `consolidateHeader=0&consolidateCitations=0&consolidateFunders=0`（§2.1 硬编码；
**三个 consolidate 参数全部显式置 0**——P2-⑥：`consolidateFunders` 与前两者同样会让 GROBID 代为
外访，漏写一个就漏一条外网通道，且 GROBID 的默认值随版本变动过，必须显式而非依赖默认），
`Accept: application/xml`。

### 7.3 TEI 消费口径（`char_count` 必须同口径）

- **落盘**：TEI XML **原样**落 `.tei.xml`（结构化产物即交付物，design/06 §2 列注释已预留该后缀）。
- **`char_count` = TEI `<text>` 元素的可见文本字符数**（stdlib `xml.etree.ElementTree` + `itertext()`，
  **零新依赖**），**不是 XML 源码长度**。这不是洁癖：`char_count` 参与 §5.3 全序比较，若 TEI 路径混入
  标签字节而纯文本路径不混，该维度跨 extractor 立即失去可比性，全序就会系统性偏袒 TEI。
- `lang` ← 根元素 `@xml:lang`；`title` ← `teiHeader/fileDesc/titleStmt/title`（供 §12 的 AC-7.1 判据）。
- TEI 解析失败（非法 XML）→ 按 §7.2 末行降级，**不**判 `extract_failed`。

## 8. 裁决⑥：离线 fixture PDF 策略 = **程序化生成，零 `.pdf` 文件入库**

### 8.1 「仓库内小样本 PDF」被否决（T1 卡文本的偏离项，证据两条）

1. **AC-0.3 明文**：「凭证/session/**PDF** 不出现在 git 历史（`git log` 全历史扫描 + .gitignore 生效验证）」。
2. **`.gitignore` 现有 `*.pdf` 全局条目**（任意层级，仅 `!docs/**/*.pdf-placeholder` 一个例外）。
   提交 fixture PDF 必须 `git add -f` 强推——形式违规，且会让 AC-0.3 的守卫测试面出现「合法的例外」，
   侵蚀该红线此后一切执行力。

附带理由：真实站点 PDF 还带**版权面**（AC-0 的再分发红线邻域），即使红线不禁也不该入库。

### 8.2 三层替代（能力等价或更强）

| 层 | 形态 | 覆盖 |
|---|---|---|
| **L1 生成式 PDF** | `tests/helpers/minipdf.py::make_text_pdf(text, *, pages=1) -> bytes`：手写最小合法 PDF（base-14 Helvetica + `Tj` 文本算子，全 ASCII 源，约 1 KB），**零 `.pdf` 文件入库** | 快乐路径 + AC-7.1（标题可控注入 ⇒ 判据可精确断言）+ 多页 + 空页 |
| **L2 生成式负例** | 同模块：`make_image_only_pdf()`（仅内嵌 1×1 ASCIIHex 图像 XObject、无文本层）、`make_corrupt_pdf()`（截断 L1 字节）、`make_encrypted_pdf()`（trailer 挂 `/Encrypt` 字典触发加密判定，**不实现任何加密算法**） | §6.1 第 2 类四个 `note` token 全覆盖 |
| **L3 TEI 语料** | `tests/fixtures/grobid/*.tei.xml`（**自造**，纯文本可 diff、可入库、无版权面）+ `httpx.MockTransport` | AC-7.2 开模式 + `bad_tei` 降级支 |

**L1 优于「入库一个真 PDF」的实质点**（不只是合规让步）：生成器是**参数化**的——同一函数可造多页/空页/
超长文本/指定标题的任意组合，测试可直接断言「注入的标题被抽了出来」，而一份静态 PDF 只能测一个形态，
且其内容对 reviewer 是不可 diff 的二进制黑箱。

**生成器自校验（强制，P2-④）**：生成器换来的代价是**它自己可能有 bug**——一个语法非法的「合法 PDF」
会让抽取器抽出空串，测试却把这解读成「抽取器正确地判了 image_only」，于是**生成器缺陷伪装成被测行为**，
整组负例测试全部变成假绿。因此 T7 必须落一个**独立的 L1 自校验测试**（不经被测的抽取代码路径）：

- `make_text_pdf()` 产物的**结构自检**：`%PDF-` 头 + `%%EOF` 尾 + xref 表偏移可解析 + 对象计数与
  `/Count` 一致（纯字节级断言，零抽取器参与）；
- **正例锚定**：`make_text_pdf("SENTINEL")` 经抽取器必须抽出 `SENTINEL` —— 这条断言若红，说明
  **生成器坏了**（而非抽取器），测试消息必须显式这样写，否则将来的人会去改抽取器；
- **负例区分度**：`make_image_only_pdf()` 与 `make_corrupt_pdf()` 必须产出**不同的** `note` token
  （`image_only` vs `corrupt`）——若二者塌缩成同一 token，说明生成器没造出预期形态。

**真实 PDF 只出现在 T19 在线批**：运行时取开放许可样本（arXiv CC-BY / NBER >18 月开放窗），落
config-home 的 `data/`（`/.paper-crawler/` 整目录 gitignored，D-032），**不入仓库、不入 git 历史**。

### 8.3 GROBID 两模式的离线载体

`grobid_url` 指向一个**假 URL**，`HttpClient(transport=httpx.MockTransport(handler))` 注入：
handler 按路径分派 `isalive`/`version`/`processFulltextDocument`，并按用例返回 TEI / 503 / 404 /
连接异常 / 非法 XML —— §7.2 处置矩阵**逐行**可测，零真实 GROBID、零网络。

## 9. 下游冻结件（消费面）

### 9.1 T7（extract 核心落地）

`pipeline/extract.py`（新模块：Protocol + 两抽取器 + GROBID 客户端 + 降级链）；`_stage_extract` 改写
（幂等键前置判 → 抽 → 全序比 → part/rename/upsert/删旧）；`_fulltext_final_path`；`config.py` 两槽；
`HttpClient.post_multipart`（§7.1，**fable 已 approve**）；`StageContext` 一个可选字段；`000N` 迁移；
`pyproject.toml` 加 `pypdf` + `uv.lock`。**不碰**：`cli.py`、`repo.py`、`types.py`（`AssetKind` 不动，§5.4）。

### 9.2 T14（`verify` 全库扩展）——三类同构扩展 + 第四类信息级

| 类 | fulltext 面判据 |
|---|---|
| `missing_file` | `fulltext.text_path` 非空，但解析后文件不存在 |
| `orphan_file` | `data_dir/fulltext/**` 下的文件未被任何 `fulltext.text_path` 引用 → suggestion `prune` |
| `hash_mismatch` | 文件存在且 `text_sha256` 非空，但实测 sha256 不符 |
| **`stale_fulltext`**（新增，信息级） | `fulltext.source_sha256` ≠ 其 `asset_id` 所指 asset 行的当前 `sha256` → suggestion `re-extract` |

- **`stale_fulltext` 为什么必须单列**（审查 P1-5）：asset 被 re-fetch（同 asset 身份、新文件内容）后，
  fulltext 行仍指向一份**由旧 PDF 抽出**的文本——它自身完全自洽（文件在、哈希对、路径对），**上面三类
  判据全绿**，但全文与当前 PDF 已**静默错配**。没有这一类，一次「PDF 更新了、全文没跟上」的错配可以
  永久隐身。判据即 §5.3 的陈旧判据（rank −2），二者共用同一 SQL 谓词，语义天然一致。
  归**信息级**（不是缺陷）：它是可自愈的——下一次 extract 必然重抽取代（陈旧行 rank 最低），
  `verify` 只负责让它可见并提示 `re-extract`。`asset_id IS NULL` 的 legacy 行**不参与本类判定**（§5.3 归一）。
- **`state='noop' AND text_path IS NULL` 不是缺陷**，报为「未真实抽取」（信息级），不计入三类。
- **si 孤儿判定粒度 = 文件级**（T14 卡指名由本卡裁决）：`asset.file_path` 对 si 存的是**具体文件路径**
  （`si/{v}/{y}/{paper}/{原名}`，见 `_asset_final_path`），一个 asset 行 ⇄ 一个文件，与 pdf **完全同构**。
  故按文件逐个判孤儿，**不做目录级判定**——目录级会把「同 paper 下多 si 文件里少了一个」整体判成存在，
  正好掩盖它要检出的那类缺口。
- `text_path` 的相对形态由 `verify.py::_resolve` 既有逻辑消费（§5.4），T14 零改造。

### 9.3 T19（在线验收批）

AC-7.1 真实抽样（开放许可 PDF，产物不入库）；AC-7.2 真实 GROBID 为**条件项**（本机可用才跑，
零在线预算——本地服务）；降级链取证走 obslog reason token（§7.2）；§12 阈值的实测标定（P2-⑤）。

### 9.4 T12（FTS5 落地）——**零消费**

**T12 不消费本卡任何冻结件**（P2-⑦，闭合 [phase7 计划 §2](../plan/phase7-implementation-plan.md) 消费方表）：
D-034 已裁 FTS5 范围＝**title + abstract 二字段**，二者都在 `paper` 表，与 `fulltext` 行/落盘产物**零交集**；
正文索引已被显式 defer（计划 §8）。故 D-033 与 D-034 在实现面**无接缝**，T7/T12 可完全并行，
两卡的迁移只在**编号**上竞争（§5.1，先合者取小号），schema 内容不重叠。此处显式写明，
以免后续读者从「都碰全文」误推出依赖关系。

## 10. 测试方法

1. **抽取器单测**（L1/L2 生成语料）：文本 PDF → 非空文本 + 注入标题可检出；多页拼接序；空页；
   四类负例 → `char_count == 0` **且 `note` 非空且取值互不相同**（handler 侧转 `extract_failed`）。
2. **幂等/全序属性测试**（`hypothesis`，仓库既有依赖）：对同一批 `(asset, extractor, ver, char_count)`
   记录做**随机顺序**注入，断言终态 `fulltext` 行恒等 —— §5.3 顺序无关性的机器证明（复刻 D-031 的做法）。
3. **降级链参数化测试**：MockTransport 按 §7.2 矩阵逐行注入 → 断言 ①handler 出口恒 `done`/`skipped`、
   ②`extractor` 落值正确、③obslog 出现期望 reason token、④探活失败/逐篇连接失败/404 三行**记忆生效**
   （此后 `processFulltextDocument` **零调用**），而读超时/503/其它非 200 三行**不记忆**（下一篇仍调）。
3b. **GROBID 空产物专项**（§6.1 P0-2 的机器判据）：mock 返回 header-only TEI（合法 XML、`char_count==0`）
   + 库内已有 pypdf 五万字行 → 断言 ①触发纯文本兜底重抽、②`fulltext` 行**仍是 pypdf 那条**（rank 2 的空
   TEI **未**取胜）、③obslog 出 `grobid_empty_tei`。这是审查反例的回归锁。
3c. **支配预判专项**（§5.2）：库内已有 grobid 行、本轮 GROBID 关闭 → 断言返回 `"skipped"` 且
   **抽取器 `extract()` 零调用**（monkeypatch 计数），证明未开源文件。
4. **崩溃/断点测试**：在步 3/步 4 之间人为中断（monkeypatch upsert 抛异常）→ 重跑 → 断言无第二份产物文件、
   终态一致；`.part` 残留被启动清理。
5. **迁移测试**：v(N-1) 库（含 noop 行）→ 迁移 → 断言五列存在、noop 行 `state='noop'`、
   `ingest_state` 未回滚；迁移幂等重跑。
6. **红线守卫**：`tests/` 树下 `.pdf` 文件数恒为 0（静态断言，AC-0.3 的本卡侧守卫）；
   GROBID 请求断言三个 `consolidate*` 参数**均为 0**（§2.1 的机器判据，防将来漏参数）。
7. **L1 生成器自校验**（§8.2 强制项）：结构自检 + SENTINEL 正例锚定 + 负例 `note` 区分度——
   **不经被测抽取路径**，独立证明语料本身合法（防生成器 bug 伪装成抽取失败，R7）。
8. **rank 序回归锁**（§5.3 P1-1）：存量 noop 行 + 一次抽取失败 → 断言终态是 `extract_failed`
   （**不是** noop），且再跑一轮命中幂等键 `"skipped"`、抽取器零调用（证明长尾不被反复重抽）。

## 11. 测试类型

单元（抽取器、TEI 解析、路径构造、全序比较器）· 属性（顺序无关，hypothesis）· 契约
（`TextExtractor` Protocol 的 fake 实现可替换性）· 集成（`pull --extract` 端到端：fetch→extract→ingest
落库落盘对账）· 迁移（schema 升级幂等与回填）· 在线（T19，条件项）。全部离线用例**零网络**
（socket 猴补看守既有）。

## 12. 验收标准（AC-7.1/7.2 的可执行化）

> AC 正式编号与验收记录模板归 **T18**；本节只给判据的可执行化表述，供 T7 落测试、T19 落真实批。
> 本节**不修改** `acceptance-criteria.md`（该文件的回填是 T18 的职责面）。

**AC-7.1（全文抽取）**——两条路径判据分叉，**均不弱于原文**：

- GROBID 路径：TEI `titleStmt/title` 与 `paper.title` 的**归一化 Levenshtein 距离 / 标题长度 ≤ 0.15**；
- 纯文本路径（`ExtractedText.title` 为 None）：`paper.title` 的归一形出现在**正文前 2000 字符**内，
  判据同为归一化编辑距离 ≤ 0.15 的**最优子串匹配**（学术 PDF 首页含标题，2000 字符窗足够且不虚高）；
- 编辑距离用 `tests/helpers/textmatch.py` 内约 15 行 DP 实现（**零新依赖**），T7 与 T19 **共用同一判据**。

**阈值 0.15 与 2000 字符窗未经真实标定**（P2-⑤，如实声明）：二者是设计期的**工程猜测**，不是实测结论——
T7 的离线载体用生成式 PDF（标题是自己注进去的，必然 0 距离命中），**根本标定不了阈值**；第一次真实
数据接触在 T19。故写死处置口径：**T19 抽样若不达标，先判「阈值未标定」而非「抽取器不合格」**——
须逐篇人工过目失配样本，区分三种成因（① 抽取器真的抽错 → 修实现；② 标题归一化不足，如 LaTeX 宏/
连字符/副标题分隔符 → 修归一化；③ 阈值本身定得太紧 → **允许一次阈值修订**）。修订须把实测分布
（样本数、距离分位数、新阈值及其理由）写进 T19 的验收记录（`docs/testing/records/`），并同步回填本节与
T18 的 AC 正式表述。**只允许这一次**：此后再改阈值须走 ADR，防止「调阈值直到通过」的验收自证。

**AC-7.2（GROBID 可选）**——三态而非两态：① `grobid_url` 未配置 → `.txt` + `extractor='pypdf'`；
② 配置且 mock 服务在线 → `.tei.xml` + `extractor='grobid'`；③ 配置但服务不可用（§7.2 矩阵逐行）
→ `.txt` + `extractor='pypdf'` + **任务不 FAILED、无异常逃逸**。第 ③ 态即「关闭时降级不报错」的严格形式。

## 13. 风险与开放问题

| # | 风险 | 处置 |
|---|---|---|
| R1 | pypdf 依赖事实未离线核实（§3.1 ⚠） | T7 装依赖时实测复核；证伪则按 §3.3 回滚触发条件降为 extra，并回填 §14 |
| R2 | `HttpClient.post_multipart` 触碰冻结件 | 纯附加、有两处先例；**fable 已 approve（2026-07-27）**，须与 `post_json` 同构走 `_request`（§7.1） |
| R3 | 迁移编号与 T2（D-034 FTS 迁移）撞号 | 本文一律 `000N` 占位；T7 按目录当时最大号 +1 取号（先合者取小号） |
| R4 | 1-1 模型丢失「败者 asset 抽取信息」+ 平局时的重复抽取 | 两项均如实入档（§5.6）+ obslog 留痕；升级触发条件已写死 |
| R5 | 步 4 之后的旧后缀产物孤儿不自愈；且 T7(W1)→T14(W2) 之间窗 2/3 无检出工具 | 如实入档（§5.5）；T7 报告登记缺口，T14 合并后一次全库 `verify` 收口 |
| R6 | 加密 PDF 姿态（§2.3）属新红线解释 | **fable 已 approve（2026-07-27）**，并按审查建议加严为五条实现约束（只试一次空串／禁回退口令列表／禁权限位旁路／`note` 不泄露口令强度） |
| **R7** | **L1 生成器自身的 bug 会伪装成「抽取失败」，使负例测试假绿** | §8.2 的三层自校验为强制项（结构自检 + SENTINEL 正例锚定 + 负例区分度）；断言消息须显式指向「生成器坏了」而非抽取器 |
| **R8** | **AC-7.1 阈值 0.15 / 2000 字符窗未经真实标定**，离线载体（自注标题）结构上无法标定 | §12 已写死处置口径：T19 不达标先判「阈值未标定」，三成因逐一甄别，**允许一次**基于实测分布的阈值修订并入验收记录；此后再改须走 ADR |
| **[UNRESOLVED]** | GROBID 服务版本串格式未实测（`/api/version` 返回纯文本 vs JSON） | 不阻塞：`extractor_ver` 取回失败即 `"unknown"`，全序的 `ver_key` 对无数字串返回 `(0,0,0)`，语义安全；T7/T19 实测后回填 |

## 14. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 2 | 2026-07-27 | **r2 审查修订（六项主裁决方向不变，修内部相容性）**：①`ExtractedText` 加 `note`（抽取器报判别信息、handler 判失败，否则 §6.1 四元闭集不可生产）；②GROBID `char_count==0` 判失败**并触发纯文本兜底**（修「header-only 空 TEI 以 rank 2 压制 pypdf 正文」反例），语义统一为「GROBID 无有效产出→纯文本」；③rank 序修正 `extract_failed(0) > noop(−1)`（原稿写反⇒失败结论永远写不进库⇒长尾每轮重抽）；④§5.2 增支配预判（存量 `(rank,ver_key)` 严格更优⇒零抽取跳过），平局残余重抽成本入 §5.6；⑤§7.2 补「逐篇连接失败/重置」行（记忆本轮）+ 记忆语义统一表述；⑥`text_path` 写死**不含 `data/` 前缀**并列出 T7 须同步改的两处列注释（照抄即全库 `missing_file`）；⑦§9.2 增第四类 `stale_fulltext`（信息级）。同批吸收 7 条 P2：「不降偏序」措辞如实化 + 窗 2 同后缀覆写＝`hash_mismatch` 且 T7→T14 检出缺口入档 + legacy `asset_id IS NULL` 归一 + L1 生成器自校验（新 R7）+ AC-7.1 阈值标定口径（新 R8）+ `consolidateFunders` 一并置 0 + §9.4「T12 零消费」闭合消费方表 | 独立审查（opus）NEEDS_FIX 逐条裁决；controller 转达 2026-07-27 |
| 1 | 2026-07-27 | 初稿（P7-T1）：六项裁决成文 + T14/T19 消费面冻结 + AC-7.1/7.2 可执行化 | [phase7-implementation-plan §4 T1](../plan/phase7-implementation-plan.md)；[D-033](../plan/decision-log.md) |
