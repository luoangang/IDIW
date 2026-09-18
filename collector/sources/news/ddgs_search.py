"""DDGS source plugin for the news module."""
from __future__ import annotations

from collector.sources.base import CollectionRequest, SourceItem, SourcePlugin


class DDGSSearchPlugin(SourcePlugin):
    module = "news"
    name = "ddgs"
    label = "DDGS"
    table_name = "ddgs_items"
    default_limit = 30
    description = "DuckDuckGo 网页搜索结果"
    resource_type = "web_page"
    configurable = {
        "region": {"type": "select", "default": "wt-wt", "options": ["wt-wt", "cn-zh", "us-en"], "label": "区域"},
        "safesearch": {"type": "select", "default": "off", "options": ["off", "moderate", "strict"], "label": "安全搜索"},
    }

    def collect(self, request: CollectionRequest) -> list[SourceItem]:
        self.validate_request(request)
        query, limit, config = request.query, request.limit, request.config
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise RuntimeError("缺少 ddgs 依赖，请运行 pip install -r requirements.txt") from exc

        region = config.get("region", "wt-wt")
        safesearch = config.get("safesearch", "off")
        results = DDGS().text(query, region=region, safesearch=safesearch, max_results=limit)
        items = []
        for row in results or []:
            url = (row.get("href") or row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            if not url or not title:
                continue
            items.append(SourceItem(
                title=title,
                url=url,
                summary=(row.get("body") or "").strip(),
                publisher="DuckDuckGo",
                language="",
                resource_type=self.resource_type,
            ))
        return items[:limit]
