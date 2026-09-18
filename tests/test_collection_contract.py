import unittest

from collector.engine import collect_query
from collector.sources.base import CollectionRequest, SourceItem, SourcePlugin


class RecordingPlugin(SourcePlugin):
    module = "news"
    name = "recording"
    label = "Recording"
    table_name = "recording_items"
    resource_type = "news_article"

    def __init__(self):
        self.request = None

    def collect(self, request: CollectionRequest) -> list[SourceItem]:
        self.validate_request(request)
        self.request = request
        return [SourceItem(title="Example", url="https://example.test/1")]


class MemoryStore:
    def __init__(self):
        self.created = None

    def list_settings(self):
        return {"recording": {"enabled": True, "item_limit": 7, "config": {"x": 1}}}

    def create_run(self, query, module_name, mode="search", options=None):
        self.created = (query, module_name, mode, options)
        return 42

    def start_source(self, *args):
        pass

    def write_items(self, plugin, run_id, query, items):
        return {"inserted": len(items), "updated": 0}

    def finish_source(self, *args, **kwargs):
        pass

    def finish_run(self, *args, **kwargs):
        pass


class CollectionContractTests(unittest.TestCase):
    def test_engine_passes_normalized_request(self):
        plugin = RecordingPlugin()
        store = MemoryStore()

        result = collect_query(
            "F-22", {plugin.name: plugin}, store, log=lambda _message: None,
            module_name="news", mode="search", options={"fresh": True},
        )

        self.assertEqual("completed", result["status"])
        self.assertEqual(("F-22", "news", "search", {"fresh": True}), store.created)
        self.assertIsInstance(plugin.request, CollectionRequest)
        self.assertEqual(7, plugin.request.limit)
        self.assertEqual({"x": 1}, plugin.request.config)

    def test_identity_is_independent_from_search_query(self):
        plugin = RecordingPlugin()
        item = SourceItem(title="Example", url="https://example.test/1")
        self.assertEqual("url:https://example.test/1", plugin.identity_value(item))

    def test_item_normalizes_author_list(self):
        item = SourceItem(
            title=" Paper ", url="https://example.test/paper", authors=["张三", " 李四 "],
        )
        self.assertEqual("Paper", item.title)
        self.assertEqual(["张三", "李四"], item.authors)
        self.assertEqual("张三, 李四", item.author)


if __name__ == "__main__":
    unittest.main()
