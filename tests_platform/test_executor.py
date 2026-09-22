import tempfile
import unittest
from pathlib import Path

from crawler_platform.executor import PackageExecutor
from crawler_platform.protocol import ProtocolError, load_manifest


ROOT = Path(__file__).resolve().parents[1]


class ExecutorTests(unittest.TestCase):
    def test_blank_lines_do_not_consume_item_limit(self):
        manifest = load_manifest(ROOT / "crawler_packages" / "baidu_baike")
        sample = (ROOT / "crawler_packages" / "baidu_baike" / "tests" / "items.jsonl").read_text(encoding="utf-8").strip()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "items.jsonl").write_text(f"\n{sample}\n\n{sample}\n", encoding="utf-8")
            valid, rejected = PackageExecutor._read_items(output, manifest, limit=2)
        self.assertEqual(2, len(valid))
        self.assertEqual([], rejected)

    def test_nonblank_records_over_limit_are_rejected(self):
        manifest = load_manifest(ROOT / "crawler_packages" / "baidu_baike")
        sample = (ROOT / "crawler_packages" / "baidu_baike" / "tests" / "items.jsonl").read_text(encoding="utf-8").strip()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "items.jsonl").write_text(f"{sample}\n\n{sample}\n{sample}\n", encoding="utf-8")
            with self.assertRaisesRegex(ProtocolError, "exceed request.limit"):
                PackageExecutor._read_items(output, manifest, limit=2)


if __name__ == "__main__":
    unittest.main()
