import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qinyun_journals_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawler
SPEC.loader.exec_module(crawler)


class CrawlerTests(unittest.TestCase):
    def test_manifest_matches_fixture_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        item = json.loads((ROOT / "tests" / "items.jsonl").read_text(encoding="utf-8"))
        fields = {field["name"] for field in manifest["output_schema"]["fields"]}
        self.assertEqual(fields, set(item))

    def test_parse_new_issue_page_url(self):
        journal = {"journal_key": "a" * 16, "name": "示例期刊", "url": "https://example.cn"}
        page = '''<li class="article_line">
        <div class="article_title"><a href="publisher/article/abstract/123">当期文章</a></div>
        <p class="article_author">张三，李四</p>
        <p class="article_position">2026, 48(5):1-10. DOI: <a>10.1234/test</a></p>
        <div class="abstract_body"><p>摘要内容</p></div>
        </li>'''
        items = crawler.parse_new_issue_page(page, "https://example.cn/publisher/article/issue/2026_5", journal)
        self.assertEqual(1, len(items))
        self.assertEqual("当期文章", items[0]["title"])
        self.assertEqual("https://example.cn/publisher/article/abstract/123", items[0]["url"])
        self.assertEqual("10.1234/test", items[0]["doi"])

    def test_current_issue_follows_js_redirect(self):
        journal = {"journal_key": "b" * 16, "name": "示例期刊", "url": "https://example.cn/",
                   "current_url": "https://example.cn/publisher/issue/current"}
        redirect_page = "<script>window.location.href='publisher/article/issue/2026_5';</script>"
        issue_page = '''<li class="article_line">
        <div class="article_title"><a href="publisher/article/abstract/123">当期文章</a></div>
        <p class="article_author">张三，李四</p>
        <p class="article_position">2026, 48(5):1-10. DOI: <a>10.1234/test</a></p>
        </li>'''
        with patch.object(crawler, "read_response", side_effect=[
            (redirect_page, journal["current_url"]),
            (issue_page, "https://example.cn/publisher/article/issue/2026_5"),
        ]):
            items = crawler.current_issue_items(None, journal, 5)
        self.assertEqual(1, len(items))
        self.assertEqual("当期文章", items[0]["title"])
        self.assertEqual("https://example.cn/publisher/article/abstract/123", items[0]["url"])

    def test_parse_new_issue_page_skips_cover_and_contents(self):
        journal = {"journal_key": "c" * 16, "name": "示例期刊", "url": "https://example.cn"}
        page = '''<li class="article_line"><div class="article_title"><a href="publisher/article/abstract/1">封面</a></div></li>
        <li class="article_line"><div class="article_title"><a href="publisher/article/abstract/2">目录</a></div></li>
        <li class="article_line"><div class="article_title"><a href="publisher/article/abstract/3">真实文章标题</a></div></li>'''
        items = crawler.parse_new_issue_page(page, "https://example.cn/publisher/article/issue/2026_5", journal)
        self.assertEqual(1, len(items))
        self.assertEqual("真实文章标题", items[0]["title"])

    def test_enrich_abstract_from_view_abstract_page(self):
        item = {"journal_key": "d" * 16, "title": "示例文章", "url": "https://example.cn/ch/reader/view_abstract.aspx?file_no=1", "abstract": None}
        page = '<span id="Abstract">本文研究了示例问题，构建了可解释的评估框架，并通过多组对比实验验证了方法的有效性。</span>'
        with patch.object(crawler, "read_response", return_value=(page, item["url"])):
            crawler.enrich_abstract(None, item, 5)
        self.assertEqual("本文研究了示例问题，构建了可解释的评估框架，并通过多组对比实验验证了方法的有效性。", item["abstract"])

    def test_extract_abstract_from_abstract_label_cell(self):
        page = '''<table><tr><td><b><span id="AbstractLabel">摘要</span>:</b></td></tr>
        <tr><td class="unnamed3 intro">本文研究非线性抛物型方程正解的梯度估计问题，通过辅助函数和极值原理建立了四类梯度估计，并刻画了奇点附近的爆破行为。</td></tr></table>'''
        self.assertEqual(
            "本文研究非线性抛物型方程正解的梯度估计问题，通过辅助函数和极值原理建立了四类梯度估计，并刻画了奇点附近的爆破行为。",
            crawler.extract_abstract(page),
        )

    def test_extract_abstract_from_cn_abstract_value(self):
        page = '''<div id="CnAbstract"><div class="zy1"><span>摘要:</span>
        <p id="CnAbstractValue">【目的】构建金属矿山TBM适应性评价方法，分析复杂地层条件下的设备改造要点与工程适用性。</p></div></div>'''
        self.assertEqual(
            "【目的】构建金属矿山TBM适应性评价方法，分析复杂地层条件下的设备改造要点与工程适用性。",
            crawler.extract_abstract(page),
        )

    def test_extract_abstract_ignores_placeholder_and_short_text(self):
        self.assertIsNone(crawler.clean_abstract("<p><b>摘要:</b></p>"))
        self.assertIsNone(crawler.clean_abstract("摘要：编者按：病理状态下血管微环境的生化特征与精准治疗策略"))
        self.assertIsNone(crawler.extract_abstract('<span id="Abstract"></span><span id="AbstractLabel">摘要</span>'))

    def test_extract_abstract_does_not_take_keyword_cell(self):
        page = '''<span id="AbstractLabel">摘要</span>:</b></td></tr>
        <tr><td><b><span id="KeyWordLabel">关键词</span>:</b><span id="KeyWord">肺结节；肺癌；影像组学；多学科诊疗</span></td></tr>'''
        self.assertIsNone(crawler.extract_abstract(page))

    def test_extract_abstract_meta_description_fallback(self):
        page = ('<meta name="Description" content="［摘要］　本文系统梳理了肺小结节的影像学评估方法，并提出了多学科综合'
                '诊疗路径与随访策略建议。［Abstract］　This study reviews imaging assessment for pulmonary nodules.">')
        self.assertEqual(
            "本文系统梳理了肺小结节的影像学评估方法，并提出了多学科综合诊疗路径与随访策略建议。",
            crawler.extract_abstract(page),
        )

    def test_noise_title_filter_is_conservative(self):
        for title in ("封面", "目录", "目次", "封一/四", "本期目录", "中华放射医学与防护杂志2026年第11期封面",
                      "2026年 第10期 目录、封面、封底", "含能快递-2026年第10期", "2026年第11期",
                      "南京信息工程大学学报第四届编委会", "《现代应用物理》投稿须知"):
            self.assertTrue(crawler.is_noise_title(title), title)
        for title in ("封面故事：一本期刊的二十年", "目录学视角下的古籍整理研究", "第10期专题研究综述",
                      "人工智能在煤炭地质勘查中的应用：场景、挑战与发展路径"):
            self.assertFalse(crawler.is_noise_title(title), title)

    def test_parse_new_issue_page_supports_underscore_classes(self):
        journal = {"journal_key": "g" * 16, "name": "示例期刊", "url": "https://example.cn"}
        page = '''<li class="article_list">
        <div class="article_list_title"><a href="publisher/article/abstract/456">下划线模板文章</a></div>
        <p class="article_list_author">王五</p>
        <p class="article_list_position">2026, 43(10):1-8</p>
        </li>'''
        items = crawler.parse_new_issue_page(page, "https://example.cn/publisher/article/issue/2026_10", journal)
        self.assertEqual(1, len(items))
        self.assertEqual("下划线模板文章", items[0]["title"])
        self.assertEqual("王五", items[0]["authors"])

    def test_parse_new_issue_page_skips_decorated_issue_noise(self):
        journal = {"journal_key": "e" * 16, "name": "示例期刊", "url": "https://example.cn/publisher/home"}
        page = '''<li class="article_line"><div class="article_title"><a href="article/abstract/1">中华示例杂志2026年第11期封面</a></div></li>
        <li class="article_line"><div class="article_title"><a href="article/abstract/2">2026年 第10期 目录、封面、封底</a></div></li>
        <li class="article_line"><div class="article_title"><a href="article/abstract/3">真实文章标题</a></div></li>'''
        items = crawler.parse_new_issue_page(page, "https://example.cn/publisher/article/issue/2026_11", journal)
        self.assertEqual(1, len(items))
        self.assertEqual("真实文章标题", items[0]["title"])

    def test_parse_new_issue_page_resolves_base_href(self):
        journal = {"journal_key": "f" * 16, "name": "示例期刊", "url": "https://ysks.bgrimm.cn/ysjsksbf/home"}
        page = '''<base href="/"><li class="article_line"><div class="article_title">
        <a href="ysjsksbf/article/abstract/20260427004?st=article_issue">真实文章标题</a></div></li>'''
        items = crawler.parse_new_issue_page(page, "https://ysks.bgrimm.cn/ysjsksbf/article/issue/2026_5", journal)
        self.assertEqual(1, len(items))
        self.assertEqual("https://ysks.bgrimm.cn/ysjsksbf/article/abstract/20260427004?st=article_issue", items[0]["url"])

    def test_enrich_abstracts_skips_existing_and_respects_limit(self):
        rows = [
            {"url": "u1", "abstract": None},
            {"url": "u2", "abstract": "已有摘要"},
            {"url": "u3", "abstract": None},
            {"url": "u4", "abstract": None},
        ]
        calls = []
        with patch.object(crawler, "enrich_abstract", side_effect=lambda opener, item, timeout: calls.append(item["url"])):
            crawler.enrich_abstracts(None, rows, 5, 2)
        self.assertEqual(["u1", "u3"], calls)

    def test_enrich_abstract_failure_is_non_fatal(self):
        item = {"journal_key": "g" * 16, "title": "示例文章", "url": "https://example.cn/1", "abstract": None}
        with patch.object(crawler, "read_response", side_effect=OSError("boom")):
            result = crawler.enrich_abstract(None, item, 5)
        self.assertIs(item, result)
        self.assertIsNone(item["abstract"])

    def test_abstract_enrich_options(self):
        self.assertEqual((False, 5), crawler.abstract_enrich_options({"enrich_abstract": "false"}))
        self.assertEqual((False, 5), crawler.abstract_enrich_options({"enrich_abstract": False}))
        self.assertEqual((True, 20), crawler.abstract_enrich_options({"abstract_enrich_limit": "99"}))
        self.assertEqual((True, 5), crawler.abstract_enrich_options({"abstract_enrich_limit": "abc"}))

    def test_collect_latest_issue_skips_enrich_when_disabled(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        record = {"journal_key": key, "journal_name": "示例期刊", "journal_url": "https://example.cn",
                  "external_id": "123", "title": "当期文章", "url": "https://example.cn/1",
                  "authors": "张三", "abstract": None, "doi": None, "year": 2026}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1,
                                  "enrich_abstract": False}}
        with patch.object(crawler, "current_issue_items", return_value=[record]), \
                patch.object(crawler, "enrich_abstracts") as enrich:
            items, warnings, successful = crawler.collect(request, journals)
        enrich.assert_not_called()
        self.assertEqual(1, len(items))
        self.assertEqual(1, successful)

    def test_collect_latest_issue_uses_current_issue(self):
        key = "a" * 16
        journals = {key: {"journal_key": key, "name": "示例期刊", "url": "https://example.cn"}}
        record = {"journal_key": key, "journal_name": "示例期刊", "journal_url": "https://example.cn",
                  "external_id": "123", "title": "当期文章", "url": "https://example.cn/1",
                  "authors": "张三", "abstract": "摘要", "doi": "10.1234/test", "year": 2026}
        request = {"query": "不会匹配", "limit": 1,
                   "parameters": {"journal_keys": [key], "collect_mode": "latest_issue", "per_journal_limit": 1}}
        with patch.object(crawler, "current_issue_items", return_value=[record]):
            items, warnings, successful = crawler.collect(request, journals)
        self.assertEqual(1, len(items))
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)

    def test_manifest_version_bumped_for_issue_browser_and_catalog(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("1.9.5", manifest["package_version"])
        default = manifest["parameters_schema"]["properties"]["journal_keys"]["default"]
        self.assertIn("3c1b46c38f3e14ac", default)

    def test_catalog_includes_sports_studies_issue_browser_entry(self):
        journals = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        entries = [row for row in journals if row["journal_key"] == "3c1b46c38f3e14ac"]
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("体育学研究", entry["name"])
        self.assertEqual("2096-5656", entry["issn"])
        self.assertEqual("32-1881/G8", entry["cn"])
        self.assertEqual("北大核心;CSSCI;AMI核心", entry["core_levels"])
        self.assertEqual("社会科学Ⅱ辑;体育", entry["categories"])
        self.assertIn("来源:官网页面", entry["tags"])
        self.assertEqual("https://ntxb.nipes.cn/tyxyj/njtyxyxbsk/issue/browser", entry["current_url"])
        self.assertEqual("https://ntxb.nipes.cn", entry["link_base"])
        self.assertTrue(re.fullmatch(entry["article_link_regex"], "/tyxyj/njtyxyxbsk/article/abstract/20260402"))
        self.assertEqual(173, len(journals))


def article_block(number, title=None):
    return (
        f'<li class="article_line"><input class="article_issue_fl" name="FileNO" '
        f'id="FileNO2026{number:04d}" value="2026{number:04d}" type="checkbox">'
        f'<div class="article_des article_issue_fl"><div class="article_title">'
        f'<a href="publisher/article/abstract/2026{number:04d}" target="_blank">{title or "测试文章"}{number}</a>'
        f'</div><p class="article_author">作者{number}</p>'
        f'<p class="article_position">2026, 48(5):{number}-{number + 1}.</p>'
        f'<div class="abstract_body"><p><b>摘要:</b></p></div></div></li>'
    )


def issue_page(count, links="", noise=None, title="示例期刊 2026年第5期"):
    blocks = "".join(article_block(number) for number in range(1, count + 1))
    blocks += noise or ""
    return (
        f"<html><head><base href=\"/\"><title>{title}</title></head><body><div class=\"article_issue_bd\"><ul>"
        f'<li><h5><span>&gt</span>目录</h5></li>{blocks}</ul>{links}</div></body></html>'
    )


class IssueParsingTests(unittest.TestCase):
    JOURNAL = {"journal_key": "h" * 16, "name": "示例期刊", "url": "https://example.cn"}
    ISSUE_URL = "https://example.cn/publisher/article/issue/2026_5"

    def test_cover_and_contents_filter_is_not_reported_as_loss(self):
        noise = (
            '<li class="article_line"><input id="FileNO202605041" type="checkbox">'
            '<div class="article_title"><a href="publisher/article/abstract/202605041">目录</a></div></li>'
            '<li class="article_line"><input id="FileNO202605042" type="checkbox">'
            '<div class="article_title"><a href="publisher/article/abstract/202605042">封面</a></div></li>'
        )
        page = issue_page(40, noise=noise)
        items = crawler.parse_new_issue_page(page, self.ISSUE_URL, self.JOURNAL)
        self.assertEqual(40, len(items))
        self.assertEqual([], crawler.issue_drop_report(page, items))
        warnings = []
        crawler.audit_issue_page(page, items, self.JOURNAL, warnings)
        self.assertEqual([], warnings)

    def test_real_unparsed_entry_is_reported(self):
        noise = (
            '<li class="article_line"><input id="FileNO20260999" type="checkbox">'
            '<div class="article_title">缺少链接的文章</div></li>'
        )
        page = issue_page(2, noise=noise)
        items = crawler.parse_new_issue_page(page, self.ISSUE_URL, self.JOURNAL)
        self.assertEqual(2, len(items))
        lost = crawler.issue_drop_report(page, items)
        self.assertEqual(["20260999"], [entry["external_id"] for entry in lost])
        warnings = []
        crawler.audit_issue_page(page, items, self.JOURNAL, warnings)
        self.assertEqual(1, len(warnings))
        self.assertIn("未解析", warnings[0])

    def test_title_container_tag_is_not_limited_to_div(self):
        page = (
            '<li class="article_line"><p class="article_title"><a href="publisher/article/abstract/77">段落标题文章</a></p>'
            '<p class="article_author">作者</p><p class="article_position">2026, 48(5):1-2.</p></li>'
        )
        items = crawler.parse_new_issue_page(page, self.ISSUE_URL, self.JOURNAL)
        self.assertEqual(1, len(items))
        self.assertEqual("段落标题文章", items[0]["title"])

    def test_pager_requires_same_issue_and_page_parameter(self):
        page = issue_page(
            1,
            links=(
                '<a href="/publisher/article/issue/2026_5?page=2">2</a>'
                '<a href="/publisher/article/issue/2026_4?page=2">上一期</a>'
                '<a href="/publisher/article/issue/2026_5?year_id=2025&amp;page=2">年份</a>'
                '<select name="issue"><option value="2026_4">2026_4</option></select>'
            ),
        )
        self.assertEqual(
            [(2, "https://example.cn/publisher/article/issue/2026_5?page=2")],
            crawler.discover_issue_pages(page, self.ISSUE_URL),
        )

    def test_pager_number_cap_is_twenty(self):
        links = "".join(
            f'<a href="/publisher/article/issue/2026_5?page={number}">{number}</a>' for number in range(2, 32)
        )
        pages = crawler.discover_issue_pages(issue_page(1, links=links), self.ISSUE_URL)
        self.assertEqual(19, len(pages))
        self.assertEqual(20, pages[-1][0])

    def test_path_suffix_pager_is_supported(self):
        page = issue_page(1, links='<a href="/publisher/article/issue/2026_5/2">2</a>')
        self.assertEqual(
            [(2, "https://example.cn/publisher/article/issue/2026_5/2")],
            crawler.discover_issue_pages(page, self.ISSUE_URL),
        )

    def test_current_issue_without_pager_makes_one_request(self):
        journal = dict(self.JOURNAL, current_url=self.ISSUE_URL)
        page = issue_page(3, links='<a href="/publisher/article/issue/2026_4">上一期</a>')
        with patch.object(crawler, "read_response", return_value=(page, self.ISSUE_URL)) as mocked:
            items = crawler.current_issue_items(None, journal, 5)
        self.assertEqual(3, len(items))
        self.assertEqual(1, mocked.call_count)

    def test_current_issue_follows_same_issue_pages(self):
        journal = dict(self.JOURNAL, current_url=self.ISSUE_URL)
        first = issue_page(2, links='<a href="/publisher/article/issue/2026_5?page=2">2</a>')
        second = issue_page(2, title="示例期刊 2026年第5期")
        second = second.replace("20260001", "20260011").replace("20260002", "20260012")
        with patch.object(crawler, "read_response", side_effect=[(first, self.ISSUE_URL), (second, self.ISSUE_URL)]) as mocked:
            warnings = []
            items = crawler.current_issue_items(None, journal, 5, warnings)
        self.assertEqual(4, len(items))
        self.assertEqual(2, mocked.call_count)
        self.assertEqual(1, len(warnings))
        self.assertIn("当期分页跟随 1 页", warnings[0])

    def test_current_issue_stops_when_page_adds_nothing(self):
        journal = dict(self.JOURNAL, current_url=self.ISSUE_URL)
        first = issue_page(1, links=(
            '<a href="/publisher/article/issue/2026_5?page=2">2</a>'
            '<a href="/publisher/article/issue/2026_5?page=3">3</a>'
        ))
        with patch.object(crawler, "read_response", side_effect=[(first, self.ISSUE_URL), (first, self.ISSUE_URL)]) as mocked:
            items = crawler.current_issue_items(None, journal, 5)
        self.assertEqual(1, len(items))
        self.assertEqual(2, mocked.call_count)

    def test_current_issue_stops_when_issue_marker_changes(self):
        journal = dict(self.JOURNAL, current_url=self.ISSUE_URL)
        first = issue_page(1, links='<a href="/publisher/article/issue/2026_5?page=2">2</a>')
        wrong = issue_page(1, title="示例期刊 2026年第4期")
        with patch.object(crawler, "read_response", side_effect=[(first, self.ISSUE_URL), (wrong, self.ISSUE_URL)]) as mocked:
            items = crawler.current_issue_items(None, journal, 5)
        self.assertEqual(1, len(items))
        self.assertEqual(2, mocked.call_count)

    def test_issue_browser_resolves_newest_issue(self):
        payload = {"years": [
            {"year_id": "2025", "issues": [
                {"issue_id": "6", "issue_url": "njtyxyxbsk/article/issue/2025_6"},
            ]},
            {"year_id": "2026", "issues": [
                {"issue_id": "3", "issue_url": "njtyxyxbsk/article/issue/2026_3"},
                {"issue_id": "4", "issue_url": "njtyxyxbsk/article/issue/2026_4"},
            ]},
        ]}
        browser = (
            '<base href="/tyxyj/"><script>var strAllIssueJson='
            + json.dumps(json.dumps(payload, ensure_ascii=False), ensure_ascii=False)
            + ';</script>'
        )
        self.assertEqual(
            "https://ntxb.nipes.cn/tyxyj/njtyxyxbsk/article/issue/2026_4",
            crawler.issue_browser_latest(browser, "https://ntxb.nipes.cn/tyxyj/njtyxyxbsk/issue/browser"),
        )

    def test_issue_browser_ignores_invalid_json(self):
        self.assertIsNone(crawler.issue_browser_latest("<html></html>", self.ISSUE_URL))
        self.assertIsNone(crawler.issue_browser_latest('var strAllIssueJson="{bad";', self.ISSUE_URL))

    def test_current_issue_follows_issue_browser(self):
        journal = dict(self.JOURNAL, current_url="https://example.cn/publisher/issue/browser")
        payload = {"years": [{"year_id": "2026", "issues": [
            {"issue_id": "5", "issue_url": "publisher/article/issue/2026_5"},
        ]}]}
        browser = (
            '<base href="/"><script>var strAllIssueJson='
            + json.dumps(json.dumps(payload, ensure_ascii=False), ensure_ascii=False)
            + ';</script>'
        )
        issue = issue_page(2)
        with patch.object(
            crawler, "read_response",
            side_effect=[(browser, journal["current_url"]), (issue, self.ISSUE_URL)],
        ) as mocked:
            items = crawler.current_issue_items(None, journal, 5)
        self.assertEqual(2, len(items))
        self.assertEqual(2, mocked.call_count)
        self.assertEqual(self.ISSUE_URL, mocked.call_args.args[1].full_url)

    def test_legacy_issue_page_uses_page_links_and_page_count(self):
        journal = {"journal_key": "i" * 16, "name": "环境科学", "url": "https://www.hjkx.ac.cn/",
                   "current_url": "https://www.hjkx.ac.cn/ch/reader/issue_list.aspx?year_id=2026&quarter_id=11"}
        first = (
            '<span id="PageCount">2</span><table><tr><td>'
            '<a href="view_abstract.aspx?file_no=1">文章一</a></td></tr></table>'
            '<a href="issue_list.aspx?year_id=2026&amp;quarter_id=11&amp;page=2">2</a>'
        )
        second = (
            '<table><tr><td><a href="view_abstract.aspx?file_no=2">文章二</a></td></tr></table>'
        )
        with patch.object(crawler, "read_response", side_effect=[(first, journal["current_url"]), (second, journal["current_url"])]) as mocked:
            items = crawler.current_issue_items(None, journal, 5)
        self.assertEqual(2, len(items))
        self.assertEqual(2, mocked.call_count)
        self.assertEqual("https://www.hjkx.ac.cn/ch/reader/issue_list.aspx?year_id=2026&quarter_id=11&page=2",
                         mocked.call_args.args[1].full_url)

    def test_page_counter_widget_is_not_pagination(self):
        page = '<span id="PageCounterDWR">7</span><a href="/publisher/article/issue/2026_4">上一期</a>'
        self.assertEqual([], crawler.discover_issue_pages(page, self.ISSUE_URL))


if __name__ == "__main__":
    unittest.main()
