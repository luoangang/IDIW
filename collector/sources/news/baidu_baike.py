"""Baidu Baike news-module source plugin."""
from __future__ import annotations

from urllib.parse import quote

from bs4 import BeautifulSoup

from collector.sources.base import CollectionRequest, SourceItem, SourcePlugin


class BaiduBaikePlugin(SourcePlugin):
    module = "news"
    name = "baidu_baike"
    label = "百度百科"
    table_name = "baidu_baike_items"
    default_limit = 1
    description = "百度百科词条正文与摘要"
    resource_type = "encyclopedia_entry"

    def collect(self, request: CollectionRequest) -> list[SourceItem]:
        self.validate_request(request)
        query, limit = request.query, request.limit
        if limit < 1:
            return []
        # The mobile entry is substantially more stable than the desktop page,
        # which commonly responds with 403 to non-browser collectors.
        url = f"https://wapbaike.baidu.com/item/{quote(query, safe='')}"
        session = self.http()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
            "Referer": "https://www.baidu.com/",
        })
        response = session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        title_node = soup.select_one('h1, [class*="lemmaTitle"]')
        title = title_node.get_text(" ", strip=True) if title_node else query
        description = soup.select_one('meta[name="description"]')
        summary = description.get("content", "").strip() if description else ""

        selectors = [
            '[class*="pageContent"]', '[class*="abstract"]',
            ".lemma-summary", ".J-summary", ".main-content", "main", "article",
        ]
        content = ""
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                content = node.get_text("\n", strip=True)
                if len(content) >= 80:
                    break
        if not content:
            content = summary
        if not content and "百度百科" not in soup.get_text(" ", strip=True):
            return []

        canonical = soup.select_one('link[rel="canonical"]')
        final_url = canonical.get("href", response.url) if canonical else response.url
        return [SourceItem(
            title=title,
            url=final_url,
            summary=summary,
            content=content,
            publisher="百度百科",
            language="zh",
            resource_type=self.resource_type,
            extra={"requested_url": url},
        )]
