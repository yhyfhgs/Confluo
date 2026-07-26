-- schema v4 (Phase 7 T7；D-033 决策 3 / design/12-fulltext-extract §5.1)：fulltext 表增列 5 项
-- ——asset 级幂等键的两个维度（asset_id / source_sha256）+ 产物哈希（text_sha256）+ 状态与
-- 失败 token（state / note）——并把存量 Phase 1 noop 行回填为 state='noop'。
--
-- 纯附加、方言中性：5 条 ALTER TABLE ADD COLUMN + 1 条 UPDATE 均 SQLite/PostgreSQL 通用
-- （design/06 §6 迁移纪律；无 SQLite 专有特性，D-001 的 PG 迁移路径不受影响）。无 Python 后置步。
--
-- **PK 保持 paper_id 不变**（design/06 §1「Paper 1─1 Fulltext」）：asset 级的是**幂等键**
-- （asset_id, source_sha256, extractor, extractor_ver），不是表的基数。改 1-N 才叫改 ER 模型，
-- 本 Phase 不做（升级触发条件＝出现 per-asset 产物矩阵的真实消费方，design/12 §5.6 → P8）。
--
-- 取代规则＝**全序取 max** `(rank, ver_key, char_count, asset_id)`，rank：grobid 2 > pypdf 1 >
-- extract_failed 0 > noop −1 > 陈旧/产物失效 −2（design/12 §5.3）。存量 noop 行因此**不删不改
-- 语义**：它是 rank 最低的合法值，任何真实抽取结论——含「抽不出」——都取代它；而 extract_failed
-- 必须高于 noop，否则存量 noop 会永久压制失败行 ⇒ 失败结论写不进库 ⇒ 幂等键永不命中 ⇒ 每轮
-- pull 对同一批长尾扫描件重抽一次。
--
-- 存量 `paper.ingest_state='extracted'`（P1 noop 造成）**不回滚**（「只前进不回退」不破坏）；
-- verify（T14）须把 `state='noop' AND text_path IS NULL` 如实报为「未真实抽取」（信息级），
-- 而非 orphan/missing。
--
-- text_path 形态（design/12 §5.4 / D-033 附带裁决）：**相对 data_dir、且不含 `data/` 前缀**——
-- `verify.py::_resolve` 把相对路径挂在 `Config.data_dir` 下、而 `data_dir` 本身即指向 `…/data`，
-- 带前缀会解析成 `…/data/data/fulltext/…` 使全库每一行都报 missing_file。`0001_init.sql:113`
-- 的旧列注释含该前缀（文档缺陷），但 0001 是既成事实**一个字节都不改**；正确形态以本迁移的列
-- 注释与 `docs/design/06-data-model.md` §2 为准。

ALTER TABLE fulltext ADD COLUMN asset_id TEXT REFERENCES asset;      -- 产物出自哪个 asset（legacy 行 NULL）
ALTER TABLE fulltext ADD COLUMN source_sha256 TEXT;                  -- 抽取时源 PDF 的 sha256（陈旧判据）
ALTER TABLE fulltext ADD COLUMN text_sha256 TEXT;                    -- 落盘产物 sha256（T14 hash_mismatch 依据）
ALTER TABLE fulltext ADD COLUMN state TEXT;                          -- extracted | extract_failed | noop
ALTER TABLE fulltext ADD COLUMN note TEXT;                           -- 失败 token：encrypted|image_only|corrupt|empty_text

UPDATE fulltext SET state = 'noop' WHERE extractor = 'noop' AND state IS NULL;
