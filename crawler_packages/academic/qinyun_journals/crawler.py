from __future__ import annotations

import argparse
import html
import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


USER_AGENT = "Mozilla/5.0 (compatible; JournalMetadataCollector/1.0)"
MAX_RESPONSE = 3_000_000


def read_response(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError("response exceeds 3 MB")
        charset = response.headers.get_content_charset()
        if not charset:
            match = re.search(rb"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", content[:4000], re.I)
            charset = match.group(1).decode("ascii") if match else "utf-8"
        try:
            text = content.decode(charset, errors="replace")
        except LookupError:
            text = content.decode("utf-8", errors="replace")
        return text, response.geturl()


def discover_search(opener, journal, query, timeout):
    base = journal["url"].rstrip("/")
    publisher = journal.get("publisher")
    if not publisher:
        page, redirected = read_response(opener, Request(base, headers={"User-Agent": USER_AGENT}), timeout)
        match = re.search(r"(?i)href\s*=\s*['\"]/?([\w-]+)/home(?:[?'\"])", page)
        if not match:
            raise ValueError("UNSUPPORTED_TEMPLATE: no Qinyun /publisher/home link")
        publisher = match.group(1)
        base = f"{urlsplit(redirected).scheme}://{urlsplit(redirected).netloc}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", publisher):
        raise ValueError("invalid Qinyun publisher path")
    search_url = f"{base}/{publisher}/article/search?key={quote(query)}"
    page, _ = read_response(opener, Request(search_url, headers={"User-Agent": USER_AGENT}), timeout)
    if "/ajax/search" not in page:
        raise ValueError("UNSUPPORTED_TEMPLATE: no Qinyun AJAX search marker")
    hidden = re.search(r"<input\b(?=[^>]*\bname=['\"]CsrfCheckCode['\"])[^>]*>", page, re.I)
    csrf = re.search(r"\bvalue=['\"]([^'\"]*)['\"]", hidden.group(0), re.I) if hidden else None
    if not csrf or not csrf.group(1):
        raise ValueError("UNSUPPORTED_TEMPLATE: missing CsrfCheckCode")
    return base, publisher, html.unescape(csrf.group(1))


