from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def lookup(query, language):
    params = urlencode({
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
        "prop": "extracts|info", "inprop": "url", "explaintext": 1, "titles": query,
    })
    request = Request(
        f"https://{language}.wikipedia.org/w/api.php?{params}",
        headers={"User-Agent": "crawler-package-platform/1.0", "Accept-Language": language},
    )
    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    content = str(page.get("extract", "")).strip()
    if not content or not page.get("fullurl"):
        return None
    return {
        "external_id": f"{language}:{page.get('pageid')}", "title": page.get("title", query),
        "url": page["fullurl"], "summary": content.split("\n", 1)[0][:4000],
        "content": content, "publisher": f"Wikipedia {language}",
        "language": language, "source_site": f"wikipedia_{language}",
    }


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
        items = []
        zh = lookup(request_data["query"], "zh")
        if zh:
            items.append(zh)
        if len(items) < request_data["limit"] and request_data["parameters"].get("english_fallback", True):
            en = lookup(request_data["query"], "en")
            if en:
                items.append(en)
        write_output(output, request_data["execution_id"], items[:request_data["limit"]])
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", {"code":"NETWORK_OR_PARSE_ERROR","message":f"{type(exc).__name__}: {exc}","retryable":True})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
