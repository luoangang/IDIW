from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, build_opener


@dataclass(frozen=True)
class Journal:
    key: str
    name: str
    base_url: str
    home_path: str
    journal_id: str = "1"


JOURNALS = {
    "data_analysis": Journal(
        "data_analysis", "数据分析与知识发现",
        "https://manu44.magtech.com.cn/Jwk_infotech_wk3", "/CN/home",
    ),
    "lis": Journal(
        "lis", "图书情报工作",
        "https://www.lis.ac.cn", "/CN/0252-3116/home.shtml",
    ),
    "qbzl": Journal(
        "qbzl", "情报资料工作",
        "http://qbzl.ruc.edu.cn", "/CN/1002-0314/home.shtml",
    ),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html_lib.unescape(value).replace("\xa0", " ")).strip()


def safe_term(value: str) -> str:
    value = re.sub(r"[\[\](){}\r\n\x00-\x1f]", " ", value or "")
    return re.sub(r"\s+", " ", value).strip()[:200]


def search_sql(term: str, journal_id: str, page: int) -> str:
    fields = ["Title", "Abstract", "Keyword", "Author", "AuthorCompany", "DOI"]
    expression = f"{term}[{fields[0]}]"
    for field in fields[1:]:
        expression = f"({expression}) OR {term}[{field}]"
    base = f"({expression}) AND {journal_id}[Journal]"
    return base if page == 1 else f"({base} AND {page}[Pager])"


def decode_response(response) -> str:
    charset = response.headers.get_content_charset() or "utf-8"
    return response.read().decode(charset, errors="replace")


def post_search(opener, journal: Journal, term: str, page: int) -> str:
    url = f"{journal.base_url}/CN/article/advancedSearchResult.do"
    payload = urlencode({"searchSQL": search_sql(term, journal.journal_id, page), "ajax": "true"}).encode()
    request = Request(
        url, data=payload,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": urljoin(journal.base_url, journal.home_path)},
    )
    with opener.open(request, timeout=25) as response:
        return decode_response(response)


def parse_bibliography(block: str):
    match = re.search(r'class=["\']j-volumn["\'][^>]*>(.*?)</span>', block, re.I | re.S)
    text = clean_html(match.group(1)) if match else ""
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else None
    detail = re.search(
        r"\b(?:19\d{2}|20\d{2})\s*[,，]\s*([^\s,(，]+)\s*[（(]\s*([^）)]+?)\s*[）)]\s*[:：]\s*(\d+(?:\s*[-–—]\s*\d+)?)",
        text,
    )
    if not detail:
        return year, None, None, None
    return year, detail.group(1).strip(), detail.group(2).strip(), re.sub(r"\s*[-–—]\s*", "-", detail.group(3))


