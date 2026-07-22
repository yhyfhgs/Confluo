"""Playwright 边界薄封装（auth-framework §1/§10；T1b）。

- **惰性 import**：模块顶层零 playwright——`_import_playwright()` 在真实首登时才
  import；未装 `[auth-browser]` → `AuthRequired(detail=安装指引)`（§10）。核心路径
  （APIKey 全链 / httpx 直取 / 健康门 / mock IdP 测试）完全不触本模块的真实分支。
- **一次性 profile 目录（A-M7，AC-4.5 ⑥）**：首登用 `tempfile.mkdtemp(prefix="pc-auth-")`
  临时 user-data-dir 启动 persistent context；storage_state 导出后 **try/finally 整目录
  `shutil.rmtree`**（异常路径亦清理）。绝不用固定 user-data-dir——浏览器 profile 内含
  明文 cookie/缓存，残留等价 session 泄漏。
- **人在回路（D-006）**：headed 浏览器由用户人工完成登录（含 MFA）；本模块只开页、
  等待用户确认、导出 storage_state——不自动填密码、不自动过 MFA、不对抗风控。

测试缝：`run_headed_login(launch=...)` 注入假 launcher（`BrowserContextHandle` 鸭型），
单测清理逻辑零真实浏览器（§9/§10：真实浏览器测试 `PC_BROWSER_TESTS` 手动门，不进 CI）。
"""

import importlib
import json
import shutil
import tempfile
from collections.abc import Callable
from typing import Any, Protocol

from paper_crawler.errors import AuthRequired

_BROWSER_INSTALL_HINT = (
    "需浏览器首登：pip install paper-crawler[auth-browser] && playwright install chromium"
)


class BrowserContextHandle(Protocol):
    """launch seam 返回的最小把手：导出 storage_state + 关闭（鸭型，假 seam 可测）。"""

    def export_storage_state(self) -> bytes: ...

    def close(self) -> None: ...


LaunchFn = Callable[[str, str], BrowserContextHandle]  # (user_data_dir, login_url) -> handle
WaitFn = Callable[[], None]


def _import_playwright() -> Any:
    """惰性 import `playwright.sync_api`；未装 → `AuthRequired`（§10 逐字安装指引）。"""
    try:
        return importlib.import_module("playwright.sync_api")
    except ImportError as exc:
        raise AuthRequired(
            "browser-based first login unavailable", detail=_BROWSER_INSTALL_HINT
        ) from exc


class _PlaywrightContext:  # pragma: no cover - 真实浏览器路径（PC_BROWSER_TESTS 手动门，§10）
    """真实 Playwright persistent context 把手（headed；storage_state 导出）。"""

    def __init__(self, sync_api: Any, user_data_dir: str, login_url: str) -> None:
        self._playwright = sync_api.sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir, headless=False
            )
            page = self._context.new_page()
            page.goto(login_url)
        except Exception:
            self._playwright.stop()
            raise

    def export_storage_state(self) -> bytes:
        state: object = self._context.storage_state()
        return json.dumps(state, ensure_ascii=False).encode("utf-8")

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._playwright.stop()


def _launch_playwright(user_data_dir: str, login_url: str) -> BrowserContextHandle:
    """默认 launcher：先惰性 import（未装即抛，不触浏览器），再起真实 context。"""
    sync_api = _import_playwright()
    return _PlaywrightContext(sync_api, user_data_dir, login_url)  # pragma: no cover


def run_headed_login(
    *,
    login_url: str,
    wait_for_user: WaitFn,
    launch: LaunchFn | None = None,
) -> bytes:
    """首登全流程：一次性 profile 目录 → headed 打开登录页 → 等用户完成登录（含 MFA）
    → 导出 storage_state 字节 → **整目录删除**（A-M7 try/finally，异常路径亦清理）。

    返回值为 storage_state JSON 字节（调用方负责加密落盘——本模块不触 CredentialStore）。
    """
    launch_fn = launch if launch is not None else _launch_playwright
    profile_dir = tempfile.mkdtemp(prefix="pc-auth-")
    try:
        handle = launch_fn(profile_dir, login_url)
        try:
            wait_for_user()
            return bytes(handle.export_storage_state())
        finally:
            handle.close()
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


__all__ = ["BrowserContextHandle", "LaunchFn", "run_headed_login"]