def search_page(opener, base, publisher, csrf, query, page, timeout):
    payload = {
        "from_year": "", "to_year": "", "search_type": "search", "source_type": "meta",
        "field": "", "key": query, "additional_year": "", "additional_author": "",
        "additional_keyword": "", "page": str(page), "page_size": "10", "CsrfCheckCode": csrf,
    }
    request = Request(
        f"{base}/{publisher}/ajax/search", data=urlencode(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Referer": f"{base}/{publisher}/home", "X-Requested-With": "XMLHttpRequest"},
    )
    raw, _ = read_response(opener, request, timeout)
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("rows") is None and (
        data.get("records") in (0, "0") or data.get("total") in (0, "0")
    ):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("UNSUPPORTED_TEMPLATE: Qinyun response lacks rows")
    return data["rows"]


def normalize(record, journal, base, publisher):
    if not isinstance(record, dict):
        return None
    title = html.unescape(re.sub(r"<[^>]+>", "", str(record.get("title") or ""))).strip()
    external_id = str(record.get("file_no") or "").strip()
    if not title or not external_id:
        return None
    doi = str(record.get("doi") or "").strip()
    raw_url = str(record.get("abstract_url") or "").strip()
    article_url = urljoin(base + "/", raw_url.lstrip("/")) if raw_url else f"{base}/{publisher}/article/abstract/{quote(external_id)}"
    year_raw = str(record.get("year_id") or "")[:4]
    author = html.unescape(re.sub(r"<[^>]+>", "", str(record.get("author_name") or record.get("display_author_name") or ""))).strip()
    abstract = html.unescape(re.sub(r"<[^>]+>", " ", str(record.get("abstract") or ""))).strip()
    return {
        "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
        "journal_url": journal["url"], "external_id": external_id[:128],
        "title": title[:1000], "url": article_url, "authors": author or None,
        "abstract": " ".join(abstract.split()) or None, "doi": doi[:255] or None,
        "year": int(year_raw) if year_raw.isdigit() else None,
    }


def hidden_fields(page):
    result = {}
    for tag in re.findall(r"<input\b[^>]*>", page, re.I):
        if not re.search(r"\btype=['\"]hidden['\"]", tag, re.I):
            continue
        name = re.search(r"\bname=['\"]([^'\"]+)['\"]", tag, re.I)
        value = re.search(r"\bvalue=['\"]([^'\"]*)['\"]", tag, re.I)
        if name:
            result[html.unescape(name.group(1))] = html.unescape(value.group(1)) if value else ""
    return result


def discover_old_search(opener, journal, timeout):
    base = journal["url"].rstrip("/")
    home, redirected = read_response(opener, Request(base, headers={"User-Agent": USER_AGENT}), timeout)
    match = re.search(r"(?:href|action)\s*=\s*['\"]([^'\"]*reader/key_query\.aspx[^'\"]*)['\"]", home, re.I)
    candidates = [urljoin(redirected, html.unescape(match.group(1)))] if match else []
    candidates.append(f"{urlsplit(redirected).scheme}://{urlsplit(redirected).netloc}/ch/reader/key_query.aspx")
    for search_url in dict.fromkeys(candidates):
        try:
            page, actual_url = read_response(opener, Request(search_url, headers={"User-Agent": USER_AGENT}), timeout)
        except Exception:
            continue
        if "__VIEWSTATE" in hidden_fields(page) and "key_query.aspx" in actual_url.lower():
            return actual_url, page
    raise ValueError("UNSUPPORTED_TEMPLATE: no ASP.NET key_query form")


def old_form_payload(page, query, next_page=False):
    payload = hidden_fields(page)
    if "__VIEWSTATE" not in payload:
        raise ValueError("UNSUPPORTED_TEMPLATE: missing ASP.NET viewstate")
    names = {match.group(1) for match in re.finditer(r"\bname=['\"]([^'\"]+)['\"]", page, re.I)}
    key_name = next((name for name in ("Key", "key", "keyword") if name in names), None)
    if not key_name:
        raise ValueError("UNSUPPORTED_TEMPLATE: unknown ASP.NET query field")
    payload[key_name] = query
    if "KeyList" in names:
        payload["KeyList"] = "title"
    payload["__EVENTTARGET"] = "next" if next_page else ""
    payload["__EVENTARGUMENT"] = ""
    if not next_page:
        button = next((name for name in ("Query", "Submit", "submit") if name in names), None)
        if not button:
            raise ValueError("UNSUPPORTED_TEMPLATE: unknown ASP.NET submit button")
        payload[button] = "检 索"
    return payload


def old_search_page(opener, search_url, page, query, timeout, next_page=False):
    payload = old_form_payload(page, query, next_page)
    request = Request(search_url, data=urlencode(payload).encode("utf-8"), headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": search_url,
    })
    result, actual_url = read_response(opener, request, timeout)
    if "key_query.aspx" not in actual_url.lower() and "view_abstract.aspx" not in result.lower():
        raise ValueError("UNSUPPORTED_TEMPLATE: old search did not return a result page")
    return result


def old_page_items(page, search_url, journal):
    seen = set()
    items = []
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", page, re.I | re.S):
        match = re.search(r"<a\b[^>]*href=['\"]([^'\"]*view_abstract\.aspx\?[^'\"]*)['\"][^>]*>(.*?)</a>", row, re.I | re.S)
        if not match:
            continue
        link = urljoin(search_url, html.unescape(match.group(1)))
        file_no = re.search(r"[?&]file_no=([^&]+)", link, re.I)
        title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", match.group(2))).split())
        if not file_no or not title or file_no.group(1) in seen:
            continue
        seen.add(file_no.group(1))
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).split()) for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.I | re.S)]
        authors = next((cell for cell in cells if cell and cell != title and not re.search(r"\d{4}.*\d+", cell)), None)
        year = re.search(r"\b(19|20)\d{2}\b", " ".join(cells))
        items.append({
            "journal_key": journal["journal_key"], "journal_name": journal["name"][:255],
            "journal_url": journal["url"], "external_id": file_no.group(1)[:128],
            "title": title[:1000], "url": link, "authors": authors,
            "abstract": None, "doi": None, "year": int(year.group(0)) if year else None,
        })
    return items


