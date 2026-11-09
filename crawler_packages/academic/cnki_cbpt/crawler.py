from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


class PaperParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.paper_depth = 0
        self.paper = None
        self.capture = None
        self.papers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        self.stack.append((tag, classes))
        if tag == "div" and "paperBox" in classes and self.paper is None:
            self.paper = {"title": "", "url": "", "authors": "", "abstract": "", "issue": ""}
            self.paper_depth = len(self.stack)
        if self.paper is None:
            return
        if tag == "a" and any(parent == "h3" for parent, _ in self.stack[:-1]):
            link = attrs.get("href") or ""
            if "/client/paper/" in link:
                self.paper["url"] = link
                self.capture = "title"
        elif tag == "span" and len(self.stack) == self.paper_depth + 1:
            self.capture = "authors"
        elif tag == "p" and "highText" in classes:
            self.capture = "abstract"
        elif tag == "span" and "publish-info" in classes:
            self.capture = "issue"

    def handle_data(self, data):
        if self.paper is not None and self.capture:
            self.paper[self.capture] += data

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if self.paper is not None:
            if self.capture == "title" and tag == "a":
                self.capture = None
            elif self.capture == "authors" and tag == "span":
                self.capture = None
            elif self.capture == "abstract" and tag == "p":
                self.capture = None
            elif self.capture == "issue" and tag == "span":
                self.capture = None
            if tag == "div" and len(self.stack) == self.paper_depth:
                for key in ("title", "authors", "abstract", "issue"):
                    self.paper[key] = " ".join(self.paper[key].split())
                if self.paper["title"] and self.paper["url"]:
                    self.papers.append(self.paper)
                self.paper = None
                self.paper_depth = 0
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def read_page(base_url, query, page, timeout):
    api = urljoin(base_url, "/portal/journal/portal/journal/api/listContent")
    body = json.dumps({"newsId": "", "xianzaiId": "", "content": query, "pageNum": page, "pageSize": 10}).encode("utf-8")
    request = Request(api, data=body, headers={
        "User-Agent": "Mozilla/5.0 journal-template-collector/1.0",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/html, */*",
    })
    with urlopen(request, timeout=timeout) as response:
        document = response.read(3_000_001)
        if len(document) > 3_000_000:
            raise ValueError("search response exceeds 3 MB")
        html = document.decode("utf-8", errors="replace")
    if "searchZone" not in html or "listContent" not in html:
        raise ValueError("site did not return a CBPT search page")
    parser = PaperParser()
    parser.feed(html)
    return parser.papers


def collect(request_data, journals):
    parameters = request_data.get("parameters") or {}
    keys = parameters.get("journal_keys") or []
    if not keys:
        raise ValueError("journal_keys cannot be empty")
    query = request_data["query"].strip()
    if not query:
        raise ValueError("query cannot be empty")
    limit = request_data["limit"]
    per_journal_limit = parameters.get("per_journal_limit", 20)
    timeout = parameters.get("timeout_seconds", 20)
    items, warnings = [], []
    successful = 0
    for index, key in enumerate(keys[:limit]):
        if len(items) >= limit:
            break
        journal_limit = min(per_journal_limit, limit // min(len(keys), limit) + int(index < limit % min(len(keys), limit)))
        journal = journals.get(key)
        if journal is None:
            warnings.append(f"Unknown journal key: {key}")
            continue
        host = urlsplit(journal["url"]).hostname or ""
        if not host.endswith(".cbpt.cnki.net"):
            warnings.append(f"Unsupported journal host: {host}")
            continue
        if host.startswith("www."):
            host = host[4:]
        base_url = "https://" + host
        seen = set()
        try:
            for page in range(1, min(100, journal_limit) + 1):
                records = read_page(base_url, query, page, timeout)
                if not records:
                    break
                page_added = 0
                for record in records:
                    url = urljoin(base_url, record["url"])
                    external_id = url.rstrip("/").split("/")[-1]
                    if not re.fullmatch(r"[\w-]{6,128}", external_id) or external_id in seen:
                        continue
                    seen.add(external_id)
                    items.append({
                        "journal_key": key, "journal_name": journal["name"][:255],
                        "journal_url": journal["url"], "external_id": external_id,
                        "title": record["title"][:1000], "url": url,
                        "authors": record["authors"] or None,
                        "abstract": record["abstract"] or None,
                        "issue": record["issue"][:255] or None,
                    })
                    page_added += 1
                    if len(seen) >= journal_limit or len(items) >= limit:
                        break
                if page_added == 0 or len(seen) >= journal_limit or len(items) >= limit:
                    break
            successful += 1
        except Exception as exc:
            warnings.append(f"{key} ({journal['name']}): {type(exc).__name__}: {exc}")
    return items, warnings, successful


def write_output(output, execution_id, items, status, warnings, error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {
        "protocol_version": "1.0", "execution_id": execution_id,
        "status": status, "item_count": len(items), "next_cursor": None,
        "has_more": False, "warnings": warnings, "error": error,
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
        rows = json.loads((Path(__file__).with_name("journals.json")).read_text(encoding="utf-8"))
        items, warnings, successful = collect(request_data, {row["journal_key"]: row for row in rows})
        status = "partial" if successful and warnings else "completed" if successful else "failed"
        error = None if successful else {"code": "ALL_JOURNALS_FAILED", "message": "; ".join(warnings)[:2000], "retryable": True}
        write_output(output, request_data["execution_id"], items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", [],
                     {"code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
