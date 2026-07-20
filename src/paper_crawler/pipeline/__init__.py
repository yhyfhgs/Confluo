"""六阶段 pipeline 执行器（接口冻结件 §2.7）。

当前只有 `fetchio`（T7a 交付：下载原子性 `PartFileIO`/`validate_pdf_magic`/
`cleanup_tmp`，见 design/05 §5.2）落地并在此重导出。`report.py`（`RunReport`，
T7b）、`stages.py`/`runner.py`（`PipelineRunner`/`StageContext`，T7c）尚未交付；
待其落盘后在此补齐 re-export，本文件暂为空壳。
"""

from paper_crawler.pipeline.fetchio import PartFileIO, cleanup_tmp, validate_pdf_magic

__all__ = ["PartFileIO", "cleanup_tmp", "validate_pdf_magic"]
