#!/usr/bin/env python
"""Export all foreign-Q1 bulk-run articles to CSV + a self-contained HTML browser.

Reads monitor runs through PlatformStore.run() (read-only, no DB writes), follows
each package execution_id to output/items.jsonl, joins journal metadata from
crawler_packages/academic/foreign_q1_journals/journals.json, deduplicates by DOI
(case / https://doi.org/ / doi: prefix normalized), keeps the most complete
record per DOI, and writes:

    <prefix>_items.csv      all articles, utf-8-sig, full abstracts
    <prefix>_abstracts.csv  only articles with a non-empty abstract
    <prefix>_items.html     single-file browser, 50 rows/page, client-side search

Existing output files are never overwritten.

Examples:
    .venv/Scripts/python.exe scripts/export_foreign_q1_full_items.py \
        --runs 28 --date 2026-11-25 --prefix foreign_q1_items_preview_2026-11-25

    .venv/Scripts/python.exe scripts/export_foreign_q1_full_items.py \
        --runs 29,30,31,32,33,34,35,36,37,38,39 --date 2026-11-26 \
        --prefix foreign_q1_full_2026-11-26
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import html
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from crawler_platform.config import SETTINGS
    from crawler_platform.storage import PlatformStore
except ModuleNotFoundError as exc:  # pragma: no cover - friendly runtime hint
    if exc.name == "pymysql":
        raise SystemExit(
            "pymysql is missing in this interpreter. Run with the project venv:\n"
            "  .venv/Scripts/python.exe scripts/export_foreign_q1_full_items.py ..."
        ) from exc
    raise

PACKAGE_KEY = "foreign_q1_journals"
JOURNALS_PATH = ROOT / "crawler_packages" / "academic" / PACKAGE_KEY / "journals.json"

FIELDS = [
    "journal_key",
    "journal_name",
    "edition",
    "frequency_class",
    "publication_frequency",
    "primary_category",
    "title",
    "abstract",
    "authors",
    "doi",
    "url",
    "published_at",
    "year",
    "volume",
    "issue",
    "pages",
    "pdf_url",
    "source_api",
    "openalex_id",
]

USABLE_RUN_STATUSES = {"completed", "partial"}

EDITION_LABELS = {"?": "未知（?）", "": "未知"}
FREQUENCY_LABELS = {
    "weekly": "周刊",
    "semimonthly": "半月刊",
    "monthly": "月刊",
    "10ish": "约10期/年",
    "bimonthly": "双月刊",
    "5/year": "5期/年",
    "quarterly": "季刊",
    "triannual": "三刊/年",
    "semiannual": "半年刊",
    "annual": "年刊",
    "unknown": "未知",
}
FREQUENCY_ORDER = [
    "weekly",
    "semimonthly",
    "monthly",
    "10ish",
    "bimonthly",
    "5/year",
    "quarterly",
    "triannual",
    "semiannual",
    "annual",
    "unknown",
]
EDITION_ORDER = ["SCIE", "SSCI", "ESCI", "AHCI", "?"]


class ExportError(RuntimeError):
    pass


def setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(part for part in (text_value(item) for item in value) if part)
    if isinstance(value, dict):
        for key in ("display_name", "name", "title", "value"):
            if value.get(key):
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def format_authors(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(part for part in (text_value(item) for item in value) if part)
    return text_value(value)


_DOI_PREFIX = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)
_DOI_LABEL = re.compile(r"^doi:\s*", re.IGNORECASE)


def clean_doi(value: Any) -> str:
    """Strip URL / 'doi:' prefixes but keep the DOI's original character case."""
    doi = text_value(value)
    for _ in range(4):
        stripped = _DOI_LABEL.sub("", _DOI_PREFIX.sub("", doi)).strip()
        if stripped == doi:
            break
        doi = stripped
    return doi


def normalize_doi(value: Any) -> str:
    return clean_doi(value).lower()


