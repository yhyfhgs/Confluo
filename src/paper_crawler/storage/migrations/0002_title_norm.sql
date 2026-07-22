-- schema v2 (Phase 3 T1；plan §2-1)：paper 增列 title_norm（弱信号候审匹配键）+ 索引。
-- 纯附加、方言中性（ALTER TABLE ADD COLUMN + CREATE INDEX 均 SQLite/PostgreSQL 通用）。
-- 存量行的 title_norm 回填**无法用 SQL 表达**（LaTeX 宏剥离/Unicode 折叠需 Python
-- ids.normalize_title）——由迁移器的 Python 步（db.py `_PY_MIGRATIONS`，按文件名绑定本
-- 迁移）在同一事务内、本 DDL 之后执行。v1 库自动升级、幂等。

ALTER TABLE paper ADD COLUMN title_norm TEXT;

CREATE INDEX idx_paper_title_norm ON paper(title_norm);
