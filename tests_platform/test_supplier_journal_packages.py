import csv
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from crawler_platform.protocol import load_manifest, validate_item


ROOT = Path(__file__).resolve().parents[1] / "crawler_packages" / "academic"
COUNTS = {"qinyun_journals": 104, "rhzh_journals": 122, "sancai_journals": 1}


def package(name):
    path = ROOT / name
    spec = importlib.util.spec_from_file_location(f"supplier_{name}", path / "crawler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = json.loads((path / "journals.json").read_text(encoding="utf-8"))
    return module, load_manifest(path), rows


@pytest.mark.parametrize("name,total", COUNTS.items())
def test_supplier_catalog_and_manifest(name, total):
    _, manifest, rows = package(name)
    assert len(rows) == total
    assert len({row["journal_key"] for row in rows}) == total
    assert manifest.package_key == name
    assert all(row["supplier"] == {"qinyun_journals": "勤云", "rhzh_journals": "仁和汇智", "sancai_journals": "西安三才"}[name] for row in rows)
    assert set(manifest.parameters_schema["properties"]["journal_keys"]["default"]) <= {row["journal_key"] for row in rows}


def test_only_verified_journals_are_in_delivery_catalogs():
    report = ROOT.parents[1] / "journal_catalog" / "supplier-journal-audit-2026-10-26.csv"
    with report.open(encoding="utf-8-sig", newline="") as handle:
        audited = list(csv.DictReader(handle))
    assert len(audited) == 630
    verified = {(row["package"], row["journal_key"]) for row in audited if row["status"] == "verified"}
    delivered = {(name, row["journal_key"]) for name in COUNTS for row in package(name)[2]}
    assert delivered == verified


def test_qinyun_normalizes_article_and_discovery():
    crawler, manifest, rows = package("qinyun_journals")
    journal = next(row for row in rows if row["journal_key"] == "jos")
    with patch.object(crawler, "read_response", return_value=("<input name='CsrfCheckCode' value='test123'><script>jos/ajax/search</script>", "https://jos.org.cn/jos/article/search")):
        assert crawler.discover_search(None, journal, "人工智能", 5) == ("https://jos.org.cn", "jos", "test123")
    item = crawler.normalize({"file_no": 42, "title": "<b>机器学习</b>", "author_name": "张三，李四", "abstract": "<p>摘要</p>", "doi": "10.1/test", "year_id": "2025", "abstract_url": "jos/article/abstract/42"}, journal, "https://jos.org.cn", "jos")
    assert item["url"] == "https://jos.org.cn/jos/article/abstract/42"
    assert item["year"] == 2025
    validate_item(manifest, item)


def test_qinyun_old_form_and_article_list():
    crawler, manifest, rows = package("qinyun_journals")
    journal = next(row for row in rows if row["name"] == "中国农业大学学报（社会科学版）")
    page = '''<form action="key_query.aspx"><input type="hidden" name="__VIEWSTATE" value="abc&amp;def" />
    <input name="Key" /><input type="submit" name="Query" value="检 索" />
    <tr><td><a href="view_abstract.aspx?flag=1&amp;file_no=20260405">农业研究</a></td><td>张三、李四</td><td>2026,43(4):72-80</td></tr></form>'''
    payload = crawler.old_form_payload(page, "农业")
    assert payload["__VIEWSTATE"] == "abc&def"
    assert payload["Key"] == "农业"
    items = crawler.old_page_items(page, "https://example.org/ch/reader/key_query.aspx", journal)
    assert len(items) == 1
    assert items[0]["external_id"] == "20260405"
    validate_item(manifest, items[0])


def test_rhzh_parses_article_and_rejects_wrong_template():
    crawler, manifest, rows = package("rhzh_journals")
    journal = next(row for row in rows if row["journal_key"] == "b11e9e7fdb08aa16")
    item = crawler.normalize({"id": "uuid-1", "titleCn": "<hl>智能</hl>分析", "abstractinfoCn": "<p>摘要</p>", "authors": [{"authorNameCn": "张三"}], "doi": "10.1/test", "yearInt": 2024}, journal)
    assert item["title"] == "智能 分析"
    assert item["authors"] == "张三"
    validate_item(manifest, item)
    with patch.object(crawler, "read_response", return_value='{"data":{}}'):
        with pytest.raises(ValueError, match="UNSUPPORTED_TEMPLATE"):
            crawler.search_page(None, journal, "智能", 1, 5)


def test_rhzh_html_and_search_data_variants():
    crawler, manifest, rows = package("rhzh_journals")
    journals = {row["journal_key"]: row for row in rows}
    page = '''<div class="article-list" id="123"><div class="article-list-title">
    <a href="/article/id/123">自动化研究</a></div>
    <a onclick='searchLike("authorNameCn","张三","");'>张三</a>
    <div class="article-list-time">2024, 5(1)</div><div class="search-abstract">摘要</div></div>'''
    items = crawler.parse_html_records(page, journals["8298cc13a9e419b4"])
    assert len(items) == 1
    assert items[0]["url"].startswith("https://www.aas.net.cn/")
    validate_item(manifest, items[0])
    search_data = crawler.normalize({"id": "cjg_1", "titleCn": "地震研究", "year": "2023", "authors": []}, journals["912d94e870b17943"])
    assert search_data["url"] == "http://www.geophy.cn/article/id/cjg_1"
    validate_item(manifest, search_data)


def test_sancai_parses_article_and_rejects_old_site():
    crawler, manifest, rows = package("sancai_journals")
    journal = next(row for row in rows if row["journal_key"] == "7371a30d9aa7945b")
    item = crawler.normalize({"ArticleID": 1084, "Title": "人工智能", "AuthorsList": "王甲，王乙", "Abstract_Chinese": "摘要", "DOI": "", "Year": 2026}, journal)
    assert item["url"].endswith("/#/digest?ArticleID=1084")
    validate_item(manifest, item)
    old = {"journal_key": "0c2a365ad24fa663", "name": "机械与电子"}
    with pytest.raises(ValueError, match="UNSUPPORTED_TEMPLATE"):
        crawler.search_page(old, "机械", 1, 5)


def test_multi_journal_partial_failure_retains_good_items():
    crawler, _, rows = package("sancai_journals")
    journals = {row["journal_key"]: row for row in rows}
    journals["1d43330d46323f18"] = {"journal_key": "1d43330d46323f18", "name": "安徽师范大学学报（社会科学版）", "url": "http://journal.ahnu.edu.cn"}
    def fake_search(journal, query, page, timeout):
        if journal["journal_key"] == "7371a30d9aa7945b":
            raise ValueError("UNSUPPORTED_TEMPLATE")
        return [{"ArticleID": 11, "Title": "研究"}]
    with patch.object(crawler, "search_page", side_effect=fake_search):
        items, warnings, successful = crawler.collect({"query": "研究", "limit": 2, "parameters": {"journal_keys": ["7371a30d9aa7945b", "1d43330d46323f18"]}}, journals)
    assert successful == 1
    assert len(items) == 1
    assert len(warnings) == 1


@pytest.mark.parametrize("name", COUNTS)
@pytest.mark.parametrize("limit,selected_count,expected_sources", [(1, 2, 1), (2, 3, 2), (3, 2, 2)])
def test_multi_journal_respects_total_limit(name, limit, selected_count, expected_sources, monkeypatch):
    crawler, manifest, rows = package(name)
    selected = [dict(row) for row in rows[:selected_count]]
    for number in range(len(selected), selected_count):
        selected.append({**selected[0], "journal_key": f"journal_{number}", "name": f"Journal {number}"})
    journals = {row["journal_key"]: row for row in selected}
    calls = []

    def item(journal, article_id):
        return {
            "journal_key": journal["journal_key"], "journal_name": journal["name"],
            "journal_url": journal["url"], "external_id": str(article_id),
            "title": "人工智能研究", "url": journal["url"],
            "authors": None, "abstract": None, "doi": None, "year": 2026,
        }

    def rows_for(journal):
        calls.append(journal["journal_key"])
        return [{"id": 1}, {"id": 2}]

    if name == "qinyun_journals":
        def discover(opener, journal, query, timeout):
            calls.append(journal["journal_key"])
            return "https://example.org", "journal", "csrf"

        monkeypatch.setattr(crawler, "build_opener", lambda *args: None)
        monkeypatch.setattr(crawler, "discover_search", discover)
        monkeypatch.setattr(crawler, "search_page", lambda *args: [{"id": 1}, {"id": 2}])
        monkeypatch.setattr(crawler, "normalize", lambda record, journal, *args: item(journal, record["id"]))
    elif name == "rhzh_journals":
        monkeypatch.setattr(crawler, "build_opener", lambda *args: None)
        for method in ("search_page", "search_data_page", "search_html_page"):
            monkeypatch.setattr(crawler, method, lambda opener, journal, query, page, timeout: [item(journal, row["id"]) for row in rows_for(journal)])
    else:
        monkeypatch.setattr(crawler, "search_page", lambda journal, query, page, timeout: rows_for(journal))
        monkeypatch.setattr(crawler, "normalize", lambda record, journal: item(journal, record["id"]))

    items, warnings, successful = crawler.collect(
        {"query": "人工智能", "limit": limit, "parameters": {"journal_keys": list(journals)}}, journals,
    )
    assert len(items) == limit
    assert successful == expected_sources
    assert not warnings
    assert calls == list(journals)[:expected_sources]
    for result in items:
        validate_item(manifest, result)


def test_qinyun_old_template_stops_when_total_limit_is_reached(monkeypatch):
    crawler, _, rows = package("qinyun_journals")
    journals = {row["journal_key"]: row for row in rows[:2]}
    discovery_calls = []

    def old_search(*args):
        discovery_calls.append(args[1]["journal_key"])
        raise ValueError("UNSUPPORTED_TEMPLATE")

    monkeypatch.setattr(crawler, "build_opener", lambda *args: None)
    monkeypatch.setattr(crawler, "discover_search", old_search)
    monkeypatch.setattr(crawler, "collect_old", lambda opener, journal, query, limit, timeout: [{"external_id": "1"}][:limit])
    items, warnings, successful = crawler.collect(
        {"query": "研究", "limit": 1, "parameters": {"journal_keys": list(journals)}}, journals,
    )
    assert len(items) == 1
    assert successful == 1
    assert not warnings
    assert discovery_calls == [next(iter(journals))]
