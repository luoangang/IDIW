"""Google News RSS source plugin for the news module."""
from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from collector.sources.base import CollectionRequest, SourceItem, SourcePlugin


class GoogleNewsRSSPlugin(SourcePlugin):
    module = "news"
    name = "google_news_rss"
    label = "Google 新闻 RSS"
    table_name = "google_news_items"
    default_limit = 30
    description = "Google 新闻搜索 RSS，可调整语言和地区"
    resource_type = "news_article"
    configurable = {
        "language": {"type": "select", "default": "zh-CN", "options": ["zh-CN", "en-US"], "label": "语言"},
        "country": {"type": "select", "default": "CN", "options": ["CN", "US", "GB"], "label": "地区"},
    }

    def collect(self, request: CollectionRequest) -> list[SourceItem]:
        self.validate_request(request)
        query, limit, config = request.query, request.limit, request.config
        language = config.get("language", "zh-CN")
        country = config.get("country", "CN")
        ceid = f"{country}:{language.split('-')[0]}"
        url = (
            "https://news.google.com/rss/search?q=" + quote_plus(query)
            + f"&hl={language}&gl={country}&ceid={ceid}"
        )
        response = self.get(url)
        root = ElementTree.fromstring(response.content)
        items: list[SourceItem] = []
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            if not title or not link:
                continue
            source_node = node.find("source")
            publisher = source_node.text.strip() if source_node is not None and source_node.text else ""
            description = node.findtext("description") or ""
            summary = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
            published_at = None
            published = node.findtext("pubDate")
            if published:
                try:
                    published_at = parsedate_to_datetime(published).astimezone(timezone.utc).replace(tzinfo=None)
                except (TypeError, ValueError):
                    pass
            guid = (node.findtext("guid") or "").strip()
            items.append(SourceItem(
                title=title,
                url=link,
                summary=summary,
                publisher=publisher,
                published_at=published_at,
                language=language,
                source_item_id=guid,
                resource_type=self.resource_type,
            ))
            if len(items) >= limit:
                break
        return items
