"""测试支持模块（非测试用例本身，不含 ``test_*.py``）：``dbdump.py``（T8a）、
``golden.py``（T6）。

包名说明：`tests/` 目录本身没有 `__init__.py`（T1 起的既有布局——`tests/unit`、
`tests/contract`、`tests/integration` 各自独立成包），pytest 的 rootdir 插入机制
因此把 `tests/`（而非项目根目录）加进 `sys.path`。据此，本包内模块须以顶层模块名
导入：``from helpers.dbdump import canonical_dump``，写成 ``from tests.helpers.dbdump
import ...`` 会因为 `tests` 本身不是包而 `ImportError`（已用本目录下的测试文件实测
验证）。
"""
