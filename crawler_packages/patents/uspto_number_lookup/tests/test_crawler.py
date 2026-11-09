import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import json

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('uspto_lookup', PACKAGE / 'crawler.py')
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)


class LookupTests(unittest.TestCase):
    def test_number_formats_and_duplicates(self):
        self.assertEqual(['7835543', '10244284'], crawler.normalize_numbers('US 7,835,543;US7835543B2\nUS 10,244,284'))
        with self.assertRaises(crawler.LookupError):
            crawler.normalize_numbers('US20200123456A1')

    def test_separate_assignee_and_applicant_and_dates(self):
        raw = '''<title>US-7835543-B2</title><h2>Title</h2><h3>Abstract</h3><p>A &amp; B.</p>
        <p>Assignee: </p><p><span><strong>Hitachi, Ltd.</strong> (Tokyo, JP)</span></p>
        <p>Appl. No.: </p><p>11/739759</p><p>Filed: </p><p>April 25, 2007</p>'''
        item = crawler.parse_detail({'documentId': 'US-7835543-B2', 'patentNumber': '7835543', 'title': 'Object detection method', 'datePublished': '2010-11-16'}, raw)
        self.assertIsNone(item['applicants'])
        self.assertEqual('Hitachi, Ltd. (Tokyo, JP)', item['assignees'])
        self.assertEqual('2007-04-25', item['application_date'])
        self.assertEqual('2010-11-16', item['grant_date'])
        self.assertEqual('A & B.', item['summary'])

    def test_partial_failure_preserves_success_without_committing_cursor(self):
        request = json.loads((PACKAGE / 'tests/request.json').read_text(encoding='utf-8'))
        with patch.object(crawler.Client, 'lookup', side_effect=[{'summary':'abstract', 'application_date':'2007-04-25', 'applicants':None, 'assignees':'Hitachi'}, *[crawler.LookupError('RATE_LIMITED','rate limit',True)] * 5]):
            with tempfile.TemporaryDirectory(dir=PACKAGE / 'tests') as temporary:
                self.assertEqual(0, crawler.run(request, Path(temporary)))
                result = json.loads((Path(temporary) / 'result.json').read_text())
                self.assertEqual('partial', result['status'])
                self.assertEqual(1, result['item_count'])
                self.assertIsNone(result['next_cursor'])

    def test_pct_filed_label_provides_filing_date(self):
        raw = '''<title>US-10162010-B2</title><h2>Title</h2>
        <p>Filed (or PCT Filed): </p><p>November 28, 2014</p>'''
        item = crawler.parse_detail({
            'documentId': 'US-10162010-B2', 'patentNumber': '10162010',
            'title': 'Wireless network based battery management system',
            'datePublished': '2018-12-25',
        }, raw)
        self.assertEqual('2014-11-28', item['application_date'])


if __name__ == '__main__':
    unittest.main()
