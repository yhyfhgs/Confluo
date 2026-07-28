#!/usr/bin/env python3
"""OpenReview accessToken 自动刷新（openreview.md §3 token 通道的运维工具）。

读取 `$PAPER_CRAWLER_HOME/config.toml`（未设 env 时 `~/.paper-crawler/config.toml`）的
`[auth.openreview]` 节里的 `username` / `password`，调用官方登录端点换取新
accessToken，**行级**写回同文件的 `token` 字段（保留文件其余内容与注释原样）。

凭证纪律（红线，AGENTS §6.4）：
- 凭证与 token **绝不打印**到 stdout/stderr/日志——任何输出与报错都不回显值；
- 请求经 `urllib`（进程内存直发）——凭证不进命令行参数（`ps` 不可见）、
  不进环境变量、不进 shell history（对比 `curl -d '{"password":...}'` 的泄漏面）；
- 写回采用临时文件 + `os.replace` 原子替换，完成后强制 `chmod 600`；
- 配置文件在 config-home（D-032 起默认位于仓库根 `.paper-crawler/`，.gitignore
  整目录强制忽略），永不入 git；本脚本自身不含任何凭证，可入 git。
- 登录端点是 OpenReview OpenAPI 定义的官方鉴权路径（非绕过）；默认每小时
  刷新一次（launchd），登录频率远低于站点限流（60 req/60s），礼貌无扰。

配置格式（用户自行写入 config.toml；建议先 `chmod 600` 该文件）：

    [auth.openreview]
    username = "你的注册邮箱"
    password = "你的密码"
    token = ""              # 本脚本自动维护，留空即可

用法：
    python3 scripts/refresh_openreview_token.py            # 刷新一次
    python3 scripts/refresh_openreview_token.py --verify   # 刷新并验证 API 可用
    python3 scripts/refresh_openreview_token.py --home /path/to/home

定时安装（macOS launchd，每小时 + 开机即跑）：见文件末尾 LAUNCHD_PLIST 注释，
或直接运行 `python3 scripts/refresh_openreview_token.py --install-launchd`。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

# launchd bootstrap（R2c 独立审查 Critical #1）：`_install_launchd` 生成的 plist 用**本机
# conda 解释器**（非本仓库 `.venv`）跑本脚本——该解释器大概率未 `pip install -e .` 过
# paper-crawler，裸 `import paper_crawler` 会在每小时续期作业里 `ModuleNotFoundError`，
# 且 launchd 的失败不会主动弹给用户（只进 `--install-launchd` 写的 stderr 日志文件），
# 等于**静默失效**——直到 token 过期用户才会发现。修法：把 `<repo>/src` 插到 `sys.path`
# 头部，任何解释器都能找到源码，不依赖该解释器已安装本包（`paper_crawler` 本身及
# `config.py` 唯一依赖的 `errors`/`sensitive` 两个子模块均只用标准库，无第三方依赖需要
# 该解释器另外装——已核实 `src/paper_crawler/__init__.py` 不触发任何第三方 import）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from paper_crawler.config import resolve_home  # noqa: E402 (须在上面 sys.path bootstrap 之后)

LOGIN_URL = "https://api2.openreview.net/login"
VERIFY_URL = "https://api2.openreview.net/notes?content.venueid=ICLR.cc%2F2024%2FConference&limit=1"
UA = "PaperCrawler/0.1 (token refresh; personal research)"
PLIST_LABEL = "com.papercrawler.openreview-token"


def _home_dir(cli_home: str | None) -> Path:
    """config-home 解析：复用 `paper_crawler.config.resolve_home()`（D-032 红线：禁裸
    `Path.home()` 硬编码兜底；解析顺序=显式 `--home` > `$PAPER_CRAWLER_HOME` >
    `~/.paper-crawler`，与 CLI 主程序/`scripts/budget_ledger.py`/`scripts/repec_snapshot.py`
    逐字段同源——此前本函数手写了一份行为等价但独立维护的复本，R2c 收敛为单一权威源）。

    **实况**：`_install_launchd` 写的 plist 恒显式带 `--home {home}`（见其 `ProgramArguments`），
    故 launchd 定时触发时 `cli_home` 恒非空、本函数只走"显式"这一支，从不依赖 `$PAPER_CRAWLER_HOME`
    /默认兜底——这两支只在用户手动交互式跑本脚本（不传 `--home`）时才可能命中，`resolve_home()`
    的统一收益（单一权威源、D-032 纪律）主要体现在那种场景，而非日常 launchd 定时作业本身。
    """
    explicit = Path(cli_home).expanduser() if cli_home else None
    return resolve_home(explicit)


def _load_credentials(cfg_path: Path) -> tuple[str, str]:
    if not cfg_path.exists():
        sys.exit(
            f"[refresh-token] 配置不存在：{cfg_path}\n"
            "请先创建并写入 [auth.openreview] username/password（见脚本 docstring）。"
        )
    with cfg_path.open("rb") as f:
        cfg = tomllib.load(f)
    section = cfg.get("auth", {}).get("openreview", {})
    username = str(section.get("username", "")).strip()
    password = str(section.get("password", ""))
    if not username or not password:
        sys.exit(
            "[refresh-token] [auth.openreview] 缺 username 或 password 字段。\n"
            "请在 config.toml 补充（值不会被本脚本打印）。"
        )
    return username, password


def _login(username: str, password: str) -> str:
    body = json.dumps({"id": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        LOGIN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            set_cookies = resp.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            # 不回显任何凭证；OpenReview 对错误凭证返回 400/401。
            sys.exit(
                f"[refresh-token] 登录被拒（HTTP {exc.code}）："
                "请核对 config.toml 中的账号密码（值不回显）。"
            )
        sys.exit(f"[refresh-token] 登录端点异常：HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError) as exc:
        sys.exit(f"[refresh-token] 网络错误：{type(exc).__name__}（请检查网络后重试）")
    token = _extract_token(payload, set_cookies)
    if not token:
        # 诊断输出只含结构（键名/类型/cookie 名），绝不含任何值。
        sys.exit(
            "[refresh-token] 未能从登录响应中定位 token。响应结构（仅键名，值已脱敏）：\n"
            f"  body: {_shape(payload)}\n"
            f"  set-cookie 名: {[c.split('=', 1)[0] for c in set_cookies]}\n"
            "请把以上结构信息反馈给维护者以适配新结构。"
        )
    return token


def _extract_token(payload: object, set_cookies: list[str]) -> str:
    """按已知候选位置提取 accessToken：body 顶层/嵌套 → Set-Cookie 头。"""
    if isinstance(payload, dict):
        for key in ("token", "accessToken", "access_token"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        user = payload.get("user")
        if isinstance(user, dict):
            for key in ("token", "accessToken"):
                value = user.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    for cookie in set_cookies:
        name, _, rest = cookie.partition("=")
        if name.strip() == "openreview.accessToken":
            return rest.split(";", 1)[0].strip()
    return ""


def _shape(obj: object, depth: int = 0) -> str:
    """响应结构骨架：键名保留、所有值替换为类型占位（诊断用，零泄漏）。"""
    if depth > 2:
        return "..."
    if isinstance(obj, dict):
        inner = ", ".join(f"{k}: {_shape(v, depth + 1)}" for k, v in obj.items())
        return "{" + inner + "}"
    if isinstance(obj, list):
        return f"[{_shape(obj[0], depth + 1)} x{len(obj)}]" if obj else "[]"
    return f"<{type(obj).__name__}>"


def _write_back(cfg_path: Path, token: str) -> None:
    """行级替换 [auth.openreview] 节内的 token 行；无则在节内插入。原子写回 + 0600。"""
    lines = cfg_path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    in_section = False
    replaced = False
    inserted_pending = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if in_section and not replaced:
                out.append(f'token = "{token}"\n')
                replaced = True
            in_section = stripped == "[auth.openreview]"
            inserted_pending = in_section
            out.append(line)
            continue
        if in_section and re.match(r"^\s*token\s*=", line):
            out.append(f'token = "{token}"\n')
            replaced = True
            inserted_pending = False
            continue
        out.append(line)
    if in_section and not replaced:  # 节在文件末尾且无 token 行
        out.append(f'token = "{token}"\n')
        replaced = True
    if not replaced and not inserted_pending:
        sys.exit("[refresh-token] config.toml 无 [auth.openreview] 节——请先按 docstring 建节。")
    tmp = cfg_path.with_suffix(".toml.tmp")
    tmp.write_text("".join(out), encoding="utf-8")
    os.replace(tmp, cfg_path)
    cfg_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def _verify(token: str) -> bool:
    req = urllib.request.Request(
        VERIFY_URL,
        headers={"User-Agent": UA, "Cookie": f"openreview.accessToken={token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False


def _install_launchd(script_path: Path, home: Path) -> None:
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{PLIST_LABEL}.plist"
    plist_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script_path}</string>
    <string>--home</string>
    <string>{home}</string>
  </array>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{log_dir}/token-refresh.log</string>
  <key>StandardErrorPath</key><string>{log_dir}/token-refresh.err</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.exit(
            f"[refresh-token] launchctl load 失败：{result.stderr.strip()}\n"
            f"plist 已写至 {plist_path}，可手动 load。"
        )
    print(
        f"[refresh-token] launchd 已安装并启动：每小时自动刷新"
        f"（plist: {plist_path}；日志: {log_dir}/token-refresh.log）"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", default=None, help="PAPER_CRAWLER_HOME（默认 ~/.paper-crawler）")
    parser.add_argument(
        "--verify", action="store_true", help="刷新后用 1 个 API 请求验证 token 可用"
    )
    parser.add_argument(
        "--install-launchd", action="store_true", help="安装 macOS launchd 每小时定时任务并立即启动"
    )
    args = parser.parse_args()

    home = _home_dir(args.home)
    if args.install_launchd:
        _install_launchd(Path(__file__).resolve(), home)
        return

    cfg_path = home / "config.toml"
    username, password = _load_credentials(cfg_path)
    token = _login(username, password)
    _write_back(cfg_path, token)
    print(f"[refresh-token] token 已刷新并写回 {cfg_path}（值不回显；文件权限 0600）")
    if args.verify:
        if _verify(token):
            print("[refresh-token] 验证通过：API 访问正常（/notes 200）")
        else:
            print(
                "[refresh-token] ⚠ 验证未通过：token 已写回但 API 校验失败，请检查网络或稍后重试",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
