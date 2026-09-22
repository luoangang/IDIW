from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree


def plain_text(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def write_output(output, execution_id, items, status="completed", error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {"protocol_version":"1.0","execution_id":execution_id,"status":status,"item_count":len(items),"next_cursor":None,"has_more":False,"warnings":[],"error":error}
    temporary = output / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output / "result.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(args.output)
    try:
        config = request_data["parameters"]
        language = config.get("language", "zh-CN")
        country = config.get("country", "CN")
        ceid = f"{country}:{language.split('-')[0]}"
        url = f"https://news.google.com/rss/search?q={quote_plus(request_data['query'])}&hl={language}&gl={country}&ceid={ceid}"
        http_request = Request(url, headers={"User-Agent":"Mozilla/5.0 crawler-package-platform/1.0","Accept-Language":language})
        with urlopen(http_request, timeout=20) as response:
            root = ElementTree.fromstring(response.read())
        items = []
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            guid = (node.findtext("guid") or link).strip()
            if not title or not link or not guid:
                continue
            source = node.find("source")
            published = node.findtext("pubDate")
            published_at = None
            if published:
                published_at = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            items.append({
                "external_id": guid[:1000], "title": title, "url": link,
                "summary": plain_text(node.findtext("description")) or None,
                "publisher": source.text.strip()[:255] if source is not None and source.text else None,
                "published_at": published_at, "language": language, "country": country,
                "source_site": "google_news_rss",
            })
            if len(items) >= request_data["limit"]:
                break
        write_output(output, request_data["execution_id"], items)
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", {"code":"NETWORK_OR_PARSE_ERROR","message":f"{type(exc).__name__}: {exc}","retryable":True})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
