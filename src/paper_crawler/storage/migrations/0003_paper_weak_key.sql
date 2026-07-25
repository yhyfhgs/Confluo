-- schema v3 (Phase 6 F1；审计 P1「AC-3.4 注入顺序无关静默破坏」)：观测级弱信号键倒排表。
--
-- 为什么需要一张表：弱信号候审的匹配键原先取自 paper 行的当前 (title_norm, _first_author)
-- ——而这两者都参与字段级来源优先级收敛，会被后到的高优先源改写，于是"改写前到达"与
-- "改写后到达"的同一批观测产生不同候审边（审计实测 ABC→1 边 / ACB→0 边）。修复把匹配键
-- 改为**该 paper 全部观测的 (title_norm, first_author) 键集合**：单调只增、不被收敛改写，
-- 故终态候审边 = {键集合有交的每一对 paper}，是输入集合（而非到达序）的函数（AC-3.4）。
-- 键集合天然是「一 paper 多行」，无法塞回 paper 单列；本表即其倒排索引，
-- (title_norm, first_author) 索引使"谁曾观测过这个键"保持 O(log n) 查找。
--
-- 纯附加、方言中性（CREATE TABLE / CREATE INDEX 均 SQLite/PostgreSQL 通用；无 SQLite 专有
-- 特性，D-001 迁移路径不受影响）。paper 的 title_norm 列与其索引保留原样（归一标题索引，
-- 仍由 upsert_paper/收敛维护），只是不再充当弱信号匹配键。
--
-- 存量行回填**无法用纯 SQL 表达**（`_first_author` 藏在 meta_json，JSON 抽取函数是方言专有）
-- ——由迁移器 Python 步（db.py `_PY_MIGRATIONS`，按文件名绑定本迁移）在同一事务内、本 DDL
-- 之后执行：把既有 paper 的 (title_norm, meta_json._first_author) 作为其历史键写入，等价于
-- 旧实现的匹配面，故 v2 库升级后弱信号覆盖零倒退。

CREATE TABLE paper_weak_key (
  paper_id TEXT NOT NULL REFERENCES paper,
  title_norm TEXT NOT NULL,
  first_author TEXT NOT NULL,
  PRIMARY KEY (paper_id, title_norm, first_author)
);

CREATE INDEX idx_paper_weak_key_lookup ON paper_weak_key(title_norm, first_author);
