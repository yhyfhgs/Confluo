# 在线测试树（T3 落地，Phase 2）：真实网络的 T5 冒烟测试落地目录。
# 每个测试文件顶部须声明 `MAX_REAL_REQUESTS = N` 并用 `@pytest.mark.online`
# 标记用例（默认 addopts `-m "not online"` 排除，见 pyproject.toml/test-plan §9）。
# 本包目前只有 conftest.py（预算护栏）+ 一个占位用例；真正会发真实请求的
# 冒烟测试从 T7（arxiv）起陆续加入。
