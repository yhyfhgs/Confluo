"""六阶段 pipeline 执行器（接口冻结件 §2.7）。

已落地并在此重导出：`fetchio`（T7a：下载原子性 `PartFileIO`/`validate_pdf_magic`/
`cleanup_tmp`，design/05 §5.2）与 `report`（T7b：`RunReport` 运行报告，design/05 §7）。
`stages.py`/`runner.py`（`PipelineRunner`/`StageContext`，T7c）落盘后在此补齐 re-export。
"""

from paper_crawler.pipeline.fetchio import PartFileIO, cleanup_tmp, validate_pdf_magic
from paper_crawler.pipeline.report import RunReport

__all__ = [
    "PartFileIO",
    "RunReport",
    "cleanup_tmp",
    "validate_pdf_magic",
]