def parse_items(document: str, journal: Journal) -> list[dict]:
    segments = re.split(r'<li\s+id=["\']art(\d+)["\']\s+class=["\']noselectrow["\']', document, flags=re.I)
    records = []
    for index in range(1, len(segments) - 1, 2):
        article_id, block = segments[index].strip(), segments[index + 1]
        title_area = re.search(r'<div[^>]+class=["\'][^"\']*j-title[^"\']*["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        area = title_area.group(1) if title_area else block
        link = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', area, re.I | re.S)
        if not link:
            continue
        title = clean_html(link.group(2))
        if not title:
            continue
        url = urljoin(journal.base_url + "/", html_lib.unescape(link.group(1)).strip())
        doi_match = re.search(r'(?:doi\.org/|/CN/)(10\.\d{4,9}/[^"\'<>\s]+)', block, re.I)
        doi = html_lib.unescape(doi_match.group(1)).rstrip(".,;，；") if doi_match else None
        author_match = re.search(r'class=["\']j-author["\'][^>]*>\s*(.*?)\s*</div>', block, re.I | re.S)
        author_text = clean_html(author_match.group(1)) if author_match else ""
        authors = [part.strip() for part in re.split(r"[,，;；、]+", author_text) if part.strip()]
        abstract_match = re.search(r'class=["\']j-abstract["\'][^>]*>\s*(.*?)\s*</div>', block, re.I | re.S)
        abstract = clean_html(abstract_match.group(1)) if abstract_match else None
        year, volume, issue, pages = parse_bibliography(block)
        pdf_match = re.search(r"lsdy1\('PDF','(\d+)'", block)
        pdf_url = (
            f"{journal.base_url}/CN/article/downloadArticleFile.do?attachType=PDF&id={pdf_match.group(1)}"
            if pdf_match else (f"{journal.base_url}/CN/PDF/{doi}" if doi else None)
        )
        records.append({
            "journal_key": journal.key,
            "journal_name": journal.name,
            "external_id": article_id,
            "title": title,
            "url": url,
            "authors": authors,
            "abstract": abstract or None,
            "doi": doi,
            "year": year,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "pdf_url": pdf_url,
            "source_site": "magetech",
        })
    return records


def year_bounds(request_data: dict):
    time_range = request_data.get("time_range") or {}
    values = []
    for key in ("from", "to"):
        value = time_range.get(key)
        match = re.match(r"(19\d{2}|20\d{2})", value or "")
        values.append(int(match.group(1)) if match else None)
    return values[0], values[1]


def write_output(output: Path, execution_id: str, items: list[dict], status: str, warnings: list, error=None):
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


def collect(request_data: dict):
    parameters = request_data.get("parameters") or {}
    selected = parameters.get("journal_keys") or list(JOURNALS)
    max_pages = int(parameters.get("max_pages_per_journal", 20))
    delay = int(parameters.get("request_delay_ms", 300)) / 1000
    limit = int(request_data["limit"])
    terms = [safe_term(request_data["query"])]
    terms.extend(safe_term(value) for value in request_data.get("aliases", []))
    terms = list(dict.fromkeys(term for term in terms if term))
    from_year, to_year = year_bounds(request_data)
    deadline = datetime.fromisoformat(request_data["deadline_at"].replace("Z", "+00:00"))
    opener = build_opener()
    selected_journals = [JOURNALS[key] for key in selected if key in JOURNALS]
    unknown_journals = [key for key in selected if key not in JOURNALS]
    records, warnings, seen = [], [], set()
    for key in unknown_journals:
        warnings.append({"code": "UNKNOWN_JOURNAL", "message": f"忽略未知期刊：{key}"})
    successful_journals = 0

    journal_count = len(selected_journals)
    for journal_index, journal in enumerate(selected_journals):
        journal_limit = limit // journal_count + int(journal_index < limit % journal_count)
        if journal_limit == 0:
            continue
        journal_start_count = len(records)
        journal_succeeded = False
        for term in terms:
            for page in range(1, max_pages + 1):
                if datetime.now(timezone.utc) >= deadline:
                    warnings.append({"code": "DEADLINE_REACHED", "message": "到达任务截止时间，已返回当前结果"})
                    return records, warnings, successful_journals
                try:
                    document = post_search(opener, journal, term, page)
                    page_items = parse_items(document, journal)
                    journal_succeeded = True
                except Exception as exc:
                    warnings.append({
                        "code": "JOURNAL_REQUEST_FAILED",
                        "message": f"{journal.name} 第 {page} 页请求失败：{type(exc).__name__}: {exc}",
                    })
                    break
                added = 0
                for item in page_items:
                    if from_year and item["year"] and item["year"] < from_year:
                        continue
                    if to_year and item["year"] and item["year"] > to_year:
                        continue
                    identity = (item["journal_key"], item["external_id"])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    records.append(item)
                    added += 1
                    if len(records) - journal_start_count >= journal_limit:
                        break
                if len(records) - journal_start_count >= journal_limit:
                    break
                if not page_items or added == 0:
                    break
                if delay:
                    time.sleep(delay)
            if len(records) - journal_start_count >= journal_limit:
                break
        successful_journals += int(journal_succeeded)
    return records, warnings, successful_journals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    request_data = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(args.output)
    try:
        items, warnings, successes = collect(request_data)
        if successes == 0:
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
