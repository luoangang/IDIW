import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cnki_cbpt_crawler", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crawler)


class CbptCrawlerTests(unittest.TestCase):
    def test_noise_titles_are_filtered(self):
        self.assertTrue(crawler.is_noise_title("欢迎订阅2027年《中国骨与关节杂志》(月刊)"))
        self.assertTrue(crawler.is_noise_title("本刊被日本科学技术振兴机构数据库收录的公告"))
        self.assertTrue(crawler.is_noise_title("稿约"))
        self.assertTrue(crawler.is_noise_title("编后"))
        self.assertTrue(crawler.is_noise_title("西北五省（区）图书馆第十八次科学讨论会顺利召开"))
        self.assertTrue(crawler.is_noise_title("宁夏回族自治区图书馆“阅游宁夏”项目入选全国第二批公共文化服务高质量发展典型案例"))
        self.assertFalse(crawler.is_noise_title("城乡居民大病保险制度实施困境与完善路径"))
        parser = crawler.PaperParser()
        parser.feed('''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/NOISE_1"><span>欢迎订阅2027年本刊</span></a></h3><span></span><p>订阅信息。</p></div><div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/REAL_1"><span>一篇真实研究文章</span></a></h3><span>张三;</span><p>真实摘要内容。</p></div>''')
        self.assertEqual(len(parser.papers), 1)
        self.assertEqual(parser.papers[0]["title"], "一篇真实研究文章")

    def test_parses_paper_metadata(self):
        parser = crawler.PaperParser()
        parser.feed('''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/ABC_123456"><span>文章标题</span></a></h3><span>张三;李四;</span><p>完整中文摘要正文。</p><div class="paperInfo"><span class="publish-info">2024 年 01 期</span></div></div>''')
        self.assertEqual(len(parser.papers), 1)
        self.assertEqual(parser.papers[0]["title"], "文章标题")
        self.assertEqual(parser.papers[0]["authors"], "张三;李四;")
        self.assertEqual(parser.papers[0]["abstract"], "完整中文摘要正文。")

    def test_portal_ignores_high_text_snippet_as_abstract(self):
        parser = crawler.PaperParser()
        parser.feed('''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/ABC_123456"><span>文章标题</span></a></h3><span>张三;</span><p class="highText">&lt;正&gt; 截断的正文命中片段</p></div>''')
        self.assertEqual(len(parser.papers), 1)
        self.assertEqual(parser.papers[0]["abstract"], "")

    def test_portal_ignores_plain_paragraph_before_authors(self):
        parser = crawler.PaperParser()
        parser.feed('''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/ABC_123456"><span>文章标题</span></a></h3><p>作者之前的段落不算摘要</p><span>张三;</span><p>作者之后的完整摘要。</p></div>''')
        self.assertEqual(len(parser.papers), 1)
        self.assertEqual(parser.papers[0]["abstract"], "作者之后的完整摘要。")

    def test_portal_empty_author_span_still_allows_abstract(self):
        parser = crawler.PaperParser()
        parser.feed('''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/ABC_123456"><span>一篇真实研究文章</span></a></h3><span></span><p>真实摘要内容。</p></div>''')
        self.assertEqual(len(parser.papers), 1)
        self.assertIsNone(parser.papers[0]["authors"] or None)
        self.assertEqual(parser.papers[0]["abstract"], "真实摘要内容。")

    def test_collect_uses_catalog_and_handles_partial_failure(self):
        journals = {
            "a" * 16: {"name": "期刊甲", "url": "http://hbsb.cbpt.cnki.net"},
            "b" * 16: {"name": "期刊乙", "url": "http://test.cbpt.cnki.net"},
        }
        def fake_page(base_url, query, page, timeout):
            if "test.cbpt" in base_url:
                raise TimeoutError("unavailable")
            return [{"title": "文章标题", "url": "/portal/journal/portal/client/paper/ABC_123456",
                     "authors": "张三;", "abstract": "摘要", "issue": "2024 年 01 期"}]

        with patch.object(crawler, "read_page", side_effect=fake_page):
            items, warnings, successful = crawler.collect(
                {"query": "人工智能", "limit": 2, "parameters": {
                    "journal_keys": ["a" * 16, "b" * 16], "per_journal_limit": 1}}, journals)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["journal_key"], "a" * 16)
        self.assertEqual(successful, 1)
        self.assertEqual(len(warnings), 1)

    def test_bundled_catalog_is_restricted_to_cbpt(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 846)
        self.assertEqual(len({row["journal_key"] for row in rows}), len(rows))
        self.assertTrue(all(row["template_group"] == "cnki_cbpt" for row in rows))

    def test_bundled_lanzhou_social_sciences_entry(self):
        rows = json.loads((ROOT / "journals.json").read_text(encoding="utf-8"))
        entry = next(row for row in rows if row["journal_key"] == "fead91fc2a60528d")
        self.assertEqual("兰州大学学报（社会科学版）", entry["name"])
        self.assertEqual("1000-2804", entry["issn"])
        self.assertEqual("62-1029/C", entry["cn"])
        self.assertEqual("https://ldsk.cbpt.cnki.net", entry["url"])
        self.assertEqual(
            "https://ldsk.chinajournal.net.cn/WKH3/WebPublication/index.aspx?mid=LDSK",
            entry["current_url"])
        self.assertEqual("北大核心;来源期刊", entry["core_levels"])
        self.assertEqual(15, entry["probe_items"])
        self.assertEqual(
            "丰富发展马克思主义建党学说的经典文献——学习《习近平党建文选》第一卷、第二卷",
            entry["probe_first_title"])

    def test_legacy_www_host_uses_valid_certificate_hostname(self):
        key = "c" * 16
        journals = {key: {"name": "示例期刊", "url": "http://www.styb.cbpt.cnki.net"}}
        with patch.object(crawler, "read_page", return_value=[]) as mocked:
            _, warnings, successful = crawler.collect(
                {"query": "人工智能", "limit": 1, "parameters": {"journal_keys": [key]}}, journals)
        self.assertEqual(successful, 1)
        self.assertEqual(warnings, [])
        self.assertEqual(mocked.call_args.args[0], "https://styb.cbpt.cnki.net")

    def test_current_issue_url(self):
        self.assertEqual(
            "https://hbsb.cbpt.cnki.net/portal/journal/portal/client/paper_list/type_benqi",
            crawler.current_issue_url("https://hbsb.cbpt.cnki.net"),
        )

    def test_read_current_issue_follows_page_links(self):
        first = '''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/first1"><span>文章一</span></a></h3><span>张三;</span><span class="publish-info">2026 年 06 期</span></div>
        <a href="/portal/journal/portal/client/paperPage_list?pageNum=2&amp;yearId=y&amp;issueId=i&amp;year=2026&amp;issue=06">下一页</a>'''
        second = '''<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/second2"><span>文章二</span></a></h3><span>李四;</span><span class="publish-info">2026 年 06 期</span></div>'''
        with patch.object(crawler, "fetch_html", side_effect=[first, second]) as mocked:
            papers = crawler.read_current_issue("https://hbsb.cbpt.cnki.net", 20)
        self.assertEqual(["文章一", "文章二"], [paper["title"] for paper in papers])
        self.assertEqual(2, mocked.call_count)
        self.assertIn("pageNum=2", mocked.call_args.args[0])

    @staticmethod
    def _paper(number, label):
        return (f'<div class="paperBox"><h3><a href="/portal/journal/portal/client/paper/{label}{number}">'
                f'<span>{label}第{number}条</span></a></h3><span>张三;</span>'
                f'<span class="publish-info">2026 年 06 期</span></div>')

    @staticmethod
    def _pager(number, year_id="y", issue_id="i"):
        return (f'<a href="/portal/journal/portal/client/paperPage_list?pageNum={number}'
                f'&amp;yearId={year_id}&amp;issueId={issue_id}&amp;year=2026&amp;issue=06">{number}</a>')

    def test_current_issue_merges_every_pager_page(self):
        first = "".join(self._paper(n, "first") for n in (1, 2)) + "".join(
            self._pager(n) for n in (2, 3))
        second = self._paper(3, "second")
        third = self._paper(4, "third")
        warnings = []
        with patch.object(crawler, "fetch_html", side_effect=[first, second, third]) as mocked:
            papers = crawler.read_current_issue("https://wsyj.cbpt.cnki.net", 20,
                                                max_pages=20, warn=warnings.append)
        self.assertEqual(["first第1条", "first第2条", "second第3条", "third第4条"],
                         [paper["title"] for paper in papers])
        self.assertEqual(3, mocked.call_count)
        self.assertEqual([], warnings)

    def test_current_issue_stops_when_following_page_has_other_issue(self):
        # Page 2 carries the first-screen identity; page 3 belongs to a stale
        # issue, so reading must stop there and report a warning.
        first = self._paper(1, "first") + \
            self._pager(2, year_id="Y1", issue_id="I1") + \
            self._pager(3, year_id="Y2", issue_id="I2")
        second = self._paper(2, "second") + self._pager(3, year_id="Y2", issue_id="I2")
        warnings = []
        with patch.object(crawler, "fetch_html", side_effect=[first, second]) as mocked:
            papers = crawler.read_current_issue("https://wsyj.cbpt.cnki.net", 20,
                                                max_pages=20, warn=warnings.append)
        self.assertEqual(["first第1条", "second第2条"], [paper["title"] for paper in papers])
        self.assertEqual(2, mocked.call_count)
        self.assertEqual(1, len(warnings))
        self.assertIn("yearId/issueId", warnings[0])
        self.assertIn("停止翻页", warnings[0])

    def test_current_issue_without_pager_reads_single_page(self):
        first = self._paper(1, "only")
        warnings = []
        with patch.object(crawler, "fetch_html", return_value=first) as mocked:
            papers = crawler.read_current_issue("https://hnjg.cbpt.cnki.net", 20,
                                                max_pages=20, warn=warnings.append)
        self.assertEqual(["only第1条"], [paper["title"] for paper in papers])
        self.assertEqual(1, mocked.call_count)
        self.assertEqual([], warnings)

    def test_current_issue_warns_when_pager_is_js_only(self):
        first = self._paper(1, "only") + \
            '<div class="page"><span onclick="toPage(2)">paperPage_list</span></div>'
        warnings = []
        with patch.object(crawler, "fetch_html", return_value=first) as mocked:
            papers = crawler.read_current_issue("https://wsyj.cbpt.cnki.net", 20,
                                                max_pages=20, warn=warnings.append)
        self.assertEqual(1, len(papers))
        self.assertEqual(1, mocked.call_count)
        self.assertEqual(1, len(warnings))
        self.assertIn("paperPage_list", warnings[0])
        self.assertIn("JS", warnings[0])

    def test_current_issue_single_page_pager_is_not_a_js_warning(self):
        # 征信-style issue: a server-rendered pager that only links pageNum=1.
        first = self._paper(1, "only") + \
            '<a href="/portal/journal/portal/client/paperPage_list?pageNum=1&amp;yearId=y&amp;issueId=i">1</a>' + \
            '<script>var url = "/paperPage_list";</script>'
        warnings = []
        with patch.object(crawler, "fetch_html", return_value=first) as mocked:
            papers = crawler.read_current_issue("https://hnjg.cbpt.cnki.net", 20,
                                                max_pages=20, warn=warnings.append)
        self.assertEqual(1, len(papers))
        self.assertEqual(1, mocked.call_count)
        self.assertEqual([], warnings)

    def test_current_issue_respects_max_pages_cap(self):
        first = self._paper(1, "first") + "".join(
            self._pager(n) for n in range(2, 8))
        second = self._paper(2, "page")
        third = self._paper(3, "page")
        warnings = []
        with patch.object(crawler, "fetch_html", side_effect=[first, second, third]) as mocked:
            papers = crawler.read_current_issue("https://wsyj.cbpt.cnki.net", 20,
                                                max_pages=3, warn=warnings.append)
        self.assertEqual(3, mocked.call_count)  # first page + pages 2 and 3
        self.assertEqual(["first第1条", "page第2条", "page第3条"],
                         [paper["title"] for paper in papers])
        self.assertEqual([], warnings)
        self.assertTrue(all("pageNum=4" not in call.args[0] for call in mocked.call_args_list))

    def test_current_issue_pager_last_page_caps_below_max_pages(self):
        first = self._paper(1, "first") + "".join(self._pager(n) for n in (2, 3))
        second = self._paper(2, "page")
        third = self._paper(3, "page")
        warnings = []
        with patch.object(crawler, "fetch_html", side_effect=[first, second, third]) as mocked:
            papers = crawler.read_current_issue("https://wsyj.cbpt.cnki.net", 20,
                                                max_pages=40, warn=warnings.append)
        self.assertEqual(3, mocked.call_count)
        self.assertEqual(3, len(papers))
        self.assertEqual([], warnings)

    def test_collect_latest_issue_ignores_query_and_limits_results(self):
        key = "d" * 16
        journals = {key: {"name": "示例期刊", "url": "http://hbsb.cbpt.cnki.net"}}
        records = [
            {"title": "最新一", "url": "/portal/journal/portal/client/paper/aaaaaa1",
             "authors": "张三;", "abstract": "", "issue": "2026 年 06 期"},
            {"title": "最新二", "url": "/portal/journal/portal/client/paper/aaaaaa2",
             "authors": "李四;", "abstract": "", "issue": "2026 年 06 期"},
        ]
        with patch.object(crawler, "read_current_issue", return_value=records) as mocked:
            items, warnings, successful = crawler.collect(
                {"query": "不存在的关键词", "limit": 1,
                 "parameters": {"journal_keys": [key], "collect_mode": "latest_issue"}},
                journals)
        self.assertEqual(1, len(items))
        self.assertEqual("最新一", items[0]["title"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual("https://hbsb.cbpt.cnki.net", mocked.call_args.args[0])

    def test_manifest_exposes_collect_mode(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        mode = manifest["parameters_schema"]["properties"]["collect_mode"]
        self.assertEqual(["keywords", "latest_issue"], mode["enum"])
        self.assertEqual("keywords", mode["default"])

    def test_wkd_current_parses_paper_digest_links(self):
        page = '<a href="../WebPublication/paperDigest.aspx?paperID=abc12345">真实文章标题示例文章</a>'
        with patch.object(crawler, "fetch_html", return_value=page):
            records = crawler.read_wkd_current(
                "https://x.cbpt.cnki.net/wki/WebPublication/index.aspx?mid=X", 20)
        self.assertEqual(1, len(records))
        self.assertEqual("abc12345", records[0]["external_id"])
        item = crawler.paper_item("k", {"name": "示例期刊", "url": "https://x.cbpt.cnki.net"},
                                  "https://x.cbpt.cnki.net", records[0])
        self.assertIsNotNone(item)
        self.assertEqual("abc12345", item["external_id"])

    def test_wkd_current_parses_sectioned_list_markup(self):
        page = (
            '<h1>栏目一</h1><ul class="column_contbox_zxlist">'
            '<li> <h3> <a href="../WebPublication/paperDigest.aspx?paperID=7d64b16c-d8f5-4028-bd7b-1d4e29ae9089" '
            'target="_blank" >丰富发展马克思主义建党学说的经典文献示例</a></h3>'
            '<samp>王炳林;廖松涛;</samp><span>2026年05期 v.54;No.261 5-13页  '
            '<a href="../WebPublication/paperDigest.aspx?paperID=7d64b16c-d8f5-4028-bd7b-1d4e29ae9089" '
            'target="_blank" >[查看摘要]</a></span></li>'
            '<li class="gray"><h3> <a href="../WebPublication/paperDigest.aspx?paperID=9bd2c33b-c45d-42cc-9494-87c0edc2c82f" '
            'target="_blank" >习近平党建思想开创历史前进的逻辑样态</a></h3>'
            '<samp>汤荣光;</samp><span>2026年05期 v.54;No.261 14-23页  '
            '<a href="../WebPublication/paperDigest.aspx?paperID=9bd2c33b-c45d-42cc-9494-87c0edc2c82f" '
            'target="_blank" >[查看摘要]</a></span></li></ul>')
        with patch.object(crawler, "fetch_html", return_value=page):
            records = crawler.read_wkd_current(
                "https://ldsk.chinajournal.net.cn/WKH3/WebPublication/index.aspx?mid=LDSK", 20)
        self.assertEqual(2, len(records))
        self.assertEqual("7d64b16c-d8f5-4028-bd7b-1d4e29ae9089", records[0]["external_id"])
        self.assertEqual("王炳林,廖松涛,", records[0]["authors"])
        self.assertEqual("2026年05期", records[0]["issue"])
        self.assertTrue(records[0]["url"].endswith("paperID=7d64b16c-d8f5-4028-bd7b-1d4e29ae9089"))

    def test_extract_wk_abstract_from_digest_paragraph(self):
        page = ('<ul><li>作者</li></ul>'
                '<p id="digest">\n<strong>摘要(Abstract)： </strong>\n</p>\n'
                '<p>\n目的 研究示例。<strong>方法</strong> 抽样。</p>'
                '<p><strong>关键词(KeyWords)：</strong>测试</p>')
        self.assertEqual("目的 研究示例。 方法 抽样。", crawler.extract_wk_abstract(page))
        self.assertIsNone(crawler.extract_wk_abstract("<html><body>无摘要页面</body></html>"))

    def test_abstract_placeholder_empty_and_title_are_rejected(self):
        self.assertIsNone(crawler.clean_abstract(None))
        self.assertIsNone(crawler.clean_abstract(""))
        self.assertIsNone(crawler.clean_abstract("   "))
        self.assertIsNone(crawler.clean_abstract("~~"))
        self.assertIsNone(crawler.clean_abstract(" ～～ "))
        self.assertIsNone(crawler.clean_abstract("……"))
        self.assertIsNone(crawler.clean_abstract("无"))
        self.assertIsNone(crawler.clean_abstract("文章标题", "文章标题"))
        self.assertEqual("正常摘要。", crawler.clean_abstract("  正常摘要。 ", "文章标题"))
        self.assertEqual("正文起点。", crawler.clean_abstract("<正> 正文起点。", "文章标题"))
        self.assertIsNone(crawler.clean_abstract("<正>~~", "公告标题"))

    def test_wk_latest_issue_enriches_abstract_with_shared_session(self):
        key = "e" * 16
        journals = {key: {
            "name": "WK 期刊", "url": "https://x.cbpt.cnki.net",
            "current_url": "https://x.cbpt.cnki.net/WKA/WebPublication/index.aspx?mid=x",
        }}
        list_page = ('<h3><a href="../WebPublication/paperDigest.aspx?paperID=abc12345">'
                     '真实文章标题示例文章</a></h3>')
        detail_page = ('<p id="digest"><strong>摘要(Abstract)： </strong></p>'
                       '<p>这是一段完整的匿名会话摘要。</p>'
                       '<p><strong>关键词(KeyWords)：</strong>测试</p>')
        opener = object()
        calls = []

        def fake_fetch(url, timeout, opener=None):
            calls.append((url, opener))
            return list_page if "index.aspx" in url else detail_page

        with patch.object(crawler, "make_opener", return_value=opener), \
                patch.object(crawler, "fetch_html", side_effect=fake_fetch), \
                patch.object(crawler.time, "sleep") as sleeper:
            items, warnings, successful = crawler.collect(
                {"query": "x", "limit": 5, "parameters": {
                    "journal_keys": [key], "collect_mode": "latest_issue",
                    "enrich_abstract": True, "abstract_enrich_limit": 5}},
                journals)
        self.assertEqual(1, len(items))
        self.assertEqual("这是一段完整的匿名会话摘要。", items[0]["abstract"])
        self.assertEqual([], warnings)
        self.assertEqual(1, successful)
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call[1] is opener for call in calls))
        sleeper.assert_not_called()

    def test_wk_captcha_shell_is_warned_and_not_bypassed(self):
        key = "f" * 16
        journals = {key: {
            "name": "WK 期刊", "url": "https://x.cbpt.cnki.net",
            "current_url": "https://x.cbpt.cnki.net/WKA/WebPublication/index.aspx?mid=x",
        }}
        list_page = "".join(
            f'<h3><a href="../WebPublication/paperDigest.aspx?paperID=abc1234{n}">'
            f'真实文章标题示例文章{n}</a></h3>' for n in (1, 2))
        captcha_page = ('<form name="form1" method="post" action="showValidateCode.aspx">'
                        '<img src="ValidateCodeZH.aspx" id="pic">请填写验证码</form>')
        detail_calls = []

        def fake_fetch(url, timeout, opener=None):
            if "paperDigest.aspx" in url:
                detail_calls.append(url)
                return captcha_page
            return list_page

        with patch.object(crawler, "make_opener", return_value=object()), \
                patch.object(crawler, "fetch_html", side_effect=fake_fetch), \
                patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(
                {"query": "x", "limit": 5, "parameters": {
                    "journal_keys": [key], "collect_mode": "latest_issue"}},
                journals)
        self.assertEqual(2, len(items))
        self.assertEqual([None, None], [item["abstract"] for item in items])
        self.assertEqual(1, successful)
        self.assertEqual(1, len(detail_calls))
        self.assertTrue(any("validate code shell" in warning for warning in warnings))

    def test_enrich_switch_limit_and_interval(self):
        key = "a1b2c3d4e5f60718"
        journals = {key: {
            "name": "WK 期刊", "url": "https://x.cbpt.cnki.net",
            "current_url": "https://x.cbpt.cnki.net/WKA/WebPublication/index.aspx?mid=x",
        }}
        list_page = "".join(
            f'<h3><a href="../WebPublication/paperDigest.aspx?paperID=abc1234{n}">'
            f'真实文章标题示例文章{n}</a></h3>' for n in (1, 2, 3))
        detail_page = ('<p id="digest"><strong>摘要(Abstract)： </strong></p>'
                       '<p>详情页摘要内容。</p>')

        def run(parameters, detail_calls, sleeper):
            def fake_fetch(url, timeout, opener=None):
                if "paperDigest.aspx" in url:
                    detail_calls.append(url)
                    return detail_page
                return list_page
            with patch.object(crawler, "make_opener", return_value=object()), \
                    patch.object(crawler, "fetch_html", side_effect=fake_fetch), \
                    patch.object(crawler.time, "sleep", side_effect=sleeper):
                return crawler.collect(
                    {"query": "x", "limit": 5, "parameters": {
                        "journal_keys": [key], "collect_mode": "latest_issue",
                        **parameters}}, journals)

        detail_calls, sleeps = [], []
        items, warnings, _ = run({"enrich_abstract": False}, detail_calls, sleeps.append)
        self.assertEqual(0, len(detail_calls))
        self.assertEqual([None, None, None], [item["abstract"] for item in items])
        self.assertEqual([], sleeps)

        detail_calls, sleeps = [], []
        items, _, _ = run({"abstract_enrich_limit": 0}, detail_calls, sleeps.append)
        self.assertEqual(0, len(detail_calls))
        self.assertEqual([], sleeps)

        detail_calls, sleeps = [], []
        items, _, _ = run({"abstract_enrich_limit": 2}, detail_calls, sleeps.append)
        self.assertEqual(2, len(detail_calls))
        self.assertEqual(["详情页摘要内容。", "详情页摘要内容。", None],
                         [item["abstract"] for item in items])
        self.assertEqual(1, len(sleeps))
        self.assertTrue(0.5 <= sleeps[0] <= 1.0)

    def test_wk_detail_failure_is_non_fatal(self):
        key = "b1c2d3e4f5061728"
        journals = {key: {
            "name": "WK 期刊", "url": "https://x.cbpt.cnki.net",
            "current_url": "https://x.cbpt.cnki.net/WKA/WebPublication/index.aspx?mid=x",
        }}
        list_page = ('<h3><a href="../WebPublication/paperDigest.aspx?paperID=abc12345">'
                     '真实文章标题示例文章</a></h3>')

        def fake_fetch(url, timeout, opener=None):
            if "paperDigest.aspx" in url:
                raise TimeoutError("detail timeout")
            return list_page

        with patch.object(crawler, "make_opener", return_value=object()), \
                patch.object(crawler, "fetch_html", side_effect=fake_fetch), \
                patch.object(crawler.time, "sleep"):
            items, warnings, successful = crawler.collect(
                {"query": "x", "limit": 5, "parameters": {
                    "journal_keys": [key], "collect_mode": "latest_issue"}},
                journals)
        self.assertEqual(1, len(items))
        self.assertIsNone(items[0]["abstract"])
        self.assertEqual(1, successful)
        self.assertTrue(any("abstract detail failed" in warning for warning in warnings))

    def test_manifest_exposes_abstract_enrichment(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("1.12.7", manifest["package_version"])
        properties = manifest["parameters_schema"]["properties"]
        self.assertEqual("boolean", properties["enrich_abstract"]["type"])
        self.assertTrue(properties["enrich_abstract"]["default"])
        limit = properties["abstract_enrich_limit"]
        self.assertEqual("integer", limit["type"])
        self.assertEqual(0, limit["minimum"])
        self.assertEqual(10, limit["maximum"])
        self.assertEqual(5, limit["default"])

    def test_manifest_exposes_max_pages_per_journal(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        pages = manifest["parameters_schema"]["properties"]["max_pages_per_journal"]
        self.assertEqual("integer", pages["type"])
        self.assertEqual(1, pages["minimum"])
        self.assertEqual(40, pages["maximum"])
        self.assertEqual(20, pages["default"])

    def test_collect_passes_max_pages_to_current_issue(self):
        key = "a1b2c3d4e5f60718"
        journals = {key: {"name": "示例期刊", "url": "http://hbsb.cbpt.cnki.net"}}
        with patch.object(crawler, "read_current_issue", return_value=[]) as mocked:
            crawler.collect(
                {"query": "x", "limit": 1, "parameters": {
                    "journal_keys": [key], "collect_mode": "latest_issue",
                    "max_pages_per_journal": 7}},
                journals)
        self.assertEqual(7, mocked.call_args.args[2])
        self.assertTrue(callable(mocked.call_args.args[3]))

    def test_collect_clamps_and_rejects_bad_page_budget(self):
        key = "a1b2c3d4e5f60718"
        journals = {key: {"name": "示例期刊", "url": "http://hbsb.cbpt.cnki.net"}}
        with patch.object(crawler, "read_current_issue", return_value=[]) as mocked:
            crawler.collect(
                {"query": "x", "limit": 1, "parameters": {
                    "journal_keys": [key], "collect_mode": "latest_issue",
                    "max_pages_per_journal": 90}},
                journals)
        self.assertEqual(40, mocked.call_args.args[2])
        with self.assertRaises(ValueError):
            crawler.collect(
                {"query": "x", "limit": 1, "parameters": {
                    "journal_keys": [key], "collect_mode": "latest_issue",
                    "max_pages_per_journal": "many"}},
                journals)



if __name__ == "__main__":
    unittest.main()
