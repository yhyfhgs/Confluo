-- schema v6（修复批 R3c；审计 C2 合成库定量基准实测）：三条高优先级索引，补齐存储层
-- 最热三类查询路径此前的全表扫。
-- 纯附加、方言中性（三条 CREATE INDEX 均 SQLite/PostgreSQL 通用；无 SQLite 专有特性，
-- D-001 迁移路径不受影响）；无 Python 后置步、无存量回填（索引不改变既有数据）。
--
-- 1. idx_identifier_paper：`identifier` 表 PK=(scheme,value)，按 paper_id 反查
--    （repo.py 的 `_paper_brief`/`_identifier_count`/`_paper_min_identifier`/
--    `_ensure_identifiers` 等）此前无可用索引——`ORDER BY scheme,value` 形态的查询退化为
--    扫全部 PK 索引项（EXPLAIN：`SCAN identifier USING INDEX sqlite_autoindex_identifier_1`），
--    纯 COUNT 形态退化为全表扫（`SCAN identifier`）。C2 合成库实测 `dedupe review --limit 0`
--    5272ms、且随库龄单调线性退化；加索引后 EXPLAIN 转
--    `SEARCH identifier USING INDEX idx_identifier_paper (paper_id=?)`，266x，代价 476KiB。
--
-- 2. idx_task_fresh：覆盖 `tasks.py::TaskQueue._fresh_skip`（入队新鲜度判定，全部 enqueue
--    调用路径必经）与 `_find_active`（duplicate 判定）两条高频查询的等值谓词列——列序取自
--    两条查询 WHERE 子句的实际书写顺序：
--      kind = ? AND (venue_id = ? OR venue_id IS NULL) AND params_json = ?
--      AND state {= 'DONE' | IN ('PENDING','RUNNING')}
--    即 (kind, venue_id, params_json, state)。C2 实测 `_fresh_skip` 在 50 万行合成库上
--    17.31ms/次（千任务一轮入队 17.3s，随库龄线性恶化）——此前只命中既有
--    `idx_task_state_kind(state,kind)` 的前两列（EXPLAIN：
--    `SEARCH task USING INDEX idx_task_state_kind (state=? AND kind=?)`），venue_id/
--    params_json 仍需逐行过滤，另加 `USE TEMP B-TREE FOR ORDER BY`。加本索引后四列等值
--    谓词全部命中（EXPLAIN：`SEARCH task USING INDEX idx_task_fresh (kind=? AND venue_id=?
--    AND params_json=? AND state=?)`），缩窄到的候选行数通常 0-1 行，其后
--    `ORDER BY updated_at DESC, id DESC` 的临时排序随之廉价（该步骤仍会出现在 EXPLAIN
--    输出里，是预期形态、非缺陷）。
--
--    **不覆盖 `claim_next`**（`SELECT id FROM task WHERE state='PENDING' ORDER BY
--    created_at, id LIMIT 1`——只以 state 单列过滤，且 state 在本索引处于末位、不构成可用
--    前缀，故 `claim_next` 的 `USE TEMP B-TREE FOR ORDER BY` 不受本索引影响）。
--    审计 C2 基准另测过候选
--    `idx_task_pending ON task(state, created_at, id)`，实测可消除该 TEMP B-TREE；但该
--    候选未列入本卡范围（任务标题即"三索引"）——如实记录，留给后续卡按 claim_next 实测
--    调用量评估是否值得追加第四条索引。
--
-- 3. idx_paper_venue：`paper.venue_id` 此前无索引，`repo.counts()`/`list_papers()` 等按
--    venue 过滤/计数全表扫（`SCAN paper`）；C2 实测 7.9ms → 0.2ms（40x），加索引后纯计数
--    查询命中 `SEARCH paper USING COVERING INDEX idx_paper_venue (venue_id=?)`（索引自身
--    即可答复 COUNT(*)，无需回表取行）。
--
-- 索引存在性 + EXPLAIN QUERY PLAN 断言见 tests/unit/test_migrations.py。

CREATE INDEX idx_identifier_paper ON identifier(paper_id);

CREATE INDEX idx_task_fresh ON task(kind, venue_id, params_json, state);

CREATE INDEX idx_paper_venue ON paper(venue_id);
