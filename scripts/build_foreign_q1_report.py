#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成国外 Q1 期刊可视化报告（自包含 HTML）。

数据快照：2026-11-25
输入：
  journal_catalog/foreign/foreign_journals_q1_2026-11-25.csv
  journal_catalog/foreign/foreign_source_audit_q1_2026-11-25.csv
  journal_catalog/foreign/foreign_{openalex,crossref,pubmed}_audit_q1_2026-11-25.csv（可选，用于汇总率）
输出：
  journal_catalog/foreign/foreign_q1_report_2026-11-25.html

只读输入，不访问网络，不修改平台/包/数据库/任务。
"""

from __future__ import annotations

import csv
import html
import math
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "journal_catalog" / "foreign"

WATCHLIST_CSV = DATA_DIR / "foreign_journals_q1_2026-11-25.csv"
SAMPLE_CSV = DATA_DIR / "foreign_q1_audit_sample_2026-11-25.csv"
MERGED_CSV = DATA_DIR / "foreign_source_audit_q1_2026-11-25.csv"
OPENALEX_AUDIT_CSV = DATA_DIR / "foreign_openalex_audit_q1_2026-11-25.csv"
CROSSREF_AUDIT_CSV = DATA_DIR / "foreign_crossref_audit_q1_2026-11-25.csv"
PUBMED_AUDIT_CSV = DATA_DIR / "foreign_pubmed_audit_q1_2026-11-25.csv"
RSS_AUDIT_CSV = DATA_DIR / "foreign_rss_audit_q1_2026-11-25.csv"
OUT_HTML = DATA_DIR / "foreign_q1_report_2026-11-25.html"

REPORT_DATE = "2026-11-25"

EDITION_ORDER = ["SCIE", "SSCI", "ESCI", "AHCI", "?"]
EDITION_LABEL = {"SCIE": "SCIE", "SSCI": "SSCI", "ESCI": "ESCI", "AHCI": "AHCI", "?": "未标注"}
EDITION_COLOR = {
    "SCIE": "#1d4ed8",
    "SSCI": "#0f766e",
    "ESCI": "#7c3aed",
    "AHCI": "#b45309",
    "?": "#64748b",
}
DECISION_ORDER = [
    "openalex_primary_crossref_fallback",
    "openalex_primary",
    "pubmed_primary",
    "no_recent_items",
]
DECISION_LABEL = {
    "openalex_primary_crossref_fallback": "OA 主源 + CR 兜底",
    "openalex_primary": "OA 主源",
    "pubmed_primary": "PubMed 主源",
    "no_recent_items": "90 天无记录",
}
DECISION_CHIP = {
    "openalex_primary_crossref_fallback": "chip-green",
    "openalex_primary": "chip-blue",
    "pubmed_primary": "chip-purple",
    "no_recent_items": "chip-gray",
}
ABSTRACT_ORDER = [("openalex", "OpenAlex", "#0f766e"), ("pubmed", "PubMed", "#7c3aed"),
                  ("crossref", "Crossref", "#1d4ed8"), ("none", "未获取", "#cbd5e1")]
DOI_ORDER = [("openalex", "OpenAlex", "#0f766e"), ("pubmed", "PubMed", "#7c3aed"),
             ("none", "未获取", "#cbd5e1")]
SOURCE_LABEL = {"openalex": "OpenAlex", "crossref": "Crossref", "pubmed": "PubMed", "none": "—"}


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def to_float(value, default: float = 0.0) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def fmt_int(value: int | float) -> str:
    return f"{int(round(value)):,}"


def pct(part: float, whole: float, digits: int = 1) -> str:
    if not whole:
        return "—"
    return f"{part / whole * 100:.{digits}f}%"


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_size(path: Path) -> str:
    if not path.exists():
        return "缺失"
    size = path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


def edition_chip(edition: str) -> str:
    key = edition if edition in EDITION_LABEL else "?"
    cls = {"SCIE": "ed-scie", "SSCI": "ed-ssci", "ESCI": "ed-esci",
           "AHCI": "ed-ahci", "?": "ed-na"}[key]
    return f'<span class="chip {cls}">{e(EDITION_LABEL[key])}</span>'


def bar_row(label: str, value: float, max_value: float, value_text: str,
            sub_text: str = "", color: str = "#0f766e", scale: str = "linear") -> str:
    ratio = value / max_value if max_value else 0.0
    width = ratio * 100 if scale == "linear" else math.sqrt(ratio) * 100
    if value > 0:
        width = max(width, 1.2)
    width = min(width, 100.0)
    sub_html = f"<span>{e(sub_text)}</span>" if sub_text else ""
    return (
        '<div class="bar-row">'
        f'<div class="bar-label" title="{e(label)}">{e(label)}</div>'
        '<div class="bar-track">'
        f'<span class="bar-fill" style="width:{width:.2f}%;background:{color}"></span>'
        "</div>"
        f'<div class="bar-value"><b>{e(value_text)}</b>{sub_html}</div>'
        "</div>"
    )


def coverage_row(label: str, hit: int, denominator: int, color: str, note: str = "") -> str:
    ratio = hit / denominator if denominator else 0
    note_html = f'<span class="cov-note">{e(note)}</span>' if note else ""
    return (
        '<div class="bar-row cov-row">'
        f'<div class="bar-label"><span class="cov-name">{e(label)}</span>{note_html}</div>'
        '<div class="bar-track cov-track">'
        f'<span class="bar-fill" style="width:{ratio * 100:.2f}%;background:{color}"></span>'
        "</div>"
        f'<div class="bar-value"><b>{hit} / {denominator}</b><span>{pct(hit, denominator)}</span></div>'
        "</div>"
    )


def stacked_bar(segments: list[tuple[str, int, str]], total: int) -> str:
    pieces = []
    for label, count, color in segments:
        if count <= 0:
            continue
        width = count / total * 100 if total else 0
        text = str(count) if width >= 7 else ""
        pieces.append(
            f'<span class="seg" style="width:{width:.3f}%;background:{color}" '
            f'title="{e(label)}：{count} 本">{text}</span>'
        )
    return '<div class="stack">' + "".join(pieces) + "</div>"


def legend(segments: list[tuple[str, int, str]], total: int) -> str:
    items = []
    for label, count, color in segments:
        items.append(
            '<span class="legend-item">'
            f'<i style="background:{color}"></i>{e(label)} '
            f'<b>{count}</b><span class="muted">（{pct(count, total)}）</span>'
            "</span>"
        )
    return '<div class="legend">' + "".join(items) + "</div>"


def source_cell(row: dict, source: str) -> str:
    status = (row.get(f"{source}_status") or "").strip()
    items = to_float(row.get(f"{source}_items_90d"))
    rate = row.get(f"{source}_abstract_rate")

    if source == "pubmed" and not status:
        return '<span class="na">未审计</span>'
    if source == "openalex" and status == "no_source":
        return '<span class="na">无 source</span>'
    if source == "crossref" and status == "no_journal":
        return '<span class="na">无记录</span>'

    if items <= 0:
        return '<span class="num-main zero">0 条</span><span class="num-sub">摘要 —</span>'

    truncated = str(row.get(f"{source}_truncated") or "").strip().lower() in {"yes", "true", "1"}
    dagger = '<sup class="dag" title="单页截断，仅统计最新最多 100 条">†</sup>' if truncated else ""
    rate_text = f"摘要 {to_float(rate):.1f}%" if str(rate).strip() else "摘要 —"
    return (
        f'<span class="num-main">{fmt_int(items)} 条{dagger}</span>'
        f'<span class="num-sub">{e(rate_text)}</span>'
    )


def rss_cell(row: dict) -> str:
    match = (row.get("rss_match") or "miss").strip()
    status = (row.get("rss_status") or "").strip()
    items = to_float(row.get("rss_items_90d"))

    if match == "miss":
        return '<span class="chip chip-gray">miss</span><span class="num-sub">未映射</span>'

    chip_cls = "chip-green" if match == "exact" else "chip-amber"
    status_html = ""
    if status and status != "ok":
        status_cls = "chip-red" if status == "blocked" else "chip-amber"
        status_html = f'<span class="chip {status_cls} mini">{e(status)}</span>'
    signal = '<span class="num-sub">仅信号</span>' if items > 0 and not status_html else ""
    return (
        f'<span class="chip {chip_cls}">{e(match)}</span>'
        f'<span class="num-main">{fmt_int(items)} 条</span>'
        f"{status_html}{signal}"
    )


def source_route(row: dict) -> str:
    primary = (row.get("primary_source") or "none").strip()
    fallback = (row.get("fallback_source") or "").strip()
    primary_html = f'<span class="src">{e(SOURCE_LABEL.get(primary, primary))}</span>'
    if fallback:
        fallback_html = f'<span class="src-fb">{e(SOURCE_LABEL.get(fallback, fallback))}</span>'
        return f'{primary_html}<span class="arrow">→</span>{fallback_html}'
    return primary_html


def decision_chip(row: dict) -> str:
    code = (row.get("decision") or "").strip()
    label = DECISION_LABEL.get(code, code or "—")
    cls = DECISION_CHIP.get(code, "chip-gray")
    return f'<span class="chip {cls}" title="{e(code)}">{e(label)}</span>'


def note_html(row: dict) -> str:
    note = (row.get("notes") or "").strip()
    if not note:
        return '<span class="na">—</span>'
    parts = [e(part) for part in note.split("; ") if part]
    return '<span class="note">' + "<br>".join(parts) + "</span>"


def audit_row(index: int, row: dict) -> str:
    edition = (row.get("edition") or "?").strip() or "?"
    decision = (row.get("decision") or "").strip()
    title = (row.get("title") or "").strip()
    issn = (row.get("issn") or "").strip()
    eissn = (row.get("eissn") or "").strip()
    category = (row.get("primary_category") or "").strip() or "—"
    jif = (row.get("jif") or "").strip()
    jif_text = f"{to_float(jif):.1f}" if jif else "—"
    search_blob = " ".join([
        title, issn, eissn, row.get("publisher") or "", category,
        decision, DECISION_LABEL.get(decision, ""), row.get("notes") or "",
        row.get("rss_status") or "", row.get("primary_source") or "",
    ]).lower()
    issn_text = " · ".join(part for part in [issn, eissn] if part)
    return (
        f'<tr class="audit-row" data-edition="{e(edition)}" data-decision="{e(decision)}" '
        f'data-search="{e(search_blob)}">'
        f'<td class="col-idx">{index}</td>'
        '<td class="col-title">'
        f'<span class="jtitle" title="{e(title)}">{e(title)}</span>'
        f'<span class="jmeta">{e(issn_text or "ISSN —")}</span>'
        "</td>"
        f'<td>{edition_chip(edition)}</td>'
        f'<td class="num">{e(jif_text)}</td>'
        f'<td class="col-cat" title="{e(category)}">{e(category)}</td>'
        f'<td class="col-src">{source_cell(row, "openalex")}</td>'
        f'<td class="col-src">{source_cell(row, "crossref")}</td>'
        f'<td class="col-src">{source_cell(row, "pubmed")}</td>'
        f'<td class="col-rss">{rss_cell(row)}</td>'
        f'<td class="col-route">{source_route(row)}</td>'
        f'<td>{decision_chip(row)}</td>'
        f'<td class="col-note">{note_html(row)}</td>'
        "</tr>"
    )


def aggregate_source(path: Path) -> dict | None:
    if not path.exists():
        return None
    rows = read_csv(path)
    items = sum(to_float(row.get("items_90d")) for row in rows)
    abstracts = sum(to_float(row.get("abstract_items")) for row in rows)
    dois = sum(to_float(row.get("doi_items")) for row in rows)
    return {
        "rows": len(rows),
        "items": int(items),
        "abstracts": int(abstracts),
        "dois": int(dois),
        "abstract_rate": abstracts / items * 100 if items else 0,
        "doi_rate": dois / items * 100 if items else 0,
    }


CSS = """
:root {
  --bg: #f2f6f6;
  --panel: #ffffff;
  --ink: #102a33;
  --muted: #5d7078;
  --line: #dbe5e6;
  --soft: #f6f9f9;
  --teal: #0f5f57;
  --teal-dark: #0a3f3a;
  --amber: #d97706;
  --blue: #1d4ed8;
  --purple: #7c3aed;
  --red: #b91c1c;
  --radius: 14px;
  --shadow: 0 1px 2px rgba(16, 42, 51, .04), 0 8px 24px rgba(16, 42, 51, .05);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(circle at 8% 0%, rgba(15, 95, 87, .07), transparent 28rem),
    radial-gradient(circle at 92% 12%, rgba(29, 78, 216, .05), transparent 30rem),
    var(--bg);
  color: var(--ink);
  font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--teal); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--teal-dark); }
