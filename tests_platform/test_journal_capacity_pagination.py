import unittest
from unittest.mock import patch

from crawler_packages.academic.cnki_cbpt import crawler as cbpt


class JournalCapacityPaginationTests(unittest.TestCase):
    def test_cbpt_parser_tolerates_valueless_html_attributes(self):
        parser = cbpt.PaperParser()
        parser.feed('<div class><div class="paperBox"><h3><a href="/client/paper/record123">Title</a></h3></div></div>')
        self.assertEqual("Title", parser.papers[0]["title"])

    def test_cbpt_continues_past_seven_pages_when_some_rows_are_invalid(self):
        pages = []

        def page(_base, _query, number, _timeout):
            pages.append(number)
            return [
                {"url": f"/client/paper/record{number:02d}{index:03d}",
                 "title": f"研究论文 {number}-{index}", "authors": "作者", "abstract": "摘要", "issue": "2026"}
                for index in range(9)
            ]

        request = {"query": "研究", "limit": 70,
                   "parameters": {"journal_keys": ["sample"], "per_journal_limit": 70, "timeout_seconds": 5}}
        journal = {"journal_key": "sample", "name": "测试期刊", "url": "https://sample.cbpt.cnki.net"}
        with patch.object(cbpt, "read_page", side_effect=page):
            items, warnings, successful = cbpt.collect(request, {"sample": journal})
        self.assertEqual(70, len(items))
        self.assertEqual(1, successful)
        self.assertEqual([], warnings)
        self.assertEqual(list(range(1, 9)), pages)


if __name__ == "__main__":
    unittest.main()
