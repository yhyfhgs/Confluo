.PHONY: test lint type check fmt

# 全量测试树 + 覆盖率门禁（test-plan §6：--cov-fail-under=80）。
# T1 阶段 tests/contract、tests/integration 仅有占位 __init__.py，pytest 收集 0 条不报错。
test:
	uv run pytest tests/unit tests/contract tests/integration \
		--cov=paper_crawler --cov-report=term-missing --cov-fail-under=80

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy src

# 本地门禁（D-017）：lint + type + test 三者全绿方可提交。
check: lint type test

# 便捷：自动格式化 + 修复可修的 lint。
fmt:
	uv run ruff format .
	uv run ruff check --fix .

# T5 在线冒烟（真实网络，限量+预算护栏；需 PAPER_CRAWLER_CONTACT_EMAIL）。
smoke:
	uv run pytest tests/online -m online -v
