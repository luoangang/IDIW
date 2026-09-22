from __future__ import annotations

import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.text = []
        self._title_depth = 0
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "h1":
            self._title_depth += 1
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content", "")
        if tag == "link" and "canonical" in values.get("rel", ""):
            self.canonical = values.get("href", "")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "h1" and self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value or self._skip_depth:
            return
        if self._title_depth:
            self.title += value
        self.text.append(value)


def write_output(output: Path, execution_id: str, items: list[dict], status="completed", error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {
        "protocol_version": "1.0", "execution_id": execution_id,
        "status": status, "item_count": len(items), "next_cursor": None,
        "has_more": False, "warnings": [], "error": error,
    }
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
        query = request_data["query"]
        requested_url = f"https://wapbaike.baidu.com/item/{quote(query, safe='')}"
        http_request = Request(requested_url, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36",
            "Referer": "https://www.baidu.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urlopen(http_request, timeout=20) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
        text = raw.decode(charset, errors="replace")
        page = PageParser()
        page.feed(text)
        content = "\n".join(dict.fromkeys(page.text))
        canonical = page.canonical or final_url
        match = re.search(r"/(\d+)(?:[/?#]|$)", canonical)
        external_id = match.group(1) if match else canonical
        item = {
            "external_id": external_id[:256], "title": (page.title or query).strip(),
            "url": canonical, "summary": html.unescape(page.description).strip() or None,
            "content": content or None, "publisher": "百度百科", "language": "zh",
            "source_site": "baidu_baike",
        }
        write_output(output, request_data["execution_id"], [item])
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", {
            "code": "NETWORK_OR_PARSE_ERROR", "message": f"{type(exc).__name__}: {exc}",
            "retryable": True,
        })
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
