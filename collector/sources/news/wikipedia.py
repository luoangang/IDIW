"""Wikipedia news-module source plugin using the MediaWiki API."""
from __future__ import annotations

from collector.sources.base import CollectionRequest, SourceItem, SourcePlugin


class WikipediaPlugin(SourcePlugin):
    module = "news"
    name = "wikipedia"
    label = "维基百科"
    table_name = "wikipedia_items"
    default_limit = 2
    description = "中英文维基百科词条，中文无结果时自动查询英文站"
    resource_type = "encyclopedia_entry"
    configurable = {
        "english_fallback": {"type": "boolean", "default": True, "label": "英文站回退"},
    }

    def _lookup(self, query: str, language: str) -> SourceItem | None:
        api = f"https://{language}.wikipedia.org/w/api.php"
        response = self.get(api, params={
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
            "prop": "extracts|info|pageprops",
            "inprop": "url",
            "explaintext": 1,
            "titles": query,
        })
        pages = response.json().get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None
        page = pages[0]
        content = page.get("extract", "").strip()
        if not content:
            return None
        summary = content.split("\n", 1)[0][:1000]
        return SourceItem(
            title=page.get("title", query),
            url=page.get("fullurl", ""),
            summary=summary,
            content=content,
            publisher=f"Wikipedia {language}",
            language=language,
            source_item_id=str(page.get("pageid", "")),
            resource_type=self.resource_type,
        )

    def collect(self, request: CollectionRequest) -> list[SourceItem]:
        self.validate_request(request)
        query, limit, config = request.query, request.limit, request.config
        if limit < 1:
            return []
        items = []
        zh_item = self._lookup(query, "zh")
        if zh_item:
            items.append(zh_item)
        if len(items) < limit and config.get("english_fallback", True):
            en_item = self._lookup(query, "en")
            if en_item and all(item.url != en_item.url for item in items):
                items.append(en_item)
        return items[:limit]
