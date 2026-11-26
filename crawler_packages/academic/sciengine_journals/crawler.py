from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


JOURNALS = {
    row["journal_key"]: row
    for row in json.loads((Path(__file__).with_name("journals.json")).read_text(encoding="utf-8"))
}
USER_AGENT = "Mozilla/5.0 (compatible; IDIW-SciEngineJournals/1.0; public metadata)"
SOURCE_API = "sciengine"
MAX_RESPONSE = 8_000_000
MAX_ABSTRACT = 5000

BLOCK_TAG = re.compile(r"</?(?:p|div|br|li|tr|td|th|h[1-6]|section|article|table)\b[^>]*>", re.I)
ANY_TAG = re.compile(r"<[^>]*>")
FRONT_MATTER_TITLE = re.compile(
    r"^(?:卷首语|序言|前言|编者按|编者的话|主编寄语|发刊词|特约主题|本期主题|本期导读|"
    r"目录|封面|封二|封三|封底|征稿|投稿|启事|稿约|编委会|理事会)"
    r"|(?:卷首语|序言|编者按|会议通知|消息|简讯)$",
    re.I,
)
FRONT_MATTER_TYPE = {
    "卷首语", "序言", "前言", "编者按", "编者的话", "主编寄语", "发刊词",
    "目录", "封面", "封底", "征稿", "启事", "稿约", "会议通知", "消息", "简讯",
}
PLACEHOLDER_ABSTRACT = {
    "无", "暂无", "暂无摘要", "无摘要", "没有摘要", "摘要", "abstract",
    "n/a", "na", "none", "null", "undefined", "-",
}


class SourceUnavailable(Exception):
    pass


