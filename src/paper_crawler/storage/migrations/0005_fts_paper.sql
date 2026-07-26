-- schema v5（Phase 7 T12；权威决策 D-034，见 docs/plan/decision-log.md）：paper_fts ——
-- FTS5 全文检索虚表（title+abstract 二字段）+ 三触发器（写路径同步）+ 存量回填。
--
-- **方言隔离不变式（D-034 决策 4/7）**：0001-0003（及本项目其余全部迁移文件）保持方言
-- 中性（D-001/D-017）；本文件是**唯一**允许含 SQLite 专有特性（FTS5 虚表 + 触发器）的
-- 迁移文件。PG 迁移时整文件替换为等价 `tsvector` 生成列 + GIN 索引（D-034 决策 6）；
-- 查询语法（`MATCH` vs `websearch_to_tsquery`）、排序函数（`bm25()` vs `ts_rank_cd()`）、
-- 词干化实现（porter 分词器 vs PG `english` 词典）三项不可移植，如实记于该决策，不假装
-- 等价。检索一律经 `repo.search_papers()` 单点封装，方言 SQL 不得散入 CLI 层。
--
-- **表形态 = content-owning**（自持内容，否决 external-content 与 contentless 两案）：
-- `paper.id` 是 ULID 文本主键、无 INTEGER PRIMARY KEY，其 rowid 隐式且 `VACUUM` 可
-- 重编号——若靠隐式 rowid 做行身份的唯一连接键，重编号后检索会静默指向错误的 paper。
-- content-owning 把 `paper_id` 物化进索引行（UNINDEXED，不参与全文匹配、只做回读），
-- 检索结果正确性不再依赖 rowid 稳定性；rowid 只用作写路径的 O(log n) 定位键，最坏后果
-- 是写入当场响亮失败（见下）或可用 `crawler reindex --check` 检出的差集，不是静默错误
-- （详见 D-034 决策 2 的完整论证）。代价：多存一份 title+abstract 副本（估算 ≈13 MB/
-- 万篇，[未实测]，T12 落地后应在验收记录回填实测值）。
--
-- **索引范围**：仅 `title` + `abstract` 二字段。全文正文索引与向量索引 **defer**
-- （phase7-implementation-plan.md §8：正文索引待抽取产物规模实测后于 P8 评估经济性；
-- 向量索引无消费场景 + 引重依赖，YAGNI）——`fulltext.text_path` 指向的正文不入库、
-- 不入索引，`fulltext` 表语义不变。
--
-- **同步机制 = SQL 触发器（写路径全覆盖）+ `crawler reindex` 兜底**，否决应用层同步
-- （写 `paper` 的路径不止一处且仍在增长，漏一处即索引静默漂移；触发器由 DB 保证覆盖，
-- 是结构性而非纪律性保障）。两条不变式（D-034 决策 3，SQL 写死，不得改动）：
--   A. `paper_id` 每次写入必须同写 `new.id`；UPDATE 取 DELETE+INSERT 形态——绝不可写成
--      `UPDATE paper_fts SET title=…,abstract=… WHERE rowid=old.rowid`，否则会在 rowid
--      重编号后把 A 的正文覆盖到 B 的索引行、而该行仍带着 B 的 paper_id，复活本 ADR
--      声称已消除的静默错映射。
--   B. 两处 `DELETE` 必须带 `AND paper_id = old.id` 双条件——只按 rowid 删，在重编号后
--      会误删无辜他行（假阴性：那篇 paper 从此静默漏检）；加上 paper_id 判别后，
--      重编号情形下 DELETE 落空，紧随其后的 `INSERT … VALUES(new.rowid, …)` 会撞上
--      已被他行占用的 rowid 而抛 `sqlite3.IntegrityError`（裸消息 `constraint failed`，
--      虚表 xUpdate 不带扩展错误码——经验区别于 FK/UNIQUE/NOT NULL/CHECK 违例的带前缀
--      消息）。这是**写入响亮失败 + 该事务整步回滚**，不是"多留一行陈旧文本"的静默
--      冗余（D-034 决策 3 前一稿的错误断言已改口）；须跑 `crawler reindex` 恢复写路径
--      ——`storage/db.py::Database.tx()` 把该特定 `IntegrityError` 翻译为可操作
--      `CrawlerError(CONFIG)`，提示跑 `crawler reindex`，不让裸异常冒到用户面前。
--   `rowid = old.rowid` 条件先行，故仍是 O(log n) 定位 + 一次列比较，不退化为全表扫描
--   （若单靠 UNINDEXED 列 `paper_id` 定位则是全表扫描，rowid 绑定是必需而非优化）。
--   `UPDATE OF title, abstract` 限定列：避免 `ingest_state`/`updated_at` 等高频列更新
--   空转重建索引行。
--
-- 分词器 `porter unicode61 remove_diacritics 2`：语料以英文学术文本为主，porter 词干化
-- 提升召回；`remove_diacritics 2` 与 `ids.normalize_title` 的 Unicode 折叠取向一致。
-- 分词器可改——改动等价于一次 `crawler reindex`，属可逆选择。

CREATE VIRTUAL TABLE paper_fts USING fts5(
  paper_id UNINDEXED, title, abstract,
  tokenize = 'porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER paper_fts_ai AFTER INSERT ON paper BEGIN
  INSERT INTO paper_fts(rowid, paper_id, title, abstract)
  VALUES (new.rowid, new.id, new.title, COALESCE(new.abstract, ''));
END;
CREATE TRIGGER paper_fts_au AFTER UPDATE OF title, abstract ON paper BEGIN
  DELETE FROM paper_fts WHERE rowid = old.rowid AND paper_id = old.id;
  INSERT INTO paper_fts(rowid, paper_id, title, abstract)
  VALUES (new.rowid, new.id, new.title, COALESCE(new.abstract, ''));
END;
CREATE TRIGGER paper_fts_ad AFTER DELETE ON paper BEGIN
  DELETE FROM paper_fts WHERE rowid = old.rowid AND paper_id = old.id;
END;

-- 存量回填：迁移执行时 `paper` 表内既有行一次性灌入索引（新迁移文件只跑一次，见
-- storage/db.py `migrate()`——非需要幂等保护的重复执行场景）。
INSERT INTO paper_fts(rowid, paper_id, title, abstract) SELECT rowid, id, title, COALESCE(abstract,'') FROM paper;
