"""Academic-paper module registration."""
from collector.modules.base import CollectorModule


MODULE = CollectorModule(
    name="paper",
    label="论文",
    description="中文与外文学术论文元数据",
    resource_type="academic_paper",
    supported_modes=("search", "sync"),
    query_label="论文主题、标题或作者",
    sort_order=20,
)
