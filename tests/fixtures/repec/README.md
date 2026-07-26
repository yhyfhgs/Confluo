# `tests/fixtures/repec/` —— ReDIF 快照 fixture（**自造样本，非上游取回件**）

## 出处如实标注（重要）

本目录的 `.rdf` 文件是**按 ReDIF 规范手工构造的合成样本**，**不是**从 `www2.nber.org`
取回的真实 bulk 文件。原因：T8 的真实快照拉取（`T8-bulk`，≤4 请求）经 controller 裁决
**不在本卡**——归 T19 在线批统一记账（[plan §3](../../../docs/plan/phase7-implementation-plan.md)）。

**唯一有 [LIVE] 依据的部分**是字段名与 JEL 值形态，来自
[enrich-eval-p6.md §6.2 探针](../../../docs/research/enrich-eval-p6.md)（[LIVE 2026-07-26]，6/6 请求）：

- 字段名 `Classification-JEL` 确证在 bulk ReDIF 面；
- `nbr:nberwo:35506` 的值逐字节为 `D1; J13; J15`（与 HTML 勘察吻合）——本目录
  `01_nberwo_multi.rdf` 的对应记录**逐字沿用该实测串**；
- 字段名 `Publication-Status`（wp↔published 版本关联）同在 bulk 面。

**其余形态（文件命名、记录切分方式、字段出现顺序、续行折行位置、`t` 系列落哪个 series 段）
均属 [未实测] 判读**，见 `src/paper_crawler/adapters/repec/parse.py` 模块 docstring 的逐条
标注。T19 取回真实快照后若形态不符，**按实测收窄解析器与本目录 fixture**，不反过来把推断
当事实。

## 文件清单

| 文件 | 覆盖的 fixture 项（[aggregators.md §5.7](../../../docs/design/adapters/aggregators.md) 清单） |
|---|---|
| `01_nberwo_multi.rdf` | ①正常记录（含 JEL + `Publication-Status`）②缺 JEL 的历史记录 ④多记录切分；另含无 handle 的 `ReDIF-Series` 块（须被跳过）与摘要内空行/续行 |
| `02_malformed.rdf` | ③畸形/截断记录（无 `Handle`、无 `Title`、`Template-Type` 前的前言、字段名大小写混杂） |

⑤快照缺失与⑥快照过期不需要 fixture 文件——由测试在 `tmp_path` 内构造（缺失＝不建目录；
过期＝写一个 `fetched_at` 早于阈值的 `manifest.json`）。