.wrap { max-width: 1340px; margin: 0 auto; padding: 28px 24px 48px; }
.muted { color: var(--muted); }
.num, .bar-value, .kpi-value { font-variant-numeric: tabular-nums; }

.hero {
  position: relative;
  overflow: hidden;
  color: #f5fbfa;
  background: linear-gradient(125deg, #082f2c 0%, #0d4a44 48%, #123f5c 100%);
  border-radius: 20px;
  padding: 34px 36px 30px;
  box-shadow: 0 16px 40px rgba(8, 47, 44, .18);
}
.hero::after {
  content: "";
  position: absolute;
  right: -80px;
  top: -120px;
  width: 380px;
  height: 380px;
  border-radius: 50%;
  border: 44px solid rgba(255, 255, 255, .05);
  pointer-events: none;
}
.eyebrow {
  font-size: 11.5px;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #9fd8cf;
  font-weight: 700;
}
.hero h1 {
  margin: 8px 0 10px;
  font-size: clamp(26px, 3.2vw, 40px);
  line-height: 1.22;
  letter-spacing: -.01em;
}
.hero .lede {
  max-width: 840px;
  margin: 0;
  color: #d2e8e4;
  font-size: 14.5px;
}
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }
.hero-chips span {
  border: 1px solid rgba(255, 255, 255, .18);
  background: rgba(255, 255, 255, .08);
  border-radius: 999px;
  padding: 4px 11px;
  font-size: 12px;
  color: #e5f5f2;
}
.topnav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 18px 0 6px;
}
.topnav a {
  color: var(--muted);
  text-decoration: none;
  font-size: 12.5px;
  padding: 5px 10px;
  border-radius: 999px;
}
.topnav a:hover { background: #e6efee; color: var(--teal-dark); }

.callout {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  border: 1px solid #efd2a8;
  background: #fff8eb;
  border-radius: 12px;
  padding: 13px 16px;
  margin: 16px 0 0;
  color: #74440c;
  font-size: 13px;
}
.callout strong { color: #5c3407; }
.callout .mark {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #d97706;
  color: #fff;
  font-weight: 800;
  font-size: 13px;
  line-height: 22px;
  text-align: center;
  margin-top: 1px;
}

.kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.kpi {
  background: var(--panel);
  border: 1px solid var(--line);
  border-top: 3px solid var(--k, var(--teal));
  border-radius: var(--radius);
  padding: 15px 16px 13px;
  box-shadow: var(--shadow);
}
.kpi.primary {
  color: #fff;
  background: linear-gradient(145deg, #0d4a44, #0f5f57);
  border-color: transparent;
}
.kpi.primary .kpi-label, .kpi.primary .kpi-sub { color: #c9e6e1; }
.kpi.primary .kpi-value { color: #fff; }
.kpi-label { font-size: 12px; color: var(--muted); font-weight: 600; }
.kpi-value { font-size: clamp(24px, 2.6vw, 34px); line-height: 1.15; font-weight: 750; margin-top: 5px; letter-spacing: -.01em; }
.kpi-sub { font-size: 11.5px; color: var(--muted); margin-top: 3px; }
.kpi.warn { --k: #b45309; }
.kpi.ok { --k: #0f766e; }

.section { margin-top: 34px; scroll-margin-top: 16px; }
.section-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 9px 12px; margin-bottom: 13px; }
.secnum {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  color: var(--teal);
  background: #e0efec;
  border-radius: 6px;
  padding: 2px 7px;
}
.section-head h2 { margin: 0; font-size: 21px; letter-spacing: -.01em; }
.section-head p { margin: 0; color: var(--muted); font-size: 12.5px; }
.grid-2 { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr); gap: 16px; align-items: start; }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 20px 22px 18px;
  box-shadow: var(--shadow);
  min-width: 0;
}
.panel h3 { margin: 0 0 3px; font-size: 15.5px; }
.panel-sub { margin: 0 0 16px; color: var(--muted); font-size: 12.5px; }
.panel .divider { height: 1px; background: var(--line); margin: 18px 0 15px; }
.footnote { margin: 14px 0 0; color: var(--muted); font-size: 11.5px; line-height: 1.55; }

.bar-row {
  display: grid;
  grid-template-columns: minmax(130px, 238px) minmax(90px, 1fr) 66px;
  gap: 11px;
  align-items: center;
  margin: 9px 0;
}
.bar-label {
  font-size: 12.5px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track {
  height: 10px;
  background: #edf2f3;
  border-radius: 999px;
  overflow: hidden;
}
.bar-fill { display: block; height: 100%; border-radius: 999px; }
.bar-value { text-align: right; line-height: 1.3; }
.bar-value b { display: block; font-size: 12.5px; }
.bar-value span { display: block; font-size: 10.5px; color: var(--muted); }
.cov-row { margin: 13px 0; }
.cov-track { height: 14px; }
.cov-name { display: block; font-weight: 600; }
.cov-note { display: block; font-size: 10.5px; color: var(--muted); line-height: 1.35; margin-top: 1px; }

.stack {
  display: flex;
  height: 27px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e3ebec;
  background: #f0f4f5;
}
.seg {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  min-width: 0;
}
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 9px; font-size: 11.5px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.legend-item i { width: 9px; height: 9px; border-radius: 3px; display: inline-block; }
.legend-item b { font-variant-numeric: tabular-nums; }
.stack-block + .stack-block { margin-top: 18px; }
.stack-title { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; font-weight: 650; margin-bottom: 7px; }
.stack-title span { color: var(--muted); font-weight: 400; }

.chip {
  display: inline-block;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1.55;
  white-space: nowrap;
  border: 1px solid transparent;
}
.chip.mini { padding: 0 5px; font-size: 9.5px; margin-left: 3px; }
.chip-green { background: #dcf3ec; color: #0a6155; border-color: #b9e4d9; }
.chip-blue { background: #e3ebfc; color: #1e40af; border-color: #c7d6f8; }
.chip-purple { background: #ede8fb; color: #5b21b6; border-color: #dcd1f7; }
.chip-amber { background: #fdf0d8; color: #92500a; border-color: #f5ddb2; }
.chip-red { background: #fde5e5; color: #991b1b; border-color: #f6caca; }
.chip-gray { background: #eef2f4; color: #52646d; border-color: #dde6e9; }
.ed-scie { background: #e3ebfc; color: #1e40af; }
.ed-ssci { background: #dcf3ec; color: #0a6155; }
.ed-esci { background: #ede8fb; color: #5b21b6; }
.ed-ahci { background: #fdf0d8; color: #92500a; }
.ed-na { background: #eef2f4; color: #52646d; }

.source-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.source-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 17px 17px 15px;
  box-shadow: var(--shadow);
  position: relative;
  overflow: hidden;
}
.source-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--k, var(--teal));
}
.source-card .role { font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 700; }
.source-card h3 { margin: 6px 0 2px; font-size: 17px; }
.source-card .metric { font-size: 12.5px; font-weight: 650; color: var(--k, var(--teal)); }
.source-card p { margin: 8px 0 0; font-size: 12px; color: var(--muted); line-height: 1.55; }
.source-card .sub { display: block; margin-top: 7px; font-size: 11px; color: var(--muted); }

.rules { margin: 0; padding: 0; list-style: none; counter-reset: rule; }
.rules li {
  counter-increment: rule;
  position: relative;
  padding: 0 0 13px 34px;
  font-size: 12.5px;
}
.rules li::before {
  content: counter(rule);
  position: absolute;
  left: 0;
  top: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e0efec;
  color: var(--teal);
  font-size: 11px;
  font-weight: 800;
  text-align: center;
  line-height: 22px;
}
.rules li:last-child { padding-bottom: 0; }
.rules b { color: var(--ink); }

.notes-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.note-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 4px solid var(--k, var(--amber));
  border-radius: 12px;
  padding: 15px 17px;
  box-shadow: var(--shadow);
}
.note-card h3 { margin: 0 0 5px; font-size: 13.5px; }
.note-card p { margin: 0; color: var(--muted); font-size: 12.3px; line-height: 1.6; }

.audit-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px;
  margin: 0 0 12px;
}
.audit-toolbar input[type="search"] {
  flex: 1 1 280px;
  min-width: 220px;
  border: 1px solid #cfdcde;
  border-radius: 9px;
  padding: 9px 12px;
  font: inherit;
  font-size: 12.5px;
  color: var(--ink);
  background: #fff;
  outline: none;
}
.audit-toolbar input[type="search"]:focus { border-color: var(--teal); box-shadow: 0 0 0 3px rgba(15, 95, 87, .12); }
.audit-toolbar select {
  border: 1px solid #cfdcde;
  border-radius: 9px;
  padding: 8px 10px;
  font: inherit;
  font-size: 12.5px;
  color: var(--ink);
  background: #fff;
  max-width: 235px;
}
.audit-toolbar button {
  border: 1px solid #cfdcde;
  border-radius: 9px;
  padding: 8px 13px;
  font: inherit;
  font-size: 12.5px;
  color: var(--muted);
  background: #f7fafa;
  cursor: pointer;
}
.audit-toolbar button:hover { background: #edf5f3; color: var(--teal-dark); }
.visible-count { margin-left: auto; font-size: 12px; color: var(--muted); white-space: nowrap; }

.table-wrap {
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: auto;
  max-height: 78vh;
  background: #fff;
  box-shadow: var(--shadow);
}
table.audit {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  min-width: 1260px;
  font-size: 12px;
}
table.audit th {
  position: sticky;
  top: 0;
  z-index: 2;
  text-align: left;
  background: #f3f8f7;
  color: #334b53;
  font-size: 11px;
  letter-spacing: .02em;
  padding: 10px 9px;
  border-bottom: 1px solid #cfdcdd;
  white-space: nowrap;
}
table.audit td {
  padding: 8px 9px;
  border-bottom: 1px solid #edf2f3;
  vertical-align: top;
}
table.audit tbody tr:hover td { background: #f7fbfa; }
table.audit tbody tr:last-child td { border-bottom: 0; }
tr[hidden] { display: none !important; }
.col-idx { width: 34px; color: #93a4aa; font-size: 10.5px; text-align: right; }
.col-title { min-width: 218px; max-width: 270px; }
.jtitle { display: block; font-weight: 650; line-height: 1.4; }
.jmeta { display: block; color: #87979d; font-size: 10.5px; margin-top: 2px; }
.col-cat { min-width: 150px; max-width: 210px; font-size: 11.2px; line-height: 1.45; color: #354e56; }
.col-src { min-width: 78px; white-space: nowrap; }
.num-main { display: block; font-weight: 600; line-height: 1.35; }
.num-main.zero { color: #87979d; font-weight: 500; }
.num-sub { display: block; font-size: 10.2px; color: var(--muted); line-height: 1.35; margin-top: 1px; }
.na { color: #9aa9ae; font-size: 10.8px; }
.dag { color: #b45309; font-size: 9px; }
.col-rss { min-width: 94px; }
.col-rss .num-main { font-size: 11px; margin-top: 2px; }
.col-route { min-width: 90px; white-space: nowrap; }
.src { font-weight: 650; }
.src-fb { color: var(--muted); }
.arrow { color: #9aa9ae; margin: 0 3px; font-size: 10px; }
.col-note { min-width: 125px; max-width: 180px; }
.note { display: block; color: #6b7c83; font-size: 10.7px; line-height: 1.4; }
.empty-cell { text-align: center !important; padding: 30px !important; color: var(--muted); }
.table-foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 18px; margin-top: 9px; font-size: 11.3px; color: var(--muted); }

.footer {
  margin-top: 34px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, .6fr);
  gap: 24px;
}
.footer h3 { margin: 0 0 9px; font-size: 14px; }
.filelist { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 22px; }
.filelist li { display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px dashed #e2eaeb; padding: 4px 0; font-size: 12px; }
.filelist a { text-decoration: none; }
.filelist a:hover { text-decoration: underline; }
.filelist .size { color: #94a3a8; font-size: 10.5px; white-space: nowrap; }
.footmeta { font-size: 11.5px; color: var(--muted); }
.footmeta code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10.5px; background: #eef3f4; padding: 1px 4px; border-radius: 4px; }

@media (max-width: 1040px) {
  .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .source-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-2 { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .wrap { padding: 16px 12px 32px; }
  .hero { padding: 25px 22px 23px; border-radius: 16px; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .source-cards, .notes-grid { grid-template-columns: 1fr; }
  .bar-row { grid-template-columns: 112px minmax(70px, 1fr) 58px; gap: 8px; }
  .bar-label { font-size: 11.5px; }
  .footer { grid-template-columns: 1fr; }
  .filelist { grid-template-columns: 1fr; }
  .audit-toolbar select { max-width: none; flex: 1 1 160px; }
  .visible-count { margin-left: 0; }
}
@media print {
  body { background: #fff; }
  .wrap { max-width: none; padding: 0; }
  .audit-toolbar { display: none; }
  .table-wrap { max-height: none; overflow: visible; box-shadow: none; }
  .panel, .kpi, .source-card, .note-card { box-shadow: none; break-inside: avoid; }
  .topnav { display: none; }
}
"""

JS = """
(function () {
  var rows = Array.prototype.slice.call(document.querySelectorAll('#audit-body tr.audit-row'));
  var q = document.getElementById('audit-search');
  var dec = document.getElementById('filter-decision');
  var ed = document.getElementById('filter-edition');
  var count = document.getElementById('visible-count');
  var empty = document.getElementById('empty-row');

  function apply() {
    var term = q.value.trim().toLowerCase();
    var decision = dec.value;
    var edition = ed.value;
    var visible = 0;
    rows.forEach(function (row) {
      var ok = (!term || row.getAttribute('data-search').indexOf(term) !== -1) &&
               (!decision || row.getAttribute('data-decision') === decision) &&
               (!edition || row.getAttribute('data-edition') === edition);
      row.hidden = !ok;
      if (ok) { visible += 1; }
    });
    count.textContent = '显示 ' + visible + ' / ' + rows.length + ' 本';
    empty.hidden = visible !== 0;
  }

  q.addEventListener('input', apply);
  dec.addEventListener('change', apply);
  ed.addEventListener('change', apply);
  document.getElementById('reset-filters').addEventListener('click', function () {
    q.value = '';
    dec.value = '';
    ed.value = '';
    apply();
    q.focus();
  });
  apply();
})();
"""


def main() -> None:
    watch = read_csv(WATCHLIST_CSV)
    audit = read_csv(MERGED_CSV)

    total = len(watch)
    daily = sum(1 for row in watch if (row.get("include_daily") or "").strip().lower() == "yes")
    edition_counts = Counter((row.get("edition") or "?").strip() or "?" for row in watch)
    scopus_counts = Counter((row.get("scopus_active") or "Unknown").strip() or "Unknown" for row in watch)

    cat_counts = Counter((row.get("primary_category") or "").strip() or "未标注" for row in watch)
    top15 = cat_counts.most_common(15)
    max_cat = top15[0][1] if top15 else 1

    oa_ok = sum(1 for row in audit if to_float(row.get("openalex_items_90d")) > 0)
    cr_ok = sum(1 for row in audit if to_float(row.get("crossref_items_90d")) > 0)
    pubmed_rows = [row for row in audit if (row.get("pubmed_status") or "").strip()]
    pubmed_ok = sum(1 for row in pubmed_rows if (row.get("pubmed_status") or "").strip() == "ok")
    rss_matched = sum(1 for row in audit if (row.get("rss_match") or "").strip() in {"exact", "fuzzy"})
    rss_active = sum(1 for row in audit if to_float(row.get("rss_items_90d")) > 0)
    audit_total = len(audit)

    abstract_counts = Counter((row.get("abstract_source") or "none").strip() or "none" for row in audit)
    doi_counts = Counter((row.get("doi_source") or "none").strip() or "none" for row in audit)
    decision_counts = Counter((row.get("decision") or "").strip() for row in audit)

    oa_agg = aggregate_source(OPENALEX_AUDIT_CSV)
    cr_agg = aggregate_source(CROSSREF_AUDIT_CSV)
    pm_agg = aggregate_source(PUBMED_AUDIT_CSV)

    # ---------- 顶部卡片 ----------
    kpi_cards = [
        ("Q1 总刊数", fmt_int(total), "JCR 2025 全学科", "primary", ""),
        ("日更候选", fmt_int(daily), f"排除 {fmt_int(total - daily)} 本 Inactive", "primary", ""),
    ]
    for edition in EDITION_ORDER[:4]:
        count = edition_counts.get(edition, 0)
        sub = f"{pct(count, total)} · 全量"
        if edition == "AHCI":
            sub = f"{pct(count, total)} · 另 7 本未标注"
        kpi_cards.append((EDITION_LABEL[edition], fmt_int(count), sub, "", EDITION_COLOR[edition]))
    kpi_cards.extend([
        ("Scopus Active", fmt_int(scopus_counts.get("Active", 0)), pct(scopus_counts.get("Active", 0), total), "ok", "#0f766e"),
        ("Scopus Inactive", fmt_int(scopus_counts.get("Inactive", 0)), pct(scopus_counts.get("Inactive", 0), total), "warn", "#b45309"),
        ("Scopus Unknown", fmt_int(scopus_counts.get("Unknown", 0)), pct(scopus_counts.get("Unknown", 0), total), "", "#64748b"),
    ])
    kpi_html = []
    for label, value, sub, variant, color in kpi_cards:
        style = f' style="--k:{color}"' if color else ""
        kpi_html.append(
            f'<div class="kpi {variant}"{style}>'
            f'<div class="kpi-label">{e(label)}</div>'
            f'<div class="kpi-value">{e(value)}</div>'
            f'<div class="kpi-sub">{e(sub)}</div>'
            "</div>"
        )

    # ---------- Edition 图 ----------
    edition_bars = []
    for edition in EDITION_ORDER:
        count = edition_counts.get(edition, 0)
        edition_bars.append(
            bar_row(EDITION_LABEL[edition], count, total, fmt_int(count),
                    pct(count, total), EDITION_COLOR[edition])
        )
    edition_segments = [
        (EDITION_LABEL[edition], edition_counts.get(edition, 0), EDITION_COLOR[edition])
        for edition in EDITION_ORDER
    ]

    # ---------- Top 15 学科图 ----------
    top15_bars = []
    for index, (category, count) in enumerate(top15):
        color = "#d97706" if category == "Multiple" else "#0f766e"
        top15_bars.append(
            bar_row(category, count, max_cat, fmt_int(count), pct(count, total), color, scale="sqrt")
        )

    # ---------- 覆盖图 ----------
    coverage_rows = [
        coverage_row("OpenAlex 有记录", oa_ok, audit_total, "#0f766e", "近 90 天 ≥1 条"),
        coverage_row("Crossref 有记录", cr_ok, audit_total, "#1d4ed8", "近 90 天 ≥1 条"),
        coverage_row("PubMed 有记录", pubmed_ok, len(pubmed_rows), "#7c3aed",
                     f"仅 {len(pubmed_rows)} 本生物医学子集；占全样本 {pct(pubmed_ok, audit_total)}"),
        coverage_row("RSS 映射命中", rss_matched, audit_total, "#b45309", "exact + fuzzy"),
        coverage_row("RSS 90 天活跃", rss_active, audit_total, "#d97706", "feed 内 ≥1 条"),
    ]

    abstract_segments = [(label, abstract_counts.get(key, 0), color) for key, label, color in ABSTRACT_ORDER]
    doi_segments = [(label, doi_counts.get(key, 0), color) for key, label, color in DOI_ORDER]
    abstract_none = abstract_counts.get("none", 0)
    doi_none = doi_counts.get("none", 0)

    # ---------- 结论卡片 ----------
    oa_metric = f"{oa_ok} / {audit_total} 有记录（{pct(oa_ok, audit_total)}）"
    if oa_agg:
        oa_metric += f" · 实取 {fmt_int(oa_agg['items'])} 条"
    oa_sub = f"条目摘要 {oa_agg['abstract_rate']:.1f}% · DOI {oa_agg['doi_rate']:.2f}%" if oa_agg else "摘要按出版商分层明显"

    cr_metric = f"{cr_ok} / {audit_total} 有记录（{pct(cr_ok, audit_total)}）"
    if cr_agg:
        cr_metric += f" · 实取 {fmt_int(cr_agg['items'])} 条"
    cr_sub = f"条目摘要 {cr_agg['abstract_rate']:.1f}% · DOI {cr_agg['doi_rate']:.1f}%" if cr_agg else "DOI 近全覆盖，摘要覆盖率低"

    pm_metric = f"{pubmed_ok} / {len(pubmed_rows)} 有记录（{pct(pubmed_ok, len(pubmed_rows))}）"
    if pm_agg:
        pm_metric += f" · 实取 {fmt_int(pm_agg['items'])} 条"
    pm_sub = f"条目摘要 {pm_agg['abstract_rate']:.1f}% · DOI {pm_agg['doi_rate']:.1f}%" if pm_agg else "摘要可用，需处理年份级 PubDate"

    rss_metric = f"映射 {rss_matched} / {audit_total} · 90 天活跃 {rss_active} / {audit_total}"
    rss_sub = "ScienceDirect feed 无摘要、无 DOI、条目常缺日期"

    source_cards = [
        ("PRIMARY · 主源", "OpenAlex", oa_metric, oa_sub,
         "用于发现、元数据与 DOI 主键。摘要按出版商分层：Wiley/OUP/T&F 较高，Elsevier/Springer/Nature 需回源或兜底。", "#0f766e"),
        ("FALLBACK · 兜底", "Crossref", cr_metric, cr_sub,
         "DOI 近 100%，适合做 DOI/元数据兜底与去重对齐；摘要覆盖低，不能单独承担摘要采集。", "#1d4ed8"),
        ("BIOMEDICAL · 生物医学", "PubMed", pm_metric, pm_sub,
         "仅用于 60 本生物医学子集，摘要约 75%；需处理年份级 PubDate 与 ISSN 分裂。", "#7c3aed"),
        ("SIGNAL · 仅信号", "RSS", rss_metric, rss_sub,
         "只作“新一期/新条目”信号，不作元数据或摘要主源；ScienceDirect 平台覆盖最大但不可给正文。", "#b45309"),
    ]
    source_cards_html = []
    for role, title, metric, sub, desc, color in source_cards:
        source_cards_html.append(
            f'<article class="source-card" style="--k:{color}">'
            f'<div class="role">{e(role)}</div>'
            f"<h3>{e(title)}</h3>"
            f'<div class="metric">{e(metric)}</div>'
            f"<p>{e(desc)}</p>"
            f'<span class="sub">{e(sub)}</span>'
            "</article>"
        )

    # ---------- 决策图 ----------
    decision_bars = []
    decision_codes = [code for code in DECISION_ORDER if decision_counts.get(code)]
    for code in list(decision_counts):
        if code and code not in decision_codes:
            decision_codes.append(code)
    max_decision = max((decision_counts.get(code, 0) for code in decision_codes), default=1)
    for code in decision_codes:
        count = decision_counts.get(code, 0)
        color = {
            "openalex_primary_crossref_fallback": "#0f766e",
            "openalex_primary": "#1d4ed8",
            "pubmed_primary": "#7c3aed",
            "no_recent_items": "#94a3b8",
        }.get(code, "#64748b")
        decision_bars.append(
            bar_row(DECISION_LABEL.get(code, code), count, max_decision, str(count),
                    pct(count, audit_total), color)
        )

    # ---------- 明细表 ----------
    table_rows = [audit_row(index, row) for index, row in enumerate(audit, start=1)]
    edition_options = []
    for edition in EDITION_ORDER:
        count = sum(1 for row in audit if ((row.get("edition") or "?").strip() or "?") == edition)
        if count:
            edition_options.append(
                f'<option value="{e(edition)}">{e(EDITION_LABEL[edition])}（{count}）</option>'
            )
    decision_options = []
    for code in decision_codes:
        if not code:
            continue
        decision_options.append(
            f'<option value="{e(code)}">{e(DECISION_LABEL.get(code, code))}（{decision_counts[code]}）</option>'
        )

    file_links = [
        (WATCHLIST_CSV, "Q1 watchlist（5,279 行）"),
        (SAMPLE_CSV, "200 本分层审计样本"),
        (MERGED_CSV, "四源合并审计（200 行）"),
        (OPENALEX_AUDIT_CSV, "OpenAlex 审计明细 CSV"),
        (CROSSREF_AUDIT_CSV, "Crossref 审计明细 CSV"),
        (PUBMED_AUDIT_CSV, "PubMed 审计明细 CSV"),
        (RSS_AUDIT_CSV, "RSS 抓取审计明细 CSV"),
    ]
    md_links = [
        (DATA_DIR / "foreign_q1_summary_2026-11-25.md", "Q1 汇总"),
        (DATA_DIR / "foreign_source_audit_q1_2026-11-25.md", "四源合并审计结论"),
        (DATA_DIR / "foreign_openalex_audit_q1_2026-11-25.md", "OpenAlex 审计"),
        (DATA_DIR / "foreign_crossref_audit_q1_2026-11-25.md", "Crossref 审计"),
        (DATA_DIR / "foreign_pubmed_audit_q1_2026-11-25.md", "PubMed 审计"),
        (DATA_DIR / "foreign_rss_audit_q1_2026-11-25.md", "RSS 审计"),
    ]
    link_items = []
    for path, label in file_links + md_links:
        if not path.exists():
            continue
        link_items.append(
            "<li>"
            f'<a href="{e(path.name)}">{e(label)}</a>'
            f'<span class="size">{e(fmt_size(path))}</span>'
            "</li>"
        )

    # 完整性提示（只在终端输出，不改变报告数字）
    checks = {
        "总刊数": (total, 5279),
        "日更候选": (daily, 5238),
        "OpenAlex 有记录": (oa_ok, 183),
        "Crossref 有记录": (cr_ok, 176),
        "PubMed 有记录": (pubmed_ok, 56),
        "PubMed 子集": (len(pubmed_rows), 60),
        "RSS 映射": (rss_matched, 56),
        "RSS 活跃": (rss_active, 39),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            print(f"WARNING: {label} = {actual}（预期 {expected}）")

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>国外 Q1 期刊源覆盖与选源报告 · {REPORT_DATE}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <div class="eyebrow">FOREIGN JOURNALS · JCR 2025 · Q1</div>
    <h1>国外 Q1 期刊源覆盖与选源报告</h1>
    <p class="lede">
      基于 {fmt_int(total)} 本 JCR 2025 全学科 Q1 期刊的版本与学科分布，
      以及 {audit_total} 本分层样本的 OpenAlex / Crossref / PubMed / RSS 四源覆盖审计，
      给出国外期刊日更采集的源适配策略与待办边界。
    </p>
    <div class="hero-chips">
      <span>Q1 全量 {fmt_int(total)} 本</span>
      <span>分层样本 {audit_total} 本</span>
      <span>4 个元数据源</span>
      <span>数据快照 {REPORT_DATE}</span>
      <span>只读报告 · 无外部依赖</span>
    </div>
  </header>

  <nav class="topnav" aria-label="页面导航">
    <a href="#overview">概览</a>
    <a href="#distribution">全量分布</a>
    <a href="#coverage">源覆盖</a>
    <a href="#selection">选源结论</a>
    <a href="#audit">200 本明细</a>
    <a href="#notes">口径与限制</a>
  </nav>

  <div class="callout" role="note">
    <span class="mark">!</span>
    <div>
      <strong>样本口径：{audit_total} / {fmt_int(total)} 是分层样本，不是全量逐本审计。</strong>
      200 本按 Scopus Top level 分层（Life Sciences / Health Sciences / Physical Sciences / Social Sciences / Unknown 各 40 本），
      用于确定源适配策略；全量 Edition、学科与 Scopus 状态统计来自 {fmt_int(total)} 行 watchlist。
    </div>
  </div>

  <section id="overview" class="section" aria-label="关键数字">
    <div class="kpis">{"".join(kpi_html)}</div>
  </section>

  <section id="distribution" class="section">
    <div class="section-head">
      <span class="secnum">01</span>
      <h2>全量分布</h2>
      <p>{fmt_int(total)} 本 Q1 的 Edition 与 JCR 主学科结构</p>
    </div>
    <div class="grid-2">
      <article class="panel">
        <h3>Edition 分布</h3>
        <p class="panel-sub">SCIE 占 {pct(edition_counts.get("SCIE", 0), total)}，SCIE + SSCI 合计
          {pct(edition_counts.get("SCIE", 0) + edition_counts.get("SSCI", 0), total)}。</p>
        {"".join(edition_bars)}
        <div class="divider"></div>
        {stacked_bar(edition_segments, total)}
        {legend(edition_segments, total)}
        <p class="footnote">“未标注”为 watchlist 中 Edition 字段为 “?” 的 7 本；
          Inactive 期刊仍保留在 Q1 全量中，但不进入日更候选。</p>
      </article>

      <article class="panel">
        <h3>Top 15 JCR 主学科 Q1 数量</h3>
        <p class="panel-sub">按 primary_category 统计；“Multiple”为 JCR 多学科刊标记，
          不计入单一学科解释。</p>
        {"".join(top15_bars)}
        <p class="footnote">条形长度为平方根刻度（便于展示长尾），标注为实际刊数；百分比为占
          {fmt_int(total)} 本全量的比例。</p>
      </article>
    </div>
  </section>

  <section id="coverage" class="section">
    <div class="section-head">
      <span class="secnum">02</span>
      <h2>200 本源覆盖</h2>
      <p>近 90 天窗口（2026-08-27 ～ 2026-11-25）的实际审计结果</p>
    </div>
    <div class="grid-2">
      <article class="panel">
        <h3>各源覆盖</h3>
        <p class="panel-sub">PubMed 的分母是 60 本生物医学子集，其余为 200 本全样本。</p>
        {"".join(coverage_rows)}
        <p class="footnote">
          缺口：OpenAlex 有 {audit_total - oa_ok} 本窗口内无记录（16 本 no_items + 1 本 no_source）；
          Crossref 有 {audit_total - cr_ok} 本无近 90 天记录；RSS 有 {audit_total - rss_matched} 本未映射。
          PubMed 4 本 no_items，接口无失败。
        </p>
      </article>

      <article class="panel">
        <h3>摘要源 / DOI 源分布</h3>
        <p class="panel-sub">按每本刊最终选定的来源统计，合计均为 {audit_total} 本。</p>
        <div class="stack-block">
          <div class="stack-title"><b>摘要源</b><span>有摘要 {audit_total - abstract_none} / {audit_total}</span></div>
          {stacked_bar(abstract_segments, audit_total)}
          {legend(abstract_segments, audit_total)}
        </div>
        <div class="stack-block">
          <div class="stack-title"><b>DOI 源</b><span>有 DOI {audit_total - doi_none} / {audit_total}</span></div>
          {stacked_bar(doi_segments, audit_total)}
          {legend(doi_segments, audit_total)}
        </div>
        <p class="footnote">
          OpenAlex 同时承担 {abstract_counts.get("openalex", 0)} 本摘要与 {doi_counts.get("openalex", 0)} 本 DOI；
          PubMed 为 {abstract_counts.get("pubmed", 0)} 本生物医学刊提供摘要；Crossref 只补了
          {abstract_counts.get("crossref", 0)} 本摘要。另有 {abstract_none} 本 90 天内无任何记录。
        </p>
      </article>
    </div>
  </section>

  <section id="selection" class="section">
    <div class="section-head">
      <span class="secnum">03</span>
      <h2>选源结论</h2>
      <p>OpenAlex 主源 · Crossref 兜底 · PubMed 补生物医学 · RSS 仅信号</p>
    </div>
    <div class="source-cards">{"".join(source_cards_html)}</div>

    <div class="grid-2" style="margin-top:16px">
      <article class="panel">
        <h3>200 本选源决策分布</h3>
        <p class="panel-sub">每本刊的实际路由（primary → fallback）。</p>
        {"".join(decision_bars)}
        <p class="footnote">
          176 本采用 OpenAlex 主源 + Crossref 兜底；7 本仅 OpenAlex；1 本 PubMed 主源；
          16 本 90 天内无记录（多为季刊/年刊或索引滞后），需回官网或等待下一窗口。
        </p>
      </article>

      <article class="panel">
        <h3>落地规则</h3>
        <p class="panel-sub">按“发现 / 元数据 / 摘要 / 信号”拆分职责，避免单源承担全部字段。</p>
        <ol class="rules">
          <li><b>OpenAlex 做发现与 DOI 主源。</b>先用 ISSN 找 source，再取近 90 天 works；
            摘要缺失的出版商（Elsevier / Springer / Nature）回源站或走兜底。</li>
          <li><b>Crossref 做 DOI/元数据兜底。</b>OpenAlex 无记录或截断时补齐；
            不把 Crossref 的 abstract 当作摘要主来源。</li>
          <li><b>PubMed 只覆盖生物医学子集。</b>摘要率约 75%，适合作为医学刊摘要补强；
            需处理年份级 PubDate、ISSN/eISSN 分裂与评论类记录。</li>
          <li><b>RSS 仅用于“新一期”信号。</b>命中率约 28%，ScienceDirect 的 feed
            无摘要、无 DOI，且条目缺日期；不能作为元数据或摘要主源。</li>
        </ol>
      </article>
    </div>
  </section>

  <section id="audit" class="section">
    <div class="section-head">
      <span class="secnum">04</span>
      <h2>200 本审计明细</h2>
      <p>标题、Edition、JIF、主学科、四源条数与摘要率、RSS、选源路由、决策与备注</p>
    </div>

    <div class="audit-toolbar">
      <input id="audit-search" type="search" placeholder="搜索刊名 / ISSN / 学科 / 备注…" aria-label="搜索审计明细">
      <select id="filter-decision" aria-label="按决策筛选">
        <option value="">全部决策（{audit_total}）</option>
        {"".join(decision_options)}
      </select>
      <select id="filter-edition" aria-label="按 Edition 筛选">
        <option value="">全部 Edition（{audit_total}）</option>
        {"".join(edition_options)}
      </select>
      <button id="reset-filters" type="button">重置</button>
      <span class="visible-count" id="visible-count">显示 {audit_total} / {audit_total} 本</span>
    </div>

    <div class="table-wrap">
      <table class="audit">
        <caption class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">200 本分层审计样本明细</caption>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">期刊</th>
            <th scope="col">Edition</th>
            <th scope="col">JIF</th>
            <th scope="col">主学科</th>
            <th scope="col">OpenAlex</th>
            <th scope="col">Crossref</th>
            <th scope="col">PubMed</th>
            <th scope="col">RSS</th>
            <th scope="col">选源（主 → 兜底）</th>
            <th scope="col">决策</th>
            <th scope="col">Notes</th>
          </tr>
        </thead>
        <tbody id="audit-body">
          {"".join(table_rows)}
          <tr id="empty-row" hidden><td class="empty-cell" colspan="12">没有匹配的期刊，请调整关键词或筛选条件。</td></tr>
        </tbody>
      </table>
    </div>
    <div class="table-foot">
      <span>共 {audit_total} 行；保持审计清单原始顺序。† 表示该源单页截断（最多 100 条），摘要率为最新 100 条口径。</span>
      <span>RSS 条数为 feed 内 90 天条目；ScienceDirect feed 无摘要/DOI。</span>
    </div>
    <noscript><p class="footnote">浏览器未启用 JavaScript：表格仍完整可读，但关键词与下拉筛选不可用。</p></noscript>
  </section>

  <section id="notes" class="section">
    <div class="section-head">
      <span class="secnum">05</span>
      <h2>口径与限制</h2>
      <p>阅读本报告数字前需要知道的边界</p>
    </div>
    <div class="notes-grid">
      <article class="note-card" style="--k:#b45309">
        <h3>200 / {fmt_int(total)} 是分层样本</h3>
        <p>200 本按 Scopus 五大 Top level 各 40 本分层抽取，用于确定源适配策略，
          不是对 {fmt_int(total)} 本 Q1 的逐本审计。样本中的覆盖率和决策比例不能直接外推为全量精确比例。</p>
      </article>
      <article class="note-card" style="--k:#d97706">
        <h3>RSS：ScienceDirect feed 无摘要/DOI</h3>
        <p>rss.sciencedirect.com 的 description 只有 Publication date / Source / Author(s) 元数据，
          没有摘要正文，也没有 DOI；条目还经常缺日期。RSS 只作“新一期信号”，
          不能作为元数据或摘要主源，活跃判断需用 lastBuildDate 或抓取时间兜底。</p>
      </article>
      <article class="note-card" style="--k:#7c3aed">
        <h3>PubMed 只审计 60 本生物医学刊</h3>
        <p>56 / 60 是该子集内有记录的比例；换算到 200 本样本为 28.0%，并非 93.3% 的全样本覆盖。
          PubMed 的摘要率约 75%，且部分刊受年份级 PubDate、评论/通讯类记录影响。</p>
      </article>
      <article class="note-card" style="--k:#1d4ed8">
        <h3>摘要率是下界，不是全窗口真值</h3>
        <p>各源近 90 天审计中，部分高产能刊被单页截断（OpenAlex / Crossref 最多 100 条）；
          表中的摘要率只代表实际取回条目。Crossref 的 abstract 由出版商选择性提交，
          缺失不等于论文没有摘要。</p>
      </article>
      <article class="note-card" style="--k:#0f766e">
        <h3>全量数字来自 watchlist 字段</h3>
        <p>{fmt_int(total)} 本总量、{fmt_int(daily)} 本日更候选、Edition 与 Scopus 状态分布均直接统计
          watchlist CSV；Top 学科使用 primary_category。未对 5,279 本逐本请求外部源。</p>
      </article>
      <article class="note-card" style="--k:#64748b">
        <h3>只读、可复现、无外部依赖</h3>
        <p>报告由 <code>scripts/build_foreign_q1_report.py</code> 离线生成，读取本地 CSV/MD，
          不联网、不修改输入文件、不写数据库。HTML 内嵌全部样式、脚本与 200 行明细，
          无 CDN，可双击直接打开。</p>
      </article>
    </div>
  </section>

  <footer class="footer">
    <div>
      <h3>数据与产物</h3>
      <ul class="filelist">{"".join(link_items)}</ul>
    </div>
    <div class="footmeta">
      <h3>说明</h3>
      <p>数据快照：{REPORT_DATE}<br>
      审计窗口：2026-08-27 ～ 2026-11-25<br>
      全量：{fmt_int(total)} 本；样本：{audit_total} 本<br>
      生成脚本：<code>scripts/build_foreign_q1_report.py</code></p>
      <p>本报告仅呈现本地审计结果；未对 5,279 本 Q1 逐本联网复核。</p>
    </div>
  </footer>

</div>
<script>{JS}</script>
</body>
</html>
"""

    OUT_HTML.write_text(html_doc, encoding="utf-8", newline="\n")
    size = OUT_HTML.stat().st_size
    print(f"Wrote {OUT_HTML} ({size:,} bytes, {size / 1024:.1f} KB)")
    print(f"Q1 total={total}, daily={daily}, editions={dict(edition_counts)}, scopus={dict(scopus_counts)}")
    print(f"Audit total={audit_total}; OpenAlex={oa_ok}, Crossref={cr_ok}, "
          f"PubMed={pubmed_ok}/{len(pubmed_rows)}, RSS mapped={rss_matched}, RSS active={rss_active}")
    print(f"Abstract source={dict(abstract_counts)}; DOI source={dict(doi_counts)}")
    print(f"Decisions={dict(decision_counts)}")
    for label, agg in [("OpenAlex", oa_agg), ("Crossref", cr_agg), ("PubMed", pm_agg)]:
        if agg:
            print(f"{label}: items={agg['items']:,}, abstracts={agg['abstracts']:,} "
                  f"({agg['abstract_rate']:.1f}%), DOIs={agg['dois']:,} ({agg['doi_rate']:.2f}%)")


if __name__ == "__main__":
    main()
