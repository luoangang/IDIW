import re
import unittest
from pathlib import Path

from collector.storage import SCHEMA_VERSION, _ACTIVE_SCHEMA_TABLES


class SchemaContractTests(unittest.TestCase):
    def test_compact_schema_has_exactly_nine_tables(self):
        self.assertEqual(4, SCHEMA_VERSION)
        self.assertEqual(
            {
                "schema_migrations",
                "sources",
                "monitors",
                "monitor_sources",
                "monitor_runs",
                "news_resources",
                "paper_resources",
                "patent_resources",
                "monitor_resource_matches",
            },
            _ACTIVE_SCHEMA_TABLES,
        )

    def test_init_sql_matches_active_schema(self):
        sql_path = Path(__file__).resolve().parents[1] / "sql" / "init.sql"
        sql = sql_path.read_text(encoding="utf-8")
        tables = set(
            re.findall(
                r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([a-zA-Z0-9_]+)`?",
                sql,
                re.IGNORECASE,
            )
        )
        self.assertEqual(_ACTIVE_SCHEMA_TABLES, tables)


if __name__ == "__main__":
    unittest.main()
