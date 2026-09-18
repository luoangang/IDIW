"""Patent module registration."""
from collector.modules.base import CollectorModule


MODULE = CollectorModule(
    name="patent",
    label="专利",
    description="专利公开文本、申请人及法律状态",
    resource_type="patent",
    supported_modes=("search", "sync"),
    query_label="技术主题、申请人或专利号",
    sort_order=30,
)
