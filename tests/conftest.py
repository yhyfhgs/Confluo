"""共享 fixtures。T1 提供一份合法 VenueSpec；后续任务按需增补。"""

import pytest

from paper_crawler.types import VenueSpec


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