def enrich_old_detail(opener, item, timeout):
    try:
        detail, _ = read_response(opener, Request(item["url"], headers={"User-Agent": USER_AGENT}), timeout)
    except Exception:
        return item
    abstract = re.search(r"<span\b[^>]*id=['\"]Abstract['\"][^>]*>(.*?)</span>", detail, re.I | re.S)
    doi = re.search(r"<span\b[^>]*id=['\"]DOI['\"][^>]*>(.*?)</span>", detail, re.I | re.S)
    if abstract:
        item["abstract"] = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", abstract.group(1))).split()) or None
    if doi:
        item["doi"] = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", doi.group(1))).split())[:255] or None
    return item


def collect_old(opener, journal, query, limit, timeout):
    search_url, page = discover_old_search(opener, journal, timeout)
    seen = set()
    items = []
    for number in range(1, min(100, (limit + 19) // 20) + 1):
        result = old_search_page(opener, search_url, page, query, timeout, next_page=number > 1)
        new_items = old_page_items(result, search_url, journal)
        for item in new_items:
            if item["external_id"] not in seen:
                seen.add(item["external_id"])
                items.append(item)
                if len(items) >= limit:
                    break
        if len(items) >= limit or not new_items:
            break
        page_count = re.search(r"<span\b[^>]*id=['\"]PageCount['\"][^>]*>(\d+)</span>", result, re.I)
        if not page_count or number >= int(page_count.group(1)):
            break
        page = result
    return [enrich_old_detail(opener, item, timeout) for item in items]


def collect(request_data, journals):
    params = request_data.get("parameters") or {}
    keys = params.get("journal_keys", ["jos"])
    if not keys or not request_data["query"].strip():
        raise ValueError("journal_keys and query must be nonempty")
    limit = request_data["limit"]
    per_journal = min(params.get("per_journal_limit", 20), max(1, (limit + len(keys) - 1) // len(keys)))
    timeout = params.get("timeout_seconds", 20)
    items, warnings, successful = [], [], 0
    for key in keys:
        if len(items) >= limit:
            break
        journal = journals.get(key)
        if not journal:
            warnings.append(f"Unknown journal key: {key}")
            continue
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        seen = set()
        try:
            try:
                base, publisher, csrf = discover_search(opener, journal, request_data["query"].strip(), timeout)
            except ValueError as exc:
                if "UNSUPPORTED_TEMPLATE" not in str(exc):
                    raise
                items.extend(collect_old(opener, journal, request_data["query"].strip(), min(per_journal, limit - len(items)), timeout))
            else:
                for page in range(1, min(100, per_journal) + 1):
                    rows = search_page(opener, base, publisher, csrf, request_data["query"].strip(), page, timeout)
                    if not rows:
                        break
                    previous_count = len(seen)
                    for record in rows:
                        item = normalize(record, journal, base, publisher)
                        if item and item["external_id"] not in seen:
                            seen.add(item["external_id"])
                            items.append(item)
                            if len(seen) >= per_journal or len(items) >= limit:
                                break
                    if len(seen) >= per_journal or len(items) >= limit or len(seen) == previous_count:
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
    result = {"protocol_version": "1.0", "execution_id": execution_id, "status": status, "item_count": len(items), "next_cursor": None, "has_more": False, "warnings": warnings, "error": error}
    temp = output / "result.json.tmp"
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temp.replace(output / "result.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    try:
        rows = json.loads(Path(__file__).with_name("journals.json").read_text(encoding="utf-8"))
        items, warnings, successful = collect(request_data, {row["journal_key"]: row for row in rows})
        status = "partial" if successful and warnings else "completed" if successful else "failed"
        error = None if successful else {"code": "ALL_JOURNALS_FAILED", "message": "; ".join(warnings)[:2000], "retryable": True}
        write_output(Path(args.output), request_data["execution_id"], items, status, warnings, error)
        return 0 if successful else 1
    except Exception as exc:
        write_output(Path(args.output), request_data.get("execution_id", ""), [], "failed", [], {"code": "CRAWLER_ERROR", "message": f"{type(exc).__name__}: {exc}", "retryable": False})
        return 1


if __name__ == "__main__":
    sys.exit(main())
