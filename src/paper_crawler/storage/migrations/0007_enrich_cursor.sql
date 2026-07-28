-- schema v7（修复批 R4b；审计 P1-16：enrich 无断点 → 字典序靠后的 DOI 永久饿死）：
-- 每个 enrich source 一行"上次处理到哪"的断点。
--
-- 缺陷本体：`cli._doi_universe` 按 `identifier.value` **字典序**取全库 DOI，
-- `cli._run_enrich_source` 遇错（额度耗尽/预算熔断/瞬时故障）永久 `break` 且不留任何
-- 位置信息。日额度不足以扫完全库时，每天都从同一批 DOI 从头开始——排在字典序后半段的
-- 论文**永远轮不到富化**，且这件事在摘要行上完全看不出来（每天都"处理了 N 篇"）。
--
-- 修法：每源一个断点键，下一轮 keyset 分页从断点之后继续（`WHERE paper_id > last_key`），
-- 扫到底则清断点回绕。遍历序同步从"DOI 字典序"改为 `paper.id`（ULID）升序 ≈ 插入序——
-- 新论文天然落在尾部，而回绕保证老论文不会因此永久排队（两条性质缺一不可）。
--
-- 表设计：
-- - `source` 主键 = enrich source id（openalex|s2|repec，`cli._ENRICH_SOURCES`）。**不带
--   venue 维**：`enrich --venue X` 与全库跑共用同一断点，二者交替时最坏情况是某一轮的
--   起点偏后，下一次取空即清断点回绕——不会永久跳过任何论文（这正是"回绕"要保的性质），
--   故不值得为它加一维复合主键。
-- - `last_key` = 上一轮**最后一个成功处理完的分页**的末条 `paper.id`（非"下一个要处理
--   的"）：语义是"这个键及之前都已处理"，配 `>` 严格大于取下一页。存在即有效，无断点
--   直接删行（不写空串——"没有断点"与"断点是空串"必须是同一种表示）。
-- - `updated_at` 只供人读排障（"这个源上次动是什么时候"），无程序语义。
--
-- 纯附加、方言中性（`CREATE TABLE` 三列，无 SQLite 专有特性；D-001 PG 迁移路径不受
-- 影响）；无 Python 后置步、无存量回填——首次运行时无断点即"从头开始"，与旧行为一致。

CREATE TABLE enrich_cursor (
  source TEXT PRIMARY KEY,
  last_key TEXT NOT NULL,
  updated_at TEXT
);