def clean(value):
    if value is None:
        return ""
    text = str(value)
    text = BLOCK_TAG.sub(" ", text)
    text = ANY_TAG.sub("", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    return " ".join(text.split())


def normalize_doi(value):
    doi = clean(value)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = doi.strip().rstrip(".,;")
    if not doi or not doi.lower().startswith("10.") or "/" not in doi:
        return None
    return doi[:255]


def is_front_matter(record, title):
    article_type = clean(record.get("articleTypeStr"))
    if article_type and article_type in FRONT_MATTER_TYPE:
        return True
    return bool(FRONT_MATTER_TITLE.search(title))


def author_names(record):
    names = []
    authors = record.get("pAuthorList")
    if isinstance(authors, dict):
        authors = [authors]
    for author in authors if isinstance(authors, list) else []:
        if isinstance(author, dict):
            name = clean(author.get("fullName"))
            if not name:
                surname = clean(author.get("surName")) or clean(author.get("surname"))
                given = clean(author.get("givenName")) or clean(author.get("givenname"))
                if surname and given:
                    name = f"{surname}{given}" if not surname.isascii() else f"{surname} {given}"
                else:
                    name = surname or given
        else:
            name = clean(author)
        if name and name not in names:
            names.append(name)
    if not names:
        for key in ("authorStr", "orderauthors", "cnAuthors", "enAuthors"):
            text = clean(record.get(key))
            if text:
                names.append(text)
                break
    return ", ".join(names)[:2000] or None


def abstract_text(record):
    value = record.get("intro")
    if value is None:
        value = record.get("introStr")
    if value is None:
        value = record.get("abstract")
    if not isinstance(value, str):
        return None
    text = clean(value)
    text = re.sub(r"^(?:摘\s*要|Abstract)\s*[:：]?\s*", "", text, flags=re.I)
    if not text or text.strip(" .。:：;；").casefold() in PLACEHOLDER_ABSTRACT:
        return None
    return text[:MAX_ABSTRACT]


def pages_text(record):
    first = clean(record.get("spage"))
    last = clean(record.get("epage"))
    if first and last:
        return (first if first == last else f"{first}-{last}")[:128]
    if first or last:
        return (first or last)[:128]
    return clean(record.get("elocationid"))[:128] or None


def year_value(record):
    match = re.search(r"(?:19|20)\d{2}", clean(record.get("pubYear")))
    return int(match.group(0)) if match else None


def pdf_url(record):
    path = clean(record.get("pdfPath"))
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return "https://www.sciengine.com" + path


def article_record(record, journal):
    title = clean(record.get("title"))[:1000]
    if not title or is_front_matter(record, title):
        return None
    doi = normalize_doi(record.get("doi"))
    if not doi:
        return None
    external_id = doi if len(doi) <= 128 else hashlib.sha1(doi.encode("utf-8")).hexdigest()
    return {
        "journal_key": journal["journal_key"],
        "journal_name": journal["name"][:255],
        "journal_url": journal["url"],
        "external_id": external_id,
        "title": title,
        "url": "https://www.sciengine.com/doi/" + quote(doi, safe="/()[]:;._-~"),
        "authors": author_names(record),
        "abstract": abstract_text(record),
        "doi": doi,
        "year": year_value(record),
        "issue": clean(record.get("issueCode"))[:64] or None,
        "volume": clean(record.get("volumeCode"))[:64] or None,
        "pages": pages_text(record),
        "source_api": SOURCE_API,
        "pdf_url": pdf_url(record),
    }


def parse_articles(payload, journal):
    if not isinstance(payload, dict):
        raise ValueError("API payload is not an object")
    if payload.get("success") is False:
        message = clean(payload.get("message")) or "success=false"
        raise ValueError(f"API returned success=false: {message}")
    groups = payload.get("data")
    if not isinstance(groups, list):
        raise ValueError("API payload has no data array")
    items, seen = [], set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for record in group.get("content") or []:
            if not isinstance(record, dict):
                continue
            item = article_record(record, journal)
            if not item or item["external_id"] in seen:
                continue
            seen.add(item["external_id"])
            items.append(item)
    return items


def fetch_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise SourceUnavailable("response exceeds 8 MB")
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        raise SourceUnavailable(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise SourceUnavailable(f"{type(exc).__name__}: {exc}") from exc


def collect(request_data, journals=None):
    catalog = journals or JOURNALS
    parameters = request_data.get("parameters") or {}
    mode = str(parameters.get("collect_mode") or "latest_issue").strip().lower()
    if mode != "latest_issue":
        raise ValueError(f"unsupported collect_mode: {mode}")
    raw_keys = parameters.get("journal_keys")
    keys = list(dict.fromkeys(raw_keys if raw_keys is not None else list(catalog)))
    if not keys:
        raise ValueError("journal_keys cannot be empty")
    try:
        limit = int(request_data.get("limit") or 1000)
        per_journal_limit = int(parameters.get("per_journal_limit", 50))
        timeout = int(parameters.get("timeout_seconds", 20))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric parameter: {exc}") from exc
    if limit <= 0:
        raise ValueError("limit must be positive")
    per_journal_limit = max(1, per_journal_limit)
    timeout = max(5, min(timeout, 60))

    warnings = []
    selected = []
    for key in keys:
        journal = catalog.get(key)
        if journal is None:
            warnings.append(f"未知期刊：{key}")
            continue
        selected.append(journal)

    items, seen, successful = [], set(), 0
    for index, journal in enumerate(selected):
        if len(items) >= limit:
            break
        remaining = limit - len(items)
        remaining_journals = len(selected) - index
        journal_limit = min(per_journal_limit, max(1, (remaining + remaining_journals - 1) // remaining_journals))
        try:
            payload = None
            latest_used = False
            latest_warning = None
            if parameters.get("follow_latest", True) and journal.get("latest_issue_api") and journal.get("article_api_template"):
                try:
                    latest = fetch_json(journal["latest_issue_api"], timeout) or {}
                    data = latest.get("data") if isinstance(latest, dict) else None
                    volume = str(data.get("latestVolume") or "").strip() if isinstance(data, dict) else ""
                    code = str(data.get("latestIssue") or "").strip() if isinstance(data, dict) else ""
                    if volume and code and (volume, code) != (str(journal.get("volume") or ""), str(journal.get("issue") or "")):
                        article_api = journal["article_api_template"].format(
                            volume=quote(volume, safe=""), code=quote(code, safe=""))
                        payload = fetch_json(article_api, timeout)
                        latest_used = True
                except Exception as exc:
                    latest_warning = f"{journal['name']}：最新期发现失败，回退固定期：{type(exc).__name__}: {exc}"
            if payload is None:
                payload = fetch_json(journal["json_api"], timeout)
            rows = parse_articles(payload, journal)
            if latest_warning:
                warnings.append(latest_warning)
            if latest_used and not rows:
                payload = fetch_json(journal["json_api"], timeout)
                rows = parse_articles(payload, journal)
                if rows:
                    warnings.append(f"{journal['name']}：最新期无有效文章，回退固定期")
        except Exception as exc:
            warnings.append(f"{journal['name']}：{type(exc).__name__}: {exc}")
            continue
        successful += 1
        if not rows:
            warnings.append(f"{journal['name']}：当期未解析到有效文章")
            continue
        added = 0
        for item in rows:
            identity = (journal["journal_key"], item["external_id"])
            if identity in seen:
                continue
            seen.add(identity)
            items.append(item)
            added += 1
            if added >= journal_limit or len(items) >= limit:
                break
    return items, warnings, successful


def write_output(output, execution_id, items, status, warnings, error=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    result = {
        "protocol_version": "1.0",
        "execution_id": execution_id,
        "status": status,
        "item_count": len(items),
        "next_cursor": None,
        "has_more": False,
        "warnings": warnings,
        "error": error,
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
        items, warnings, successful = collect(request_data)
        if not successful:
            write_output(output, request_data.get("execution_id", ""), [], "failed", warnings, {
                "code": "ALL_JOURNALS_FAILED",
                "message": "所有已选择期刊均未成功响应",
                "retryable": True,
            })
            return 1
        status = "partial" if warnings else "completed"
        write_output(output, request_data["execution_id"], items, status, warnings)
        return 0
    except Exception as exc:
        write_output(output, request_data.get("execution_id", ""), [], "failed", [], {
            "code": "PACKAGE_ERROR",
            "message": f"{type(exc).__name__}: {exc}",
            "retryable": False,
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
