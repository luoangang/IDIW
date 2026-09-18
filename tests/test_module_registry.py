import unittest
from pathlib import Path

from collector.modules.discovery import discover_modules
from collector.sources.discovery import discover_plugins


class ModuleRegistryTests(unittest.TestCase):
    def test_business_modules_and_news_sources_are_registered(self):
        module_result = discover_modules()
        source_result = discover_plugins()

        self.assertEqual({}, module_result.errors)
        self.assertEqual({}, source_result.errors)
        self.assertEqual({"news", "paper", "patent"}, set(module_result.modules))
        self.assertEqual(4, len(source_result.plugins))
        self.assertEqual(
            {"news"},
            {plugin.module for plugin in source_result.plugins.values()},
        )

    def test_source_metadata_exposes_module(self):
        plugins = discover_plugins().plugins
        for plugin in plugins.values():
            self.assertEqual("news", plugin.metadata()["module"])
            self.assertEqual(["search"], plugin.metadata()["supported_modes"])
            self.assertGreaterEqual(plugin.metadata()["contract_version"], 1)
            self.assertEqual("news_resources", plugin.metadata()["storage_table"])
            self.assertTrue(plugin.__class__.__module__.startswith("collector.sources.news."))

    def test_module_metadata_defines_resource_contract(self):
        modules = discover_modules().modules
        self.assertEqual("news_article", modules["news"].resource_type)
        self.assertEqual(("search", "sync"), modules["paper"].supported_modes)
        self.assertEqual(("search", "sync"), modules["patent"].supported_modes)

    def test_source_directories_are_physically_isolated(self):
        source_root = Path(__file__).resolve().parents[1] / "collector" / "sources"
        self.assertTrue((source_root / "news").is_dir())
        self.assertTrue((source_root / "patent").is_dir())
        self.assertTrue((source_root / "paper").is_dir())
        self.assertEqual(
            [],
            [path.name for path in (source_root / "patent").glob("*.py") if path.name != "__init__.py"],
        )
        self.assertEqual(
            [],
            [path.name for path in (source_root / "paper").glob("*.py") if path.name != "__init__.py"],
        )


if __name__ == "__main__":
    unittest.main()