def load_journal_metadata(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise ExportError(f"journal catalog not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise ExportError(f"unexpected journals.json shape: {type(raw).__name__}")
    metadata: dict[str, dict[str, str]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = text_value(entry.get("journal_key"))
        if not key or key in metadata:
            continue
        metadata[key] = {
            "journal_name": text_value(entry.get("name")) or text_value(entry.get("name_en")),
            "edition": text_value(entry.get("edition")) or "?",
            "frequency_class": text_value(entry.get("frequency_class")) or "unknown",
            "publication_frequency": text_value(entry.get("publication_frequency")),
            "primary_category": text_value(entry.get("primary_category")),
        }
    return metadata


def parse_runs(values: list[str]) -> list[int]:
    run_ids: list[int] = []
    for chunk in values:
        for part in re.split(r"[,;\s]+", chunk):
            if not part:
                continue
            try:
                run_id = int(part)
            except ValueError as exc:
                raise ExportError(f"invalid run id: {part!r}") from exc
            if run_id < 1:
                raise ExportError(f"invalid run id: {run_id}")
            if run_id not in run_ids:
                run_ids.append(run_id)
    if not run_ids:
        raise ExportError("at least one --runs value is required")
    return run_ids


def resolve_output_paths(out_dir: Path, prefix: str) -> tuple[Path, Path, Path]:
    return (
        out_dir / f"{prefix}_items.csv",
        out_dir / f"{prefix}_abstracts.csv",
        out_dir / f"{prefix}_items.html",
    )


def fail_if_outputs_exist(paths: tuple[Path, ...]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise ExportError(
            "refusing to overwrite existing output(s):\n  " + "\n  ".join(existing)
        )


def package_run_for(run: dict[str, Any], run_id: int) -> dict[str, Any]:
    rows = [p for p in run.get("packages", []) if p.get("package_key") == PACKAGE_KEY]
    if not rows:
        raise ExportError(f"run {run_id} has no {PACKAGE_KEY} package execution")
    # Latest attempt wins if a run contains retries/continuations.
    return max(rows, key=lambda item: int(item.get("id") or 0))


def read_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ExportError(f"items.jsonl not found: {path}")
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ExportError(f"bad JSON at {path}:{line_no}: {exc}") from exc
            if isinstance(item, dict):
                items.append(item)
    return items


def build_row(item: dict[str, Any], metadata: dict[str, dict[str, str]]) -> dict[str, str]:
    journal_key = text_value(item.get("journal_key"))
    meta = metadata.get(journal_key, {})
    abstract = text_value(item.get("abstract") or item.get("summary"))
    return {
        "journal_key": journal_key,
        "journal_name": text_value(item.get("journal_name")) or meta.get("journal_name", ""),
        "edition": meta.get("edition") or "?",
        "frequency_class": meta.get("frequency_class") or "unknown",
        "publication_frequency": meta.get("publication_frequency", ""),
        "primary_category": meta.get("primary_category", ""),
        "title": text_value(item.get("title")),
        "abstract": abstract,
        "authors": format_authors(item.get("authors") or item.get("author")),
        "doi": clean_doi(item.get("doi")),
        "url": text_value(item.get("url") or item.get("article_url")),
        "published_at": text_value(item.get("published_at")),
        "year": text_value(item.get("year")),
        "volume": text_value(item.get("volume")),
        "issue": text_value(item.get("issue")),
        "pages": text_value(item.get("pages")),
        "pdf_url": text_value(item.get("pdf_url")),
        "source_api": text_value(item.get("source_api")),
        "openalex_id": text_value(item.get("openalex_id")),
    }


def completeness(row: dict[str, str]) -> tuple[int, int, int, int, str]:
    non_empty = sum(1 for field in FIELDS if row.get(field))
    return (
        non_empty,
        len(row.get("abstract", "")),
        len(row.get("title", "")),
        len(row.get("authors", "")),
        row.get("published_at", ""),
    )


def dedupe_by_doi(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    best: dict[str, tuple[dict[str, str], tuple]] = {}
    without_doi: list[dict[str, str]] = []
    collapsed = 0
    for row in rows:
        key = normalize_doi(row.get("doi"))
        if not key:
            without_doi.append(row)
            continue
        score = completeness(row)
        previous = best.get(key)
        if previous is None:
            best[key] = (row, score)
            continue
        collapsed += 1
        if score > previous[1]:
            best[key] = (row, score)
    deduped = [item[0] for item in best.values()] + without_doi
    return deduped, collapsed, len(without_doi)


def sort_rows(rows: list[dict[str, str]]) -> None:
    rows.sort(key=lambda row: (row["title"].casefold(), row["doi"].casefold()))
    rows.sort(key=lambda row: row["published_at"], reverse=True)
    rows.sort(key=lambda row: (row["journal_name"].casefold(), row["journal_key"]))


def write_csv_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    if path.exists():
        raise ExportError(f"refusing to overwrite existing output: {path}")
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        if path.exists():
            raise ExportError(f"refusing to overwrite existing output: {path}")
        tmp.rename(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str) -> None:
    if path.exists():
        raise ExportError(f"refusing to overwrite existing output: {path}")
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        if path.exists():
            raise ExportError(f"refusing to overwrite existing output: {path}")
        tmp.rename(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def ordered_values(counts: Counter[str], preferred: list[str]) -> list[str]:
    values = [value for value in preferred if counts.get(value)]
    values.extend(sorted(value for value in counts if value not in values))
    return values


def build_filter_options(
    rows: list[dict[str, str]],
    field: str,
    order: list[str],
    labels: dict[str, str],
    fallback: str,
) -> str:
    counts = Counter(row[field] or fallback for row in rows)
    options: list[str] = []
    for value in ordered_values(counts, order):
        label = labels.get(value, value)
        if value == "?":
            label = "未知（?）"
        options.append(
            f'<option value="{html.escape(value)}">'
            f"{html.escape(label)}（{counts[value]:,}）</option>"
        )
    return "".join(options)


HTML_HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4f6f7;color:#17212b;font-family:"Microsoft YaHei","PingFang SC",system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1560px;margin:0 auto;padding:24px 22px 42px}
.pagehead{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap}
h1{font-size:23px;margin:0 0 7px;line-height:1.35}
.muted{color:#74808b;font-size:12px;line-height:1.7}
.downloads{display:flex;gap:8px;flex-wrap:wrap}
.downloads a{display:inline-block;background:#fff;border:1px solid #c9d2d9;border-radius:5px;padding:7px 11px;font-size:12px;color:#176b5b;text-decoration:none;white-space:nowrap}
.downloads a:hover{background:#eef6f3}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px;margin:15px 0 4px}
.card{background:#fff;border:1px solid #dce2e5;border-radius:6px;padding:11px 13px;font-size:12px;color:#536170}
.card span{display:block}
.card b{display:block;font-size:21px;color:#17212b;margin:4px 0 1px;font-variant-numeric:tabular-nums}
.card em{font-style:normal;color:#8a949d;font-size:11px}
.notice{margin:12px 0 0;padding:10px 13px;border-radius:5px;border:1px solid #d9e2e8;background:#fff;color:#46535f;font-size:12px;line-height:1.7}
.notice.warn{border-color:#e7c98c;background:#fff8e8;color:#6b5116}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:15px 0 11px}
.toolbar input{width:min(430px,100%);min-height:36px;border:1px solid #b8c2cc;border-radius:5px;padding:7px 10px;font-size:13px;background:#fff;color:#17212b}
.toolbar select{min-height:36px;border:1px solid #b8c2cc;border-radius:5px;padding:6px 9px;font-size:12px;background:#fff;color:#17212b;max-width:250px}
#count{font-variant-numeric:tabular-nums}
.tablewrap{overflow:auto;max-height:calc(100vh - 268px);border:1px solid #d4dbe2;border-radius:6px;background:#fff}
table{width:100%;min-width:1180px;border-collapse:collapse;table-layout:fixed}
th,td{padding:8px 10px;border-bottom:1px solid #e3e8ec;text-align:left;font-size:12px;vertical-align:top}
th{background:#e9edf1;position:sticky;top:0;z-index:2;font-weight:600;color:#33424f}
th:nth-child(1){width:205px}
th:nth-child(2){width:28%}
th:nth-child(3){width:150px}
th:nth-child(4){width:88px}
th:nth-child(5){width:155px}
tbody tr:hover{background:#f8fafb}
.jname{font-weight:600;color:#283844;overflow-wrap:anywhere}
.jmeta{color:#7c8893;font-size:11px;line-height:1.5;margin-top:2px}
.titlecell{overflow-wrap:anywhere}
.titlelink{display:inline;border:0;background:none;padding:0;margin:0;color:#176b5b;font:inherit;text-align:left;cursor:pointer;line-height:1.65}
.titlelink:hover{text-decoration:underline}
td.doi{color:#4b5b68;overflow-wrap:anywhere;line-height:1.6}
td.doi a{color:#365d7d;text-decoration:none}
td.doi a:hover{text-decoration:underline}
td.abstract{color:#435160;line-height:1.7;overflow-wrap:anywhere}
.pill{display:inline-block;padding:1px 6px;border-radius:9px;font-size:10px;font-weight:700;background:#dff3e9;color:#096443;vertical-align:1px}
.pill.no{background:#eef1f3;color:#5f6c77}
.empty{padding:26px;text-align:center}
.pagination{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:11px;font-size:12px;color:#5e6b77}
.pagination button{min-height:31px;border:1px solid #b8c2cc;background:#fff;color:#365d7d;border-radius:4px;padding:4px 11px;cursor:pointer;font-size:12px}
.pagination button:disabled{color:#b3bcc4;cursor:default}
.pagination button:not(:disabled):hover{background:#eef6f3}
dialog{width:900px;max-width:calc(100vw - 28px);max-height:88vh;overflow:auto;border:1px solid #aebac3;border-radius:7px;padding:0;color:#17212b;background:#fff;box-shadow:0 18px 50px rgba(23,33,43,.25)}
dialog::backdrop{background:rgba(23,33,43,.48)}
.modal-inner{padding:20px 22px 24px}
.dhead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}
.dhead .muted{font-size:11px;letter-spacing:.08em}
.dclose{border:1px solid #b8c2cc;background:#fff;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:12px;color:#365d7d}
.dclose:hover{background:#eef6f3}
#dTitle{font-size:18px;line-height:1.55;margin:0 0 9px;overflow-wrap:anywhere}
.modal-meta{font-size:12px;color:#5f6d78;line-height:1.8;overflow-wrap:anywhere}
.modal-extra{font-size:11px;color:#8a949d;line-height:1.7;margin:2px 0 12px;overflow-wrap:anywhere}
.modal-abstract{white-space:pre-wrap;line-height:1.9;font-size:13px;background:#f7f9fa;border:1px solid #e1e6eb;border-radius:5px;padding:14px;max-height:48vh;overflow:auto;overflow-wrap:anywhere}
.modal-links{margin:13px 0 0;font-size:12px;line-height:1.9;overflow-wrap:anywhere}
.modal-links a{color:#176b5b}
footer{margin-top:18px;font-size:11px;color:#8a949d;line-height:1.8}
@media (max-width:760px){
  main{padding:16px 12px 30px}
  .tablewrap{max-height:none}
  h1{font-size:19px}
}
</style>
</head>
<body>
<main>
<header class="pagehead">
  <div>
    <h1>国外 Q1 文章浏览器 · @@DATE@@</h1>
    <div class="muted">@@SUMMARY@@</div>
  </div>
  <div class="downloads">
    <a href="@@ITEMS_CSV@@">全部文章 CSV</a>
    <a href="@@ABSTRACTS_CSV@@">仅有摘要 CSV</a>
  </div>
</header>
<div class="cards">@@CARDS@@</div>
@@NOTICE@@
<section class="toolbar">
  <input id="q" type="search" placeholder="搜索标题 / 摘要 / 期刊 / 作者 / DOI" autocomplete="off" spellcheck="false">
  <select id="edition" aria-label="按 edition 筛选"><option value="">全部 edition</option>@@EDITION_OPTIONS@@</select>
  <select id="freq" aria-label="按出版频次筛选"><option value="">全部频次</option>@@FREQ_OPTIONS@@</select>
  <span id="count" class="muted"></span>
</section>
<div class="tablewrap">
  <table>
    <thead><tr><th>期刊</th><th>标题</th><th>作者</th><th>发表</th><th>DOI</th><th>摘要</th></tr></thead>
    <tbody id="rows"><tr><td colspan="6" class="muted empty">正在加载文章数据…</td></tr></tbody>
  </table>
</div>
<div class="pagination">
  <span id="pageInfo"></span>
  <button id="prev" type="button">上一页</button>
  <button id="next" type="button">下一页</button>
</div>
<dialog id="detail">
  <div class="modal-inner">
    <div class="dhead"><span class="muted">文章详情</span><button class="dclose" id="close" type="button">关闭</button></div>
    <h2 id="dTitle"></h2>
    <div class="modal-meta" id="dMeta"></div>
    <div class="modal-meta" id="dPub"></div>
    <div class="modal-extra" id="dExtra"></div>
    <div class="modal-abstract" id="dAbs"></div>
    <p class="modal-links" id="dLinks"></p>
  </div>
</dialog>
<footer>
  由 <code>scripts/export_foreign_q1_full_items.py</code> 生成 · 数据源：本机 crawler_platform 只读 runs @@RUNS@@ · 未写入数据库 ·
  单文件 HTML，无 CDN / 外部字体 / 外部脚本 · CSV 编码 UTF-8-SIG
</footer>
"""

HTML_JS = r"""
(function () {
  'use strict';
  var payloadEl = document.getElementById('payload');
  var DATA = JSON.parse(payloadEl.textContent);
  payloadEl.remove();
  var J = DATA.journals || [];
  var R = DATA.rows || [];
  var LABELS = DATA.labels || {};
  var ED_LABELS = LABELS.edition || {};
  var FREQ_LABELS = LABELS.freq || {};
  var PAGE_SIZE = 50;
  var filtered = [];
  var page = 1;
  var searchIndex = new Array(R.length);
  var timer = null;

  function $(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }
  function safeUrl(value) {
    var url = String(value == null ? '' : value).trim();
    return /^https?:\/\//i.test(url) ? url : '';
  }
  function doiUrl(doi) {
    doi = String(doi == null ? '' : doi).trim();
    if (!doi) return '';
    return 'https://doi.org/' + doi.split('/').map(encodeURIComponent).join('/');
  }
  function jour(row) {
    return J[row[0]] || ['', '未知期刊', '?', 'unknown', '', ''];
  }
  function edLabel(value) { return ED_LABELS[value] || value || '未知'; }
  function freqLabel(value) { return FREQ_LABELS[value] || value || '未知'; }
  function haystack(index) {
    var cached = searchIndex[index];
    if (cached !== undefined) return cached;
    var row = R[index];
    var j = jour(row);
    cached = [row[1], row[2], j[1], row[3], row[4]].join('\n').toLowerCase();
    searchIndex[index] = cached;
    return cached;
  }
  function abstractPreview(value) {
    return String(value == null ? '' : value).replace(/\s+/g, ' ').slice(0, 220);
  }

  function applyFilters() {
    var query = $('q').value.trim().toLowerCase();
    var edition = $('edition').value;
    var freq = $('freq').value;
    var next = [];
    for (var i = 0; i < R.length; i += 1) {
      var row = R[i];
      var j = jour(row);
      if (edition && (j[2] || '?') !== edition) continue;
      if (freq && (j[3] || 'unknown') !== freq) continue;
      if (query && haystack(i).indexOf(query) === -1) continue;
      next.push(i);
    }
    filtered = next;
    page = 1;
    render();
  }

  function render() {
    var pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    if (page > pages) page = pages;
    if (page < 1) page = 1;
    var start = (page - 1) * PAGE_SIZE;
    var slice = filtered.slice(start, start + PAGE_SIZE);
    var html = slice.map(function (index) {
      var row = R[index];
      var j = jour(row);
      var doi = row[4] || '';
      var doiHtml = doi
        ? '<a href="' + esc(doiUrl(doi)) + '" target="_blank" rel="noopener noreferrer">' + esc(doi) + '</a>'
        : '';
      var abstract = row[2] || '';
      var preview = abstractPreview(abstract);
      var pill = abstract.trim()
        ? '<span class="pill">有</span>'
        : '<span class="pill no">无</span>';
      var journalMeta = edLabel(j[2]) + ' · ' + freqLabel(j[3]);
      return '<tr>' +
        '<td><div class="jname">' + esc(j[1] || '未知期刊') + '</div><div class="jmeta">' + esc(journalMeta) + '</div></td>' +
        '<td class="titlecell"><button type="button" class="titlelink" data-i="' + index + '">' + esc(row[1] || '（无标题）') + '</button></td>' +
        '<td>' + esc(row[3] || '') + '</td>' +
        '<td>' + esc(row[6] || row[7] || '') + '</td>' +
        '<td class="doi">' + doiHtml + '</td>' +
        '<td class="abstract">' + pill + ' ' + esc(preview) + (abstract.length > 220 ? '…' : '') + '</td>' +
        '</tr>';
    }).join('');
    $('rows').innerHTML = html || '<tr><td colspan="6" class="muted empty">没有匹配文章</td></tr>';
    $('count').textContent = '筛选 ' + filtered.length.toLocaleString() + ' / 共 ' + R.length.toLocaleString() + ' 篇';
    $('pageInfo').textContent = '第 ' + page.toLocaleString() + ' / ' + pages.toLocaleString() + ' 页 · 每页 ' + PAGE_SIZE + ' 条';
    $('prev').disabled = page <= 1;
    $('next').disabled = page >= pages;
  }

  function addLink(container, href, label, previous) {
    var url = safeUrl(href);
    if (!url) return previous;
    if (previous) container.appendChild(document.createTextNode(' · '));
    var link = document.createElement('a');
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = label;
    container.appendChild(link);
    return true;
  }

  function showDetail(row) {
    var j = jour(row);
    $('dTitle').textContent = row[1] || '（无标题）';
    var meta = [
      j[1],
      j[2] ? ('edition ' + j[2]) : '',
      j[3] ? ('频次 ' + freqLabel(j[3]) + (j[4] ? '（' + j[4] + '）' : '')) : '',
      row[3],
      row[6] || row[7]
    ].filter(Boolean);
    $('dMeta').textContent = meta.join(' · ');
    var publication = [
      row[8] ? ('Vol. ' + row[8]) : '',
      row[9] ? ('No. ' + row[9]) : '',
      row[10] ? ('pp. ' + row[10]) : '',
      row[7] && row[7] !== row[6] ? ('年份 ' + row[7]) : ''
    ].filter(Boolean);
    $('dPub').textContent = publication.join(' · ');
    $('dExtra').textContent = [
      row[12] ? ('source_api: ' + row[12]) : '',
      j[5] ? ('学科: ' + j[5]) : '',
      j[0] ? ('journal_key: ' + j[0]) : ''
    ].filter(Boolean).join(' · ');
    $('dAbs').textContent = row[2] || '（本条没有摘要）';
    var container = $('dLinks');
    container.textContent = '';
    var any = false;
    any = addLink(container, row[5], '打开原文', any);
    any = addLink(container, row[11], 'PDF', any);
    any = addLink(container, doiUrl(row[4]), 'DOI 链接', any);
    any = addLink(container, row[13], 'OpenAlex', any);
    if (!any) container.textContent = '（本条没有可用链接）';
    $('detail').showModal();
  }

  $('rows').addEventListener('click', function (event) {
    var button = event.target.closest('button[data-i]');
    if (!button) return;
    var index = Number(button.getAttribute('data-i'));
    if (Number.isInteger(index) && R[index]) showDetail(R[index]);
  });
  $('close').addEventListener('click', function () { $('detail').close(); });
  $('detail').addEventListener('click', function (event) {
    if (event.target === $('detail')) $('detail').close();
  });
  $('prev').addEventListener('click', function () {
    if (page > 1) { page -= 1; render(); }
  });
  $('next').addEventListener('click', function () {
    var pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    if (page < pages) { page += 1; render(); }
  });
  $('q').addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(applyFilters, 150);
  });
  $('edition').addEventListener('change', applyFilters);
  $('freq').addEventListener('change', applyFilters);
  applyFilters();
})();
"""


def build_html(
    rows: list[dict[str, str]],
    run_ids: list[int],
    date_label: str,
    items_csv_name: str,
    abstracts_csv_name: str,
    duplicate_count: int,
    no_doi_count: int,
    run_notes: list[str],
    warnings: list[str],
) -> str:
    journal_index: dict[str, int] = {}
    journals: list[list[str]] = []
    compact_rows: list[list[Any]] = []
    for row in rows:
        group_key = row["journal_key"] or ("name:" + row["journal_name"])
        index = journal_index.get(group_key)
        if index is None:
            index = len(journals)
            journal_index[group_key] = index
            journals.append([
                row["journal_key"],
                row["journal_name"],
                row["edition"],
                row["frequency_class"],
                row["publication_frequency"],
                row["primary_category"],
            ])
        compact_rows.append([
            index,
            row["title"],
            row["abstract"],
            row["authors"],
            row["doi"],
            row["url"],
            row["published_at"],
            row["year"],
            row["volume"],
            row["issue"],
            row["pages"],
            row["pdf_url"],
            row["source_api"],
            row["openalex_id"],
        ])

    total = len(rows)
    journal_count = len(journals)
    abstract_count = sum(1 for row in rows if row["abstract"].strip())
    abstract_pct = (abstract_count * 100.0 / total) if total else 0.0
    run_text = ", ".join(str(run_id) for run_id in run_ids)

    cards = "".join(
        f'<div class="card"><span>{html.escape(label)}</span><b>{value}</b><em>{html.escape(note)}</em></div>'
        for label, value, note in [
            ("文章", f"{total:,}", "DOI 去重后"),
            ("期刊", f"{journal_count:,}", "至少 1 篇文章"),
            ("有摘要", f"{abstract_count:,}", f"{abstract_pct:.1f}%"),
            ("合并重复", f"{duplicate_count:,}", "同一 DOI 保留字段更全一条"),
        ]
    )

    notices: list[str] = []
    if run_notes:
        notices.append(
            '<div class="notice warn"><b>注意：</b>'
            + "；".join(html.escape(note) for note in run_notes)
            + "。本页仅包含可用 runs 的数据。</div>"
        )
    if warnings:
        notices.append(
            '<div class="notice warn"><b>数据提示：</b>'
            + "；".join(html.escape(warning) for warning in warnings)
            + "</div>"
        )
    if no_doi_count:
        notices.append(
            f'<div class="notice">有 {no_doi_count:,} 条记录没有 DOI，未参与 DOI 去重，已保留在结果中。</div>'
        )

    summary = (
        f"runs {run_text} · {total:,} 篇文章 · {journal_count:,} 本期刊 · "
        f"有摘要 {abstract_count:,} 篇（{abstract_pct:.1f}%） · "
        f"同一 DOI 合并 {duplicate_count:,} 条"
    )

    title = f"国外 Q1 文章浏览器 · {date_label}"
    head = (
        HTML_HEAD.replace("@@TITLE@@", html.escape(title))
        .replace("@@DATE@@", html.escape(date_label))
        .replace("@@SUMMARY@@", html.escape(summary))
        .replace("@@ITEMS_CSV@@", html.escape(items_csv_name))
        .replace("@@ABSTRACTS_CSV@@", html.escape(abstracts_csv_name))
        .replace("@@CARDS@@", cards)
        .replace("@@NOTICE@@", "\n".join(notices))
        .replace("@@RUNS@@", html.escape(run_text))
        .replace(
            "@@EDITION_OPTIONS@@",
            build_filter_options(rows, "edition", EDITION_ORDER, EDITION_LABELS, "?"),
        )
        .replace(
            "@@FREQ_OPTIONS@@",
            build_filter_options(rows, "frequency_class", FREQUENCY_ORDER, FREQUENCY_LABELS, "unknown"),
        )
    )

    payload = json.dumps(
        {
            "journals": journals,
            "rows": compact_rows,
            "labels": {"edition": EDITION_LABELS, "freq": FREQUENCY_LABELS},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # Make the inline JSON inert inside <script>: every '<' becomes \u003c so no
    # "</script>" (or "<!--") sequence can terminate or confuse the raw-text element.
    payload = (
        payload.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    return (
        head
        + '\n<script type="application/json" id="payload">'
        + payload
        + "</script>\n<script>"
        + HTML_JS
        + "</script>\n</main>\n</body>\n</html>\n"
    )


def human_size(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / (1024 * 1024):.2f} MB"


def main(argv: list[str] | None = None) -> int:
    setup_stdout()
    parser = argparse.ArgumentParser(
        description="Export foreign Q1 bulk-run articles to CSV and a self-contained HTML browser.",
    )
    parser.add_argument(
        "--runs",
        action="append",
        required=True,
        metavar="IDS",
        help="run ids, comma separated and/or repeated, e.g. --runs 28 or --runs 29,30 --runs 31",
    )
    parser.add_argument(
        "--date",
        default=_dt.date.today().isoformat(),
        metavar="YYYY-MM-DD",
        help="date label used in the HTML title (default: today)",
    )
    parser.add_argument(
        "--out-dir",
        default="journal_catalog/foreign",
        help="output directory (default: journal_catalog/foreign)",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="output filename prefix (default: foreign_q1_full_<date>)",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="skip failed/running/cancelled runs instead of aborting (output then covers usable runs only)",
    )
    args = parser.parse_args(argv)

    try:
        run_ids = parse_runs(args.runs)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise ExportError(f"invalid --date: {args.date!r} (expected YYYY-MM-DD)")
        try:
            _dt.date.fromisoformat(args.date)
        except ValueError as exc:
            raise ExportError(f"invalid --date: {args.date!r}") from exc

        prefix = args.prefix or f"foreign_q1_full_{args.date}"
        if not re.fullmatch(r"[A-Za-z0-9._-]+", prefix):
            raise ExportError("--prefix may only contain letters, digits, dot, underscore and dash")

        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = ROOT / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        items_csv, abstracts_csv, items_html = resolve_output_paths(out_dir, prefix)
        fail_if_outputs_exist((items_csv, abstracts_csv, items_html))

        store = PlatformStore(SETTINGS)
        metadata = load_journal_metadata(JOURNALS_PATH)

        run_notes: list[str] = []
        run_reports: list[dict[str, Any]] = []
        for position, run_id in enumerate(run_ids, 1):
            try:
                run = store.run(run_id)
            except KeyError as exc:
                raise ExportError(f"run {run_id} not found in platform DB") from exc
            package = package_run_for(run, run_id)
            status = str(package.get("status") or "")
            execution_id = str(package.get("execution_id") or "")
            path = SETTINGS.runs_dir / execution_id / "output" / "items.jsonl"
            report = {
                "run_id": run_id,
                "status": status,
                "execution_id": execution_id,
                "fetched": int(package.get("fetched") or 0),
                "path": path,
                "usable": status in USABLE_RUN_STATUSES and path.exists(),
            }
            run_reports.append(report)
            if not report["usable"]:
                reason = status or "unknown"
                if not path.exists():
                    reason += ", items.jsonl missing"
                error_code = str(package.get("error_code") or "")
                if error_code:
                    reason += f", {error_code}"
                run_notes.append(f"run {run_id} 不可用（{reason}）")
                print(f"[{position}/{len(run_ids)}] run {run_id}: SKIP ({reason})")
            else:
                print(
                    f"[{position}/{len(run_ids)}] run {run_id}: {status}, fetched={report['fetched']}, "
                    f"items file={path}"
                )

        if run_notes and not args.allow_incomplete:
            raise ExportError(
                "some requested runs are not usable; rerun after they complete or pass --allow-incomplete:\n  "
                + "\n  ".join(run_notes)
            )

        all_rows: list[dict[str, str]] = []
        warnings: list[str] = []
        missing_metadata = 0
        for report in run_reports:
            if not report["usable"]:
                continue
            items = read_items(report["path"])
            if report["fetched"] and len(items) != report["fetched"]:
                warnings.append(
                    f"run {report['run_id']} 的 items.jsonl 有 {len(items):,} 条，"
                    f"平台记录 fetched={report['fetched']:,}"
                )
            run_rows: list[dict[str, str]] = []
            for item in items:
                row = build_row(item, metadata)
                if row["journal_key"] not in metadata:
                    missing_metadata += 1
                run_rows.append(row)
            all_rows.extend(run_rows)
            abstract_count = sum(1 for row in run_rows if row["abstract"].strip())
            journal_count = len({row["journal_key"] or row["journal_name"] for row in run_rows})
            report["items"] = len(run_rows)
            report["abstracts"] = abstract_count
            report["journals"] = journal_count
            if report["status"] == "partial":
                warnings.append(f"run {report['run_id']} 状态为 partial，部分期刊可能未完成")
            print(
                f"  run {report['run_id']}: items={len(run_rows):,}, journals={journal_count:,}, "
                f"abstracts={abstract_count:,}"
            )

        if not all_rows:
            raise ExportError("no items were read from the requested runs")

        rows, duplicate_count, no_doi_count = dedupe_by_doi(all_rows)
        if duplicate_count:
            warnings.append(f"同一 DOI 合并了 {duplicate_count:,} 条重复记录，保留字段更全的一条")
        if missing_metadata:
            warnings.append(f"{missing_metadata:,} 条记录的 journal_key 不在 journals.json 中，元数据留空")
        sort_rows(rows)

        abstract_rows = [row for row in rows if row["abstract"].strip()]
        with_abstract = len(abstract_rows)
        journal_count = len({row["journal_key"] or row["journal_name"] for row in rows})
        doi_count = sum(1 for row in rows if row["doi"])

        page = build_html(
            rows=rows,
            run_ids=run_ids,
            date_label=args.date,
            items_csv_name=items_csv.name,
            abstracts_csv_name=abstracts_csv.name,
            duplicate_count=duplicate_count,
            no_doi_count=no_doi_count,
            run_notes=run_notes,
            warnings=warnings,
        )

        # Final existence check, immediately before writing.
        fail_if_outputs_exist((items_csv, abstracts_csv, items_html))
        write_csv_atomic(items_csv, rows)
        write_csv_atomic(abstracts_csv, abstract_rows)
        write_text_atomic(items_html, page)

        edition_counts = Counter(row["edition"] for row in rows)
        frequency_counts = Counter(row["frequency_class"] for row in rows)
        print("")
        print(
            f"input rows: {len(all_rows):,} | deduped: {len(rows):,} | "
            f"merged duplicates: {duplicate_count:,} | without DOI: {no_doi_count:,}"
        )
        print(
            f"unique normalised DOIs: {len({normalize_doi(row['doi']) for row in rows if row['doi']}):,} | "
            f"journals: {journal_count:,} | abstracts: {with_abstract:,} "
            f"({with_abstract * 100.0 / len(rows):.1f}%)"
        )
        print("editions:", ", ".join(f"{key}={value:,}" for key, value in edition_counts.most_common()))
        print("frequencies:", ", ".join(f"{key}={value:,}" for key, value in frequency_counts.most_common()))
        print("")
        print(f"CSV   {items_csv}  rows={len(rows):,}  size={human_size(items_csv)}")
        print(f"ABS   {abstracts_csv}  rows={with_abstract:,}  size={human_size(abstracts_csv)}")
        print(f"HTML  {items_html}  rows={len(rows):,}  size={human_size(items_html)}")
        if warnings:
            print("warnings:")
            for warning in warnings:
                print("  -", warning)
        return 0
    except ExportError as exc:
        sys.stdout.flush()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
