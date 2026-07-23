"""aea fixture 加载器（`tests/fixtures/aea/`）。

出处分级（design/adapters/aea.md §8；每文件头/`_grounded` 字段注明）：
- `01_challenge_cf_mitigated.http`：**[LIVE-DERIVED]**——依
  `docs/research/site-survey/aea.md` §4/附录请求 #11 的 [LIVE] 2026-07-24 实测记录
  构造（`HEAD pubs.aeaweb.org/doi/pdfplus/{JEP DOI}` → `HTTP/2 403` +
  `cf-mitigated: challenge` + 5672B 挑战体）；body 为最小复刻（非 5672B 全量——原始
  响应体未随勘察提交 git，只有文字记录，沿 oup_silverchair `01_challenge_cf_mitigated`
  fixture 先例："仅保留判定器所需特征"）。
- `02_crossref_aer_works_sample.json` / `03_crossref_single_doi_aer.json`：
  **[LIVE-DERIVED]**——DOI/ISSN/volume/issue/published/abstract 长度等结构性字段
  取自 site-survey §2/§3 实测记录；`title`/`abstract` 正文本身未随勘察提交（仅记长度
  724 字符），此处为长度匹配的 **[SYNTHETIC]** 占位文本（非真实版权文字，含
  `_grounded` 字段逐一注明）。
- `04_landing_citation_meta.html`：**[SYNTHETIC]**——依 site-survey §2 记录的
  `citation_*` meta 键集合（title/journal_title/issn/volume/issue/firstpage/
  lastpage/doi/pdf_url/author/author_institution）手写最小合法 HTML，非真实页面
  截断。
- `05_unpaywall_closed_aer.json` / `06_unpaywall_gold_jep.json`：**[LIVE-DERIVED]**
  ——`is_oa`/`oa_status`/`best_oa_location.host_type` 等判定性字段取自 site-survey
  §5/§4 实测记录（`_grounded` 字段逐一注明字段出处）；周边 schema 形状手写、非
  literal 捕获响应体。

``.http`` 格式（沿 wiley/oup_silverchair fixtures 约定）：``#`` 开头行为注释；
``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为响应头；**首个空行**后为
原始 body。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "aea"


def fixture_bytes(name: str) -> bytes:
    """读取 `aea/<name>` 的原始字节。"""
    return (_DIR / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 ``.http`` 快照 → ``(status, headers, body)``（见模块 docstring 的格式说明）。"""
    raw = (_DIR / name).read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:  # 无空行分隔——整体视为 body，200 无头
        return 200, {}, raw
    status = 200
    headers: dict[str, str] = {}
    for line in head.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if key.upper() == "HTTP-STATUS":
            status = int(value)
        else:
            headers[key] = value
    return status, headers, body


__all__ = ["fixture_bytes", "http_fixture"]
