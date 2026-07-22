"""`auth/browser.py` 单测（auth-framework §10；安全断言 #6/#9；T1b）。

假 Playwright seam（`launch=` 注入）覆盖首登清理逻辑——**零真实浏览器**：

- 一次性 profile 目录：`mkdtemp(prefix="pc-auth-")` → 成功/异常路径 **整目录 rmtree**
  （A-M7，AC-4.5 ⑥）。
- 惰性依赖：模块顶层零 playwright import；未装 `[auth-browser]` → `AuthRequired`
  （detail=§10 安装指引），且同样不残留临时目录。
"""

import sys
from pathlib import Path

import pytest

import paper_crawler.auth.browser as browser_mod
from paper_crawler.auth.browser import run_headed_login
from paper_crawler.errors import AuthRequired


class FakeContext:
    """假 BrowserContextHandle：记录调用序 + 可注入导出异常。"""

    def __init__(self, state: bytes = b'{"cookies": []}', export_error: Exception | None = None):
        self.state = state
        self.export_error = export_error
        self.closed = False

    def export_storage_state(self) -> bytes:
        if self.export_error is not None:
            raise self.export_error
        return self.state

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def tracked_mkdtemp(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """截获 mkdtemp：记录真实创建的临时目录（清理断言用）。"""
    created: list[Path] = []
    import tempfile

    real = tempfile.mkdtemp

    def spy(prefix: str = "tmp") -> str:
        path = real(prefix=prefix)
        created.append(Path(path))
        return path

    monkeypatch.setattr(browser_mod.tempfile, "mkdtemp", spy)
    return created


def test_run_headed_login_returns_state_and_removes_profile_dir(
    tracked_mkdtemp: list[Path],
) -> None:
    seen: dict[str, object] = {}
    context = FakeContext(state=b'{"cookies": [{"name": "sid"}]}')

    def launch(user_data_dir: str, login_url: str) -> FakeContext:
        seen["dir"] = Path(user_data_dir)
        seen["url"] = login_url
        assert Path(user_data_dir).is_dir()  # launch 时目录已建
        return context

    waited: list[bool] = []
    state = run_headed_login(
        login_url="https://academic.oup.com/qje",
        wait_for_user=lambda: waited.append(True),
        launch=launch,
    )
    assert state == b'{"cookies": [{"name": "sid"}]}'
    assert waited == [True]  # 人在回路：等待用户确认后才导出
    assert context.closed is True
    assert seen["url"] == "https://academic.oup.com/qje"
    assert tracked_mkdtemp == [seen["dir"]]
    assert tracked_mkdtemp[0].name.startswith("pc-auth-")  # 规格化一次性目录前缀
    assert not tracked_mkdtemp[0].exists()  # A-M7：storage_state 导出后整目录已删


def test_run_headed_login_cleans_dir_when_wait_raises(tracked_mkdtemp: list[Path]) -> None:
    context = FakeContext()

    def abort() -> None:
        raise KeyboardInterrupt  # 用户中断登录

    with pytest.raises(KeyboardInterrupt):
        run_headed_login(
            login_url="https://mock.test/login",
            wait_for_user=abort,
            launch=lambda d, u: context,
        )
    assert context.closed is True  # 异常路径亦关闭浏览器上下文
    assert not tracked_mkdtemp[0].exists()  # try/finally：异常路径亦整目录清理


def test_run_headed_login_cleans_dir_when_export_raises(tracked_mkdtemp: list[Path]) -> None:
    context = FakeContext(export_error=RuntimeError("export boom"))
    with pytest.raises(RuntimeError, match="export boom"):
        run_headed_login(
            login_url="https://mock.test/login",
            wait_for_user=lambda: None,
            launch=lambda d, u: context,
        )
    assert context.closed is True
    assert not tracked_mkdtemp[0].exists()


def test_run_headed_login_cleans_dir_when_launch_raises(tracked_mkdtemp: list[Path]) -> None:
    def launch(user_data_dir: str, login_url: str) -> FakeContext:
        raise RuntimeError("launch boom")

    with pytest.raises(RuntimeError, match="launch boom"):
        run_headed_login(
            login_url="https://mock.test/login", wait_for_user=lambda: None, launch=launch
        )
    assert not tracked_mkdtemp[0].exists()


def test_default_launch_without_playwright_raises_auth_required(
    tracked_mkdtemp: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """未装 [auth-browser]：AuthRequired + §10 安装指引；临时目录同样零残留。"""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(AuthRequired) as excinfo:
        run_headed_login(login_url="https://mock.test/login", wait_for_user=lambda: None)
    assert "pip install paper-crawler[auth-browser]" in excinfo.value.detail
    assert "playwright install chromium" in excinfo.value.detail
    assert not tracked_mkdtemp[0].exists()


def test_module_import_does_not_load_playwright() -> None:
    """惰性红线（§10）：import auth 包/浏览器模块不加载 playwright。"""
    assert "paper_crawler.auth.browser" in sys.modules  # 本测试文件顶部已 import
    assert "playwright" not in sys.modules
