"""`crawler subs watch` CLI 集成测试（Phase 6 T5 DoD："CLI 集成测试走真实 argv"）。

全部经 `typer.testing.CliRunner` 打真实参数（不直接调命令函数），覆盖：用法校验、
未知订阅、坏订阅文件、happy path（退出 0 + 日报落盘）、`--dry-run`（退出 0 + 不落盘 +
stdout 回显日报）、熔断（退出 3 + 熔断简报一行）、`--all` 多订阅合并、空目录。

零网络：`cli._watch_fetcher_factory` 是模块级 seam（同 `_http_client_factory` 的注入
惯例），本测试把它换成 mock_platform 驱动的 `AdapterFetcher`；日报落盘路径相对当前
工作目录，故整组测试 `chdir` 到 tmp（绝不写进真实仓库的 docs/）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from paper_crawler import cli as cli_module
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.cli import app
from paper_crawler.errors import WatermarkInvalid
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import SubscriptionRepo
from paper_crawler.subs.types import FailureEvent, RunSummary
from paper_crawler.subs.watch import (
    AdapterFetcher,
    NberRssFetcher,
    RoutingFetcher,
    SourceFetcher,
    SourceRequest,
)
from paper_crawler.types import VenueNames, VenueSpec

runner = CliRunner()

# 模块导入期捕获真实装配件——autouse 的 seam fixture 之后会把模块属性换成 mock 版本。
_REAL_FETCHER_FACTORY = cli_module._watch_fetcher_factory

CORPUS_SIZE = 6
_REPORT_DIR = Path("docs") / "reports" / "watch"


def _mock_source_venue() -> VenueSpec:
    """喂给 mock_platform 的语料配置（一卷一期六篇，seed 固定 → 确定性）。"""
    return VenueSpec(
        id="mock_journal",
        kind="journal",
        names=VenueNames(full="Mock Journal"),
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
        quirks={"volumes": 1, "issues_per_volume": 1, "papers_per_issue": CORPUS_SIZE, "seed": 42},
    )


@pytest.fixture(autouse=True)
def _fetcher_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """把订阅拉取件换成 mock_platform（零网络；真实 argv 仍走完整 CLI 装配）。"""

    def _factory(env: cli_module.CliEnv) -> SourceFetcher:
        del env
        venue = _mock_source_venue()
        return AdapterFetcher({"crossref": MockPlatformAdapter()}, venues={"crossref": venue})

    monkeypatch.setattr(cli_module, "_watch_fetcher_factory", _factory)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离 HOME（config + venues + subscriptions）+ chdir 到 tmp（日报落 tmp/docs/…）。"""
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    home_dir = tmp_path / "home"
    venues_dir = home_dir / "venues"
    venues_dir.mkdir(parents=True)
    (home_dir / "subscriptions").mkdir()
    (home_dir / "config.toml").write_text(
        '[paths]\nvenues_dirs = ["venues"]\n[identity]\nemail = "test@example.com"\n',
        encoding="utf-8",
    )
    (venues_dir / "mock-journal.yaml").write_text(
        yaml.safe_dump(_mock_source_venue().model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    return home_dir


def _write_subscription(
    directory: Path, name: str, *, guard: dict[str, object] | None = None
) -> None:
    doc: dict[str, object] = {
        "name": name,
        "sources": {"crossref": {"issns": ["0000-0000"]}},
        "actions": {"ingest": "metadata"},
        "guard": guard if guard is not None else {"max_new_per_run": 200},
    }
    (directory / f"{name}.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _invoke(home: Path, *args: str) -> Result:
    return runner.invoke(app, ["subs", "watch", *args, "--home", str(home)])


# --- 用法校验（退出码 2）------------------------------------------------------


def test_neither_name_nor_all_exits_2(home: Path) -> None:
    result = _invoke(home)
    assert result.exit_code == 2
    assert "必须指定 NAME 或 --all" in result.output


def test_name_and_all_together_exits_2(home: Path) -> None:
    _write_subscription(home / "subscriptions", "mock-watch")
    result = _invoke(home, "mock-watch", "--all")
    assert result.exit_code == 2


def test_unknown_subscription_exits_2(home: Path) -> None:
    _write_subscription(home / "subscriptions", "mock-watch")
    result = _invoke(home, "nope")
    assert result.exit_code == 2
    assert "未知订阅" in result.output


def test_invalid_subscription_file_rejects_the_whole_run(home: Path) -> None:
    """plan §4 T5 裁决④：坏订阅整体响亮拒载，报错带出错文件路径。"""
    _write_subscription(home / "subscriptions", "good")
    bad = home / "subscriptions" / "bad.yaml"
    bad.write_text("name: bad\nsources: {arxiv: {catgories: [cs.AI]}}\n", encoding="utf-8")

    result = _invoke(home, "--all")

    assert result.exit_code == 2
    assert str(bad) in result.output


def test_missing_subscriptions_dir_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """两段查找都落空（home 下没有、CWD 下也没有）→ 拒载而非静默"零个订阅"。"""
    workdir = tmp_path / "empty-work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    home_dir = tmp_path / "home2"
    (home_dir / "venues").mkdir(parents=True)
    (home_dir / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")

    result = runner.invoke(app, ["subs", "watch", "--all", "--home", str(home_dir)])

    assert result.exit_code == 2
    assert "订阅目录不存在" in result.output


# --- happy path ---------------------------------------------------------------


def test_watch_single_subscription_writes_the_daily_report(home: Path) -> None:
    _write_subscription(home / "subscriptions", "mock-watch")

    result = _invoke(home, "mock-watch")

    assert result.exit_code == 0
    assert f"新增 {CORPUS_SIZE} 入库 {CORPUS_SIZE}" in result.output
    assert "日报已落盘" in result.output
    reports = sorted(_REPORT_DIR.glob("daily-*.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "## mock-watch" in text
    assert "### 新增清单" in text


def test_watch_uses_cwd_subscriptions_when_home_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`<home>/subscriptions` 不存在时退到 CWD 的 `subscriptions/`（design/09 §2 字面路径）。"""
    workdir = tmp_path / "repo-root"
    (workdir / "subscriptions").mkdir(parents=True)
    monkeypatch.chdir(workdir)
    home_dir = tmp_path / "home3"
    (home_dir / "venues").mkdir(parents=True)
    (home_dir / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    _write_subscription(workdir / "subscriptions", "cwd-watch")

    result = runner.invoke(app, ["subs", "watch", "cwd-watch", "--home", str(home_dir)])

    assert result.exit_code == 0
    assert "cwd-watch" in result.output


def test_watch_all_merges_two_subscriptions_into_one_report(home: Path) -> None:
    _write_subscription(home / "subscriptions", "alpha")
    _write_subscription(home / "subscriptions", "beta")

    result = _invoke(home, "--all")

    assert result.exit_code == 0
    reports = sorted(_REPORT_DIR.glob("daily-*.md"))
    assert len(reports) == 1  # 多订阅合并**一份**
    text = reports[0].read_text(encoding="utf-8")
    assert "## alpha" in text and "## beta" in text
    # beta 串行跑在 alpha 之后，看到的是已被 alpha 填过的库 → 零新增。
    assert "beta: 状态 ok 候选 6 新增 0" in result.output


def test_empty_subscriptions_dir_exits_0_with_a_message(home: Path) -> None:
    result = _invoke(home, "--all")
    assert result.exit_code == 0
    assert "没有已登记的订阅" in result.output
    assert not _REPORT_DIR.exists()


# --- dry-run / 熔断 ------------------------------------------------------------


def test_dry_run_echoes_the_report_without_writing_it(home: Path) -> None:
    _write_subscription(home / "subscriptions", "mock-watch")

    result = _invoke(home, "mock-watch", "--dry-run")

    assert result.exit_code == 0
    assert "（预览，未入库）" in result.output
    assert "# 日报 — " in result.output  # 日报回显到 stdout
    assert "日报已落盘" not in result.output
    assert not _REPORT_DIR.exists()


def test_dry_run_then_real_run_still_ingests(home: Path) -> None:
    """dry-run 不动库 → 紧接着的真实运行仍是"全新"（AC-6.2 的"零副作用"字面）。"""
    _write_subscription(home / "subscriptions", "mock-watch")

    _invoke(home, "mock-watch", "--dry-run")
    result = _invoke(home, "mock-watch")

    assert result.exit_code == 0
    assert f"入库 {CORPUS_SIZE}" in result.output


def test_truncation_exits_3_and_prints_the_overload_brief(home: Path) -> None:
    _write_subscription(home / "subscriptions", "mock-watch", guard={"max_new_per_run": 2})

    result = _invoke(home, "mock-watch")

    assert result.exit_code == 3
    assert "状态 truncated" in result.output
    assert "熔断简报:" in result.output
    assert "入库 0" in result.output
    # 熔断仍出日报（过载报告段），但零入库。
    text = sorted(_REPORT_DIR.glob("daily-*.md"))[0].read_text(encoding="utf-8")
    assert "### 过载分布" in text


# --- 存储侧水位损坏：优雅报错、退出码非零、无裸 traceback -----------------------


def _corrupt_watermark(home: Path, name: str) -> None:
    """把某条订阅的水位文档直改成 partial `'2026'`（存储侧 `_parse_date` 必拒载）。

    经真实 `SubscriptionRepo` 写，不裸拼 SQL——写入口的 JSON 序列化口径与生产同一份。
    """
    database = Database(home / "catalog.sqlite")
    try:
        SubscriptionRepo(database).write_watermark(
            name,
            {"schema_ver": 1, "sources": {"crossref": {"kind": "date_cursor", "date": "2026"}}},
        )
    finally:
        database.close()


def test_broken_watermark_exits_1_with_a_graceful_error(home: Path) -> None:
    """单订阅路径：水位损坏 → "错误: …" 一行 + 退出码 1，**不是**裸 traceback。

    线上 P0 的用户可见面正是这一条：异常一路冒到 typer 之外，用户看到的是一屏 Python
    调用栈。修法两层——`run_watch_all` 的订阅级隔离把它收进 `RunSummary.failures`，
    CLI 再把消息打成一行（`_echo_error` 既有样式）。
    """
    _write_subscription(home / "subscriptions", "mock-watch")
    _invoke(home, "mock-watch")  # 先跑一次，把订阅行与库建出来
    _corrupt_watermark(home, "mock-watch")

    result = _invoke(home, "mock-watch")

    assert result.exit_code == 1
    assert "错误: mock-watch: " in result.output
    assert "无法解析为 ISO 日期" in result.output
    assert "状态 failed" in result.output
    # 优雅 = 命令自己收场：CliRunner 拿到的是 typer 的正常退出，不是逃逸的异常。
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output


def test_broken_watermark_in_one_subscription_lets_the_others_run(home: Path) -> None:
    """`--all` 路径：坏订阅记失败，**其余订阅照跑照入库**，日报照落盘，退出码 1。"""
    _write_subscription(home / "subscriptions", "alpha")
    _write_subscription(home / "subscriptions", "beta")
    _invoke(home, "--all")  # 建库 + 两条订阅行；这一轮 alpha 把语料全入了库
    _corrupt_watermark(home, "alpha")

    result = _invoke(home, "--all")

    assert result.exit_code == 1
    assert "错误: alpha: " in result.output
    assert "beta: 状态 ok" in result.output  # 坏订阅之后的订阅照跑
    assert "日报已落盘" in result.output
    text = sorted(_REPORT_DIR.glob("daily-*.md"))[0].read_text(encoding="utf-8")
    assert "## alpha" in text and "## beta" in text
    assert "### 失败事件" in text


def test_a_crawler_error_escaping_the_watch_subsystem_stays_graceful(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """命令边界契约：从 watch 子系统逃出来的 `CrawlerError` 一律"错误: …" + 退出码 1。

    `run_watch_all` 现在自己做订阅级隔离，正常路径不会有异常逃到这里——但那是**它**的
    实现细节，不是本命令可以依赖的不变量（子系统日后在循环外新增一处受控故障就会破功，
    用户又得看一屏 traceback）。故命令边界保留 catch，并用本用例把它钉成活代码而非
    无人走过的死分支（同 `_fetcher_seam` 的模块属性注入手法）。
    """
    _write_subscription(home / "subscriptions", "mock-watch")

    def _boom(*args: object, **kwargs: object) -> object:
        raise WatermarkInvalid("watermark:sources.crossref.date —— 边界契约用例", detail="x")

    monkeypatch.setattr(cli_module, "run_watch_all", _boom)

    result = _invoke(home, "mock-watch")

    assert result.exit_code == 1
    assert "错误: watermark:sources.crossref.date" in result.output
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_watch_help_lists_the_subcommand(home: Path) -> None:
    """`crawler subs --help` 能看到 watch（子命令组挂载生效，不是死代码）。"""
    result = runner.invoke(app, ["subs", "--help"])
    assert result.exit_code == 0
    assert "watch" in result.output


def test_legacy_venue_watch_command_is_untouched() -> None:
    """既有 `crawler watch <venue>` 逐字不变（命名共存：订阅 watch 落在 `subs watch`）。"""
    result = runner.invoke(app, ["watch", "--help"])
    assert result.exit_code == 0
    assert "preprint" in result.output


# --- 装配件本身（seam 被 monkeypatch 掉的那一份，单独直测）---------------------


def test_real_fetcher_factory_registers_rate_domains_and_injects_the_shared_client(
    home: Path,
) -> None:
    """真实装配：`load_adapters()` → 注入共享 http + 登记限速域（不另开绕过限速的通道）。

    autouse 的 seam fixture 换掉了模块属性，故这里用模块导入期捕获的原件直测。
    """
    env = cli_module._build_env(home, False)
    try:
        fetcher = _REAL_FETCHER_FACTORY(env)
        # arxiv 是多域 adapter：主域已登记、副域已别名到主域（不放宽速率）。
        assert env.ctx.limiter.acquire("export.arxiv.org") >= 0
        # nber 走专属 RSS 通道，其余退到 AdapterFetcher（P1-B 路由）。
        assert isinstance(fetcher, RoutingFetcher)
        assert isinstance(fetcher._routes["nber"], NberRssFetcher)
        fallback = fetcher._fallback
        assert isinstance(fallback, AdapterFetcher)
        # 合成 venue 兜底可用（registry 里没有以 crossref 为 fulltext_source 的 venue）。
        spec = fallback.venue_for(SourceRequest(subscription="s", source="crossref"))
        assert spec.fulltext_source == "crossref"
        # back.nber.org 已登记限速桶（RSS 请求走共享 limiter，不绕过限速）。
        assert env.ctx.limiter.acquire("back.nber.org") >= 0
    finally:
        env.http.close()
        env.ctx.db.close()


def test_summary_line_names_the_failing_sources() -> None:
    summary = RunSummary(
        subscription="s",
        started_at="2026-07-26T00:00:00+00:00",
        failures=(
            FailureEvent(source="s2", error_class="transient", message="boom"),
            FailureEvent(source="ssrn", error_class="transient", message="boom"),
        ),
    )
    line = cli_module._subs_summary_line(summary)
    assert "失败源: s2, ssrn" in line
