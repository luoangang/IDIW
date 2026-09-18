"""News and open-web intelligence module."""
from collector.modules.base import CollectorModule


MODULE = CollectorModule(
    name="news",
    label="新闻",
    description="新闻、百科和开放网页情报",
    resource_type="news_article",
    supported_modes=("search",),
    query_label="装备或主题",
    sort_order=10,
)
