from confluo_scout.search.graph import SessionGraph
from confluo_scout.search.highlight import Highlighter
from confluo_scout.search.parse import exact_expression, parse_query
from confluo_scout.search.text import cjk_chunks, is_cjk


def test_parse_fields_and_phrases():
    pq = parse_query('venue:iclr year:2025..2027 author:"Yoshua Bengio" status:oral "world models" planning -robotics')
    assert pq.venues == ["iclr"] and pq.years == (2025, 2027) and pq.authors == ["Yoshua Bengio"]
    assert pq.labels == ["oral"] and pq.min_tier == 4
    assert pq.phrases == ["world models"] and pq.excludes == ["robotics"]
    assert pq.plain == "world models planning"
    assert parse_query("year:>=2026").years == (2026, 9999)
    assert parse_query("year:2024").years == (2024, 2024)


def test_exact_expression():
    assert exact_expression(parse_query('"diffusion model" AND (video OR audio) -survey')) == \
        '("diffusion model" AND ( "video" OR "audio" )) NOT ("survey")'
    assert exact_expression(parse_query("transform* title:attention")) == '"transform"* AND title : "attention"'
    assert exact_expression(parse_query("")) is None


def test_highlight_exact_and_near():
    h = Highlighter(["large language models"], ["llm"])
    html = h.render("Large Language Models (LLMs) and an LLM agent.")
    assert '<mark class="hit">Large Language Models</mark>' in html
    assert '<mark class="near">LLM</mark>' in html
    assert h.matched("large language model calibration") == ({"large language models"}, set())


def test_cjk_helpers():
    assert is_cjk("如何让大语言模型更准确地报告自己的置信度")
    assert cjk_chunks("如何让大语言模型更准确地报告自己的置信度") == ["大语言模型", "准确", "报告", "置信度"]


def test_ppr_rewards_multiple_paths():
    g = SessionGraph()
    g.add("q", "k:a", 1.0)
    g.add("q", "k:b", 1.0)
    g.add("k:a", "p:1", 1.0)
    g.add("k:b", "p:1", 1.0)
    g.add("k:a", "p:2", 1.0)
    pr = g.ppr()
    assert pr["p:1"] > pr["p:2"] > 0
