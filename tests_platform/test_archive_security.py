import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from crawler_platform.api import _safe_extract
from crawler_platform.protocol import ProtocolError


class ArchiveSecurityTests(unittest.TestCase):
    def test_regular_package_is_extracted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "package.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("package/manifest.json", "{}")
            package = _safe_extract(archive, root / "out")
            self.assertEqual("{}", (package / "manifest.json").read_text())

    def test_symbolic_link_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "package.zip"
            link = zipfile.ZipInfo("package/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr(link, "../../outside")
            with self.assertRaisesRegex(ProtocolError, "link or special file"):
                _safe_extract(archive, root / "out")
            self.assertFalse((root / "out" / "package" / "link").exists())


if __name__ == "__main__":
    unittest.main()
