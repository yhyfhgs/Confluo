"""共享 fixtures。T1 提供一份合法 VenueSpec；后续任务按需增补。

2026-07-22（合并期加固）：新增 socket 级禁网护栏——T1-T4 全离线是 Phase 2
Global Constraint，此前仅靠约定；T5 合并暴露 canary 集成测试经 arxiv
healthcheck 打真网的漏网路径后，改为结构性拦截。
"""

import socket

import pytest

from paper_crawler.types import VenueSpec


@pytest.fixture(autouse=True)
def _no_real_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """离线纪律护栏：非 `online` 标记的测试禁止真实 socket 连接。

    httpx.MockTransport / 进程内 CliRunner / sqlite / 文件 IO 均不触 socket.connect，
    不受影响；subprocess 子进程不继承本补丁（kill-9 类测试跑 mock adapter，本就
    无网络）。在线冒烟测试带 `@pytest.mark.online`，自动豁免。
    """
    if request.node.get_closest_marker("online"):
        return

    def _blocked(self: socket.socket, address: object) -> None:
        raise RuntimeError(
            f"offline test attempted real network connection to {address!r} "
            "(Phase 2 Global Constraint: T1-T4 zero real network; "
            "mark with @pytest.mark.online if intentional)"
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture
def venue_dict() -> dict[str, object]:
    """一份最小合法的 venue 声明（dict 形态，供构造/校验测试复用）。"""
    return {
        "id": "mock_journal",
        "kind": "journal",
        "names": {"full": "Mock Journal", "aliases": ["MJ"]},
        "field": ["cs_ai"],
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
    }


@pytest.fixture
def venue(venue_dict: dict[str, object]) -> VenueSpec:
    """已解析的 VenueSpec。"""
    return VenueSpec(**venue_dict)
