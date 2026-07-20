"""六阶段 pipeline 执行器（接口冻结件 §2.7）。

- `fetchio`（T7a）：下载原子性 `PartFileIO`/`validate_pdf_magic`/`cleanup_tmp`
  （design/05 §5.2）；
- `report`（T7b）：`RunReport` 运行报告（design/05 §7）；
- `stages`（T7c）：`Selector`/`StageContext` 与六阶段 handler（design/05 §1）；
- `runner`（T7c）：`PipelineRunner` —— pull 级联编排、串行 drain、错误分类路由
  （design/05 §2/§3/§4/§5）。
"""

from paper_crawler.pipeline.fetchio import PartFileIO, cleanup_tmp, validate_pdf_magic
from paper_crawler.pipeline.report import RunReport
from paper_crawler.pipeline.runner import PipelineRunner
from paper_crawler.pipeline.stages import Selector, StageContext

__all__ = [
    "PartFileIO",
    "PipelineRunner",
    "RunReport",
    "Selector",
    "StageContext",
    "cleanup_tmp",
    "validate_pdf_magic",
]
