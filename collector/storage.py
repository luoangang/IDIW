"""MySQL persistence using one physical resource table per business module."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from collector.config import (
    MYSQL_CHARSET, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER,
)
from collector.modules.base import CollectorModule
from collector.sources.base import SourceItem, SourcePlugin


SCHEMA_VERSION = 4
_SAFE_DATABASE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MODULE_TABLES = {
    "news": "news_resources",
    "paper": "paper_resources",
    "patent": "patent_resources",
}
_LEGACY_NEWS_TABLES = {
    "baidu_baike": "baidu_baike_items",
    "wikipedia": "wikipedia_items",
    "google_news_rss": "google_news_items",
    "ddgs": "ddgs_items",
}
_ACTIVE_SCHEMA_TABLES = {
    "schema_migrations", "sources", "monitors", "monitor_sources",
    "monitor_runs", "news_resources", "paper_resources", "patent_resources",
    "monitor_resource_matches",
}
_OBSOLETE_SCHEMA_TABLES = (
    "run_resource_events", "run_source_results", "source_cursors", "paper_journals",
    "collection_job_sources", "collection_jobs", "collection_runs",
    "baidu_baike_items", "wikipedia_items", "google_news_items", "ddgs_items",
    "collector_item_template", "collector_modules", "collector_source_plugins",
    "collector_sources", "news_articles", "resource_queries", "resource_index",
    "schedule_tasks", "source_settings", "source_sync_state",
)


def _json_load(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class MySQLStore:
    def connect(self, with_database: bool = True):
        kwargs = dict(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset=MYSQL_CHARSET,
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=8,
        )
        if with_database:
            kwargs["database"] = MYSQL_DATABASE
        return pymysql.connect(**kwargs)

    def initialize(self) -> None:
        if not _SAFE_DATABASE.fullmatch(MYSQL_DATABASE):
            raise ValueError("unsafe database name")
        conn = self.connect(with_database=False)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                    f"CHARACTER SET {MYSQL_CHARSET} COLLATE utf8mb4_unicode_ci"
                )
            conn.commit()
        finally:
            conn.close()

        sql_path = Path(__file__).resolve().parent.parent / "sql" / "init.sql"
        statements = [
            part.strip() for part in sql_path.read_text(encoding="utf-8").split(";")
            if part.strip()
        ]
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                for statement in statements:
                    table_match = re.search(
                        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([a-zA-Z0-9_]+)`?",
                        statement, re.IGNORECASE,
                    )
                    if table_match and table_match.group(1) not in _ACTIVE_SCHEMA_TABLES:
                        continue
                    cursor.execute(statement)
                self._prepare_v4_schema(cursor)
                self._migrate_legacy_news(cursor)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _table_exists(cursor, table: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
            (MYSQL_DATABASE, table),
        )
        return cursor.fetchone() is not None

    @staticmethod
    def _column_exists(cursor, table: str, column: str) -> bool:
        cursor.execute(
            """SELECT 1 FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name=%s""",
            (MYSQL_DATABASE, table, column),
        )
        return cursor.fetchone() is not None

    def _prepare_v4_schema(self, cursor) -> None:
        additions = {
            "monitor_sources": (
                ("cursor_json", "JSON NULL AFTER config_json"),
                ("last_success_at", "DATETIME NULL AFTER cursor_json"),
                ("last_error", "TEXT NULL AFTER last_success_at"),
                (
                    "updated_at",
                    "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP "
                    "ON UPDATE CURRENT_TIMESTAMP AFTER last_error",
                ),
            ),
            "monitor_runs": (
                ("source_results_json", "JSON NULL AFTER options_json"),
            ),
        }
        for table, columns in additions.items():
            for column, definition in columns:
                if not self._column_exists(cursor, table, column):
                    cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")

        if self._column_exists(cursor, "paper_resources", "journal_id"):
            cursor.execute(
                """SELECT constraint_name FROM information_schema.key_column_usage
                WHERE table_schema=%s AND table_name='paper_resources'
                  AND column_name='journal_id' AND referenced_table_name IS NOT NULL""",
                (MYSQL_DATABASE,),
            )
            for row in cursor.fetchall():
                cursor.execute(
                    f"ALTER TABLE paper_resources DROP FOREIGN KEY `{row['constraint_name']}`"
                )
            cursor.execute("ALTER TABLE paper_resources DROP COLUMN journal_id")

    def _migrate_legacy_news(self, cursor) -> None:
        """Copy legacy source tables into the v3 news table without deleting them."""
        for source_key, table in _LEGACY_NEWS_TABLES.items():
            if not self._table_exists(cursor, table):
                continue
            cursor.execute(
                f"""INSERT IGNORE INTO news_resources
                (resource_uid, source_key, resource_type, external_id, title, url,
                 summary, content, author_display, publisher, published_at, language,
                 identity_hash, canonical_hash, content_hash, metadata_json,
                 matched_queries_json, first_run_id, last_run_id, first_seen_at, last_seen_at)
                SELECT UUID(), %s, COALESCE(NULLIF(resource_type, ''), 'document'),
                       NULLIF(source_item_id, ''), title, url, summary, content, author,
                       publisher, published_at, language,
                       SHA2(CONCAT(%s, '\n',
                         IF(NULLIF(TRIM(source_item_id), '') IS NOT NULL,
                            CONCAT('external:', TRIM(source_item_id)),
                            CONCAT('url:', TRIM(url)))), 256),
                       SHA2(LOWER(TRIM(url)), 256), content_hash,
                       IF(JSON_VALID(extra_json), extra_json, JSON_OBJECT()),
                       JSON_ARRAY(query_text), first_run_id, last_run_id,
                       first_seen_at, last_seen_at
                FROM `{table}`
                ON DUPLICATE KEY UPDATE
                  last_run_id=GREATEST(news_resources.last_run_id, VALUES(last_run_id)),
                  last_seen_at=GREATEST(news_resources.last_seen_at, VALUES(last_seen_at))""",
                (source_key, source_key),
            )

    def _migrate_legacy_runs(self, cursor) -> None:
        if not self._table_exists(cursor, "collection_jobs"):
            return
        cursor.execute(
            """INSERT IGNORE INTO monitor_runs
            (id, monitor_id, module_name, query_text, mode, trigger_type, options_json,
             source_results_json,
             status, total_fetched, total_inserted, total_updated, error_message,
             started_at, finished_at)
            SELECT id, NULL, module_name, query_text, COALESCE(NULLIF(mode, ''), 'search'),
                   'manual', IF(JSON_VALID(options_json), options_json, JSON_OBJECT()), NULL,
                   status, total_fetched, total_inserted, 0, error_message,
                   started_at, finished_at
            FROM collection_jobs"""
        )
        if not self._table_exists(cursor, "collection_job_sources"):
            return
        cursor.execute("SELECT * FROM collection_job_sources ORDER BY run_id, id")
        self._merge_source_results(cursor, cursor.fetchall())

    @staticmethod
    def _merge_source_results(cursor, rows: list[dict[str, Any]]) -> None:
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            run_id = int(row["run_id"])
            source_key = row.get("source_key") or row.get("source_name")
            if not source_key:
                continue
            grouped.setdefault(run_id, {})[source_key] = {
                "status": row.get("status", "completed"),
                "fetched": int(row.get("fetched_count") or 0),
                "inserted": int(row.get("inserted_count") or 0),
                "updated": int(row.get("updated_count") or 0),
                "error": row.get("error_message") or "",
                "started_at": str(row.get("started_at") or ""),
                "finished_at": str(row.get("finished_at") or ""),
            }
        for run_id, results in grouped.items():
            cursor.execute(
                "UPDATE monitor_runs SET source_results_json=%s WHERE id=%s",
                (json.dumps(results, ensure_ascii=False), run_id),
            )

    def _migrate_v3_tables(self, cursor) -> None:
        if self._table_exists(cursor, "run_source_results"):
            cursor.execute("SELECT * FROM run_source_results ORDER BY run_id, id")
            self._merge_source_results(cursor, cursor.fetchall())

        if self._table_exists(cursor, "source_cursors"):
            cursor.execute(
                """SELECT source_key, scope_key, cursor_json, last_success_at
                FROM source_cursors WHERE scope_type='monitor'"""
            )
            for row in cursor.fetchall():
                try:
                    monitor_id = int(row["scope_key"])
                except (TypeError, ValueError):
                    continue
                cursor.execute(
                    """UPDATE monitor_sources SET cursor_json=%s, last_success_at=%s
                    WHERE monitor_id=%s AND source_key=%s""",
                    (
                        row["cursor_json"], row["last_success_at"],
                        monitor_id, row["source_key"],
                    ),
                )

    def _drop_obsolete_tables(self, cursor) -> None:
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        try:
            for table in _OBSOLETE_SCHEMA_TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")

    def sync_catalog(self, modules: dict[str, CollectorModule],
                     plugins: dict[str, SourcePlugin]) -> None:
        del modules  # Module definitions live in code; only source settings are persisted.
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                has_legacy_settings = self._table_exists(cursor, "source_settings")
                for plugin in plugins.values():
                    legacy = {}
                    if has_legacy_settings:
                        cursor.execute(
                            """SELECT enabled, item_limit, config_json FROM source_settings
                               WHERE source_name=%s""",
                            (plugin.name,),
                        )
                        legacy = cursor.fetchone() or {}
                    defaults = {
                        key: spec.get("default") for key, spec in plugin.configurable.items()
                    }
                    enabled = int(legacy.get("enabled", 1))
                    item_limit = int(legacy.get("item_limit", plugin.default_limit))
                    config = _json_load(legacy.get("config_json"), defaults)
                    cursor.execute(
                        """INSERT INTO sources
                        (source_key, module_name, label, adapter_name, resource_type,
                         supported_modes_json, enabled, item_limit, config_json)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE module_name=VALUES(module_name),
                        label=VALUES(label), adapter_name=VALUES(adapter_name),
                        resource_type=VALUES(resource_type),
                        supported_modes_json=VALUES(supported_modes_json), status='active'""",
                        (
                            plugin.name, plugin.module, plugin.label,
                            f"{plugin.__class__.__module__}.{plugin.__class__.__name__}",
                            plugin.resource_type, json.dumps(plugin.supported_modes),
                            enabled, item_limit, json.dumps(config, ensure_ascii=False),
                        ),
                    )
                self._migrate_legacy_runs(cursor)
                self._migrate_v3_tables(cursor)
                self._drop_obsolete_tables(cursor)
                cursor.execute(
                    "INSERT IGNORE INTO schema_migrations (version, name) VALUES (%s, %s)",
                    (SCHEMA_VERSION, "compact monitoring schema"),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_modules(self) -> list[dict]:
        """Kept for API compatibility; module metadata is now code-owned."""
        return []

    def list_settings(self) -> dict[str, dict[str, Any]]:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT source_key, module_name, enabled, item_limit, config_json FROM sources"
                )
                rows = cursor.fetchall()
            return {
                row["source_key"]: {
                    "module": row["module_name"],
                    "enabled": bool(row["enabled"]),
                    "item_limit": int(row["item_limit"]),
                    "config": _json_load(row["config_json"], {}),
                }
                for row in rows
            }
        finally:
            conn.close()

    def update_setting(self, source_name: str, enabled: bool, item_limit: int,
                       config: dict) -> None:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE sources SET enabled=%s, item_limit=%s, config_json=%s
                       WHERE source_key=%s""",
                    (
                        int(enabled), max(1, min(int(item_limit), 500)),
                        json.dumps(config, ensure_ascii=False), source_name,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def create_run(self, query: str, module_name: str = "news", mode: str = "search",
                   options: dict[str, Any] | None = None, monitor_id: int | None = None,
                   trigger_type: str = "manual") -> int:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO monitor_runs
                    (monitor_id, module_name, query_text, mode, trigger_type, options_json)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (
                        monitor_id, module_name, query, mode, trigger_type,
                        json.dumps(options or {}, ensure_ascii=False),
                    ),
                )
                run_id = cursor.lastrowid
            conn.commit()
            return run_id
        finally:
            conn.close()

    def start_source(self, run_id: int, source_name: str,
                     module_name: str = "news", scope_key: str = "") -> None:
        del module_name, scope_key
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                self._update_run_source_result(
                    cursor, run_id, source_name,
                    {"status": "running", "started_at": self._database_now(cursor)},
                )
            conn.commit()
        finally:
            conn.close()

    def finish_source(self, run_id: int, source_name: str, status: str,
                      fetched: int = 0, inserted: int = 0, updated: int = 0,
                      error: str = "", scope_key: str = "") -> None:
        del scope_key
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                self._update_run_source_result(
                    cursor, run_id, source_name,
                    {
                        "status": status,
                        "fetched": fetched,
                        "inserted": inserted,
                        "updated": updated,
                        "error": error,
                        "finished_at": self._database_now(cursor),
                    },
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _database_now(cursor) -> str:
        del cursor
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _update_run_source_result(cursor, run_id: int, source_name: str,
                                  values: dict[str, Any]) -> None:
        cursor.execute(
            "SELECT source_results_json FROM monitor_runs WHERE id=%s FOR UPDATE",
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"run does not exist: {run_id}")
        results = _json_load(row["source_results_json"], {})
        if not isinstance(results, dict):
            results = {}
        current = results.get(source_name, {})
        if not isinstance(current, dict):
            current = {}
        current.update(values)
        results[source_name] = current
        cursor.execute(
            "UPDATE monitor_runs SET source_results_json=%s WHERE id=%s",
            (json.dumps(results, ensure_ascii=False), run_id),
        )

    @staticmethod
    def _hash_json(value: dict[str, Any]) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_query(raw: Any, query: str) -> list[str]:
        values = _json_load(raw, [])
        if not isinstance(values, list):
            values = []
        if query and query not in values:
            values.append(query)
        return values

    def write_items(self, plugin: SourcePlugin, run_id: int, query: str,
                    items: list[SourceItem]) -> dict[str, int]:
        table = _MODULE_TABLES.get(plugin.module)
        if not table:
            raise ValueError(f"unsupported module table: {plugin.module}")
        stats = {"inserted": 0, "updated": 0}
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT monitor_id FROM monitor_runs WHERE id=%s", (run_id,))
                run = cursor.fetchone()
                if not run:
                    raise ValueError(f"run does not exist: {run_id}")
                monitor_id = run["monitor_id"]
                for item in items:
                    identity_value = f"{plugin.name}\n{plugin.identity_value(item)}"
                    identity_hash = hashlib.sha256(identity_value.encode("utf-8")).hexdigest()
                    canonical_hash = hashlib.sha256(item.url.strip().lower().encode("utf-8")).hexdigest()
                    metadata = {
                        "authors": item.authors,
                        "identifiers": item.identifiers,
                        "extra": item.extra,
                    }
                    content_hash = self._hash_json({
                        "title": item.title,
                        "summary": item.summary,
                        "content": item.content,
                        "published_at": item.published_at.isoformat() if item.published_at else "",
                        "metadata": metadata,
                    })
                    cursor.execute(
                        f"""SELECT id, resource_uid, content_hash, matched_queries_json
                            FROM `{table}` WHERE source_key=%s AND identity_hash=%s""",
                        (plugin.name, identity_hash),
                    )
                    existing = cursor.fetchone()
                    queries = self._merge_query(
                        existing.get("matched_queries_json") if existing else None, query,
                    )
                    resource_uid = existing["resource_uid"] if existing else str(uuid.uuid4())
                    common = {
                        "resource_uid": resource_uid,
                        "source_key": plugin.name,
                        "resource_type": item.resource_type or plugin.resource_type,
                        "external_id": item.source_item_id[:512] or None,
                        "title": item.title[:1000],
                        "url": item.url,
                        "summary": item.summary,
                        "content": item.content,
                        "publisher": item.publisher[:255],
                        "published_at": item.published_at,
                        "language": item.language[:32],
                        "identity_hash": identity_hash,
                        "canonical_hash": canonical_hash,
                        "content_hash": content_hash,
                        "metadata_json": json.dumps(metadata, ensure_ascii=False),
                        "matched_queries_json": json.dumps(queries, ensure_ascii=False),
                    }
                    if plugin.module == "news":
                        self._write_news(cursor, common, item, run_id, existing)
                    elif plugin.module == "paper":
                        self._write_paper(cursor, common, item, run_id, existing)
                    else:
                        self._write_patent(cursor, common, item, run_id, existing)
                    if monitor_id is not None:
                        cursor.execute(
                            """INSERT INTO monitor_resource_matches
                            (monitor_id, module_name, resource_uid, first_run_id, last_run_id,
                             match_reason_json)
                            VALUES (%s,%s,%s,%s,%s,%s)
                            ON DUPLICATE KEY UPDATE last_run_id=VALUES(last_run_id),
                            last_matched_at=NOW(), match_count=match_count+1,
                            match_reason_json=VALUES(match_reason_json)""",
                            (
                                monitor_id, plugin.module, resource_uid, run_id, run_id,
                                json.dumps({"query": query}, ensure_ascii=False),
                            ),
                        )
                    stats["updated" if existing else "inserted"] += 1
            conn.commit()
            return stats
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _write_news(cursor, common: dict[str, Any], item: SourceItem,
                    run_id: int, existing: dict | None) -> None:
        values = (
            common["resource_type"], common["external_id"], common["title"], common["url"],
            common["summary"], common["content"], item.author[:500], common["publisher"],
            common["published_at"], common["language"], common["canonical_hash"],
            common["content_hash"], common["metadata_json"], common["matched_queries_json"], run_id,
        )
        if existing:
            cursor.execute(
                """UPDATE news_resources SET resource_type=%s, external_id=%s, title=%s,
                url=%s, summary=%s, content=%s, author_display=%s, publisher=%s,
                published_at=%s, language=%s, canonical_hash=%s, content_hash=%s,
                metadata_json=%s, matched_queries_json=%s, last_run_id=%s, last_seen_at=NOW()
                WHERE id=%s""",
                (*values, existing["id"]),
            )
        else:
            cursor.execute(
                """INSERT INTO news_resources
                (resource_uid, source_key, resource_type, external_id, title, url, summary,
                 content, author_display, publisher, published_at, language, identity_hash,
                 canonical_hash, content_hash, metadata_json, matched_queries_json,
                 first_run_id, last_run_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    common["resource_uid"], common["source_key"], common["resource_type"],
                    common["external_id"], common["title"], common["url"], common["summary"],
                    common["content"], item.author[:500], common["publisher"],
                    common["published_at"], common["language"], common["identity_hash"],
                    common["canonical_hash"], common["content_hash"], common["metadata_json"],
                    common["matched_queries_json"], run_id, run_id,
                ),
            )

    @staticmethod
    def _write_paper(cursor, common: dict[str, Any], item: SourceItem,
                     run_id: int, existing: dict | None) -> None:
        extra, identifiers = item.extra, item.identifiers
        fields = (
            common["resource_type"], common["external_id"], extra.get("journal_key"),
            common["title"], common["url"], common["summary"], common["content"],
            item.author[:500], json.dumps(item.authors, ensure_ascii=False),
            json.dumps(extra.get("affiliations", []), ensure_ascii=False),
            json.dumps(extra.get("keywords", []), ensure_ascii=False), common["publisher"],
            common["published_at"], extra.get("publication_date"), common["language"],
            identifiers.get("doi") or extra.get("doi"), extra.get("year"),
            extra.get("volume"), extra.get("issue"), extra.get("pages"),
            json.dumps(extra.get("funding", []), ensure_ascii=False), extra.get("citation_text"),
            common["canonical_hash"], common["content_hash"], common["metadata_json"],
            common["matched_queries_json"], run_id,
        )
        if existing:
            cursor.execute(
                """UPDATE paper_resources SET resource_type=%s, external_id=%s,
                journal_key=%s, title=%s, url=%s, summary=%s, content=%s,
                author_display=%s, authors_json=%s, affiliations_json=%s, keywords_json=%s,
                publisher=%s, published_at=%s, publication_date=%s, language=%s, doi=%s,
                publication_year=%s, volume=%s, issue=%s, pages=%s, funding_json=%s,
                citation_text=%s, canonical_hash=%s, content_hash=%s, metadata_json=%s,
                matched_queries_json=%s, last_run_id=%s, last_seen_at=NOW() WHERE id=%s""",
                (*fields, existing["id"]),
            )
        else:
            cursor.execute(
                """INSERT INTO paper_resources
                (resource_uid, source_key, resource_type, external_id, journal_key, title, url,
                 summary, content, author_display, authors_json, affiliations_json, keywords_json,
                 publisher, published_at, publication_date, language, doi, publication_year,
                 volume, issue, pages, funding_json, citation_text, identity_hash, canonical_hash,
                 content_hash, metadata_json, matched_queries_json, first_run_id, last_run_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    common["resource_uid"], common["source_key"], common["resource_type"],
                    common["external_id"], extra.get("journal_key"), common["title"], common["url"],
                    common["summary"], common["content"], item.author[:500],
                    json.dumps(item.authors, ensure_ascii=False),
                    json.dumps(extra.get("affiliations", []), ensure_ascii=False),
                    json.dumps(extra.get("keywords", []), ensure_ascii=False), common["publisher"],
                    common["published_at"], extra.get("publication_date"), common["language"],
                    identifiers.get("doi") or extra.get("doi"), extra.get("year"),
                    extra.get("volume"), extra.get("issue"), extra.get("pages"),
                    json.dumps(extra.get("funding", []), ensure_ascii=False), extra.get("citation_text"),
                    common["identity_hash"], common["canonical_hash"], common["content_hash"],
                    common["metadata_json"], common["matched_queries_json"], run_id, run_id,
                ),
            )

    @staticmethod
    def _write_patent(cursor, common: dict[str, Any], item: SourceItem,
                      run_id: int, existing: dict | None) -> None:
        extra, identifiers = item.extra, item.identifiers
        fields = (
            common["resource_type"], common["external_id"],
            identifiers.get("patent_number") or extra.get("patent_number"),
            extra.get("application_number"), extra.get("publication_number"),
            common["title"], common["url"], common["summary"], common["content"],
            json.dumps(extra.get("applicants", []), ensure_ascii=False),
            json.dumps(extra.get("inventors", []), ensure_ascii=False),
            json.dumps(extra.get("classifications", []), ensure_ascii=False),
            extra.get("priority_date"), extra.get("application_date"), extra.get("publication_date"),
            extra.get("legal_status"), extra.get("country_code"), common["publisher"],
            common["published_at"], common["language"], common["canonical_hash"],
            common["content_hash"], common["metadata_json"], common["matched_queries_json"], run_id,
        )
        if existing:
            cursor.execute(
                """UPDATE patent_resources SET resource_type=%s, external_id=%s,
                patent_number=%s, application_number=%s, publication_number=%s, title=%s,
                url=%s, summary=%s, content=%s, applicants_json=%s, inventors_json=%s,
                classification_json=%s, priority_date=%s, application_date=%s,
                publication_date=%s, legal_status=%s, country_code=%s, publisher=%s,
                published_at=%s, language=%s, canonical_hash=%s, content_hash=%s,
                metadata_json=%s, matched_queries_json=%s, last_run_id=%s,
                last_seen_at=NOW() WHERE id=%s""",
                (*fields, existing["id"]),
            )
        else:
            cursor.execute(
                """INSERT INTO patent_resources
                (resource_uid, source_key, resource_type, external_id, patent_number,
                 application_number, publication_number, title, url, summary, content,
                 applicants_json, inventors_json, classification_json, priority_date,
                 application_date, publication_date, legal_status, country_code, publisher,
                 published_at, language, identity_hash, canonical_hash, content_hash,
                 metadata_json, matched_queries_json, first_run_id, last_run_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    common["resource_uid"], common["source_key"], common["resource_type"],
                    common["external_id"], identifiers.get("patent_number") or extra.get("patent_number"),
                    extra.get("application_number"), extra.get("publication_number"), common["title"],
                    common["url"], common["summary"], common["content"],
                    json.dumps(extra.get("applicants", []), ensure_ascii=False),
                    json.dumps(extra.get("inventors", []), ensure_ascii=False),
                    json.dumps(extra.get("classifications", []), ensure_ascii=False),
                    extra.get("priority_date"), extra.get("application_date"), extra.get("publication_date"),
                    extra.get("legal_status"), extra.get("country_code"), common["publisher"],
                    common["published_at"], common["language"], common["identity_hash"],
                    common["canonical_hash"], common["content_hash"], common["metadata_json"],
                    common["matched_queries_json"], run_id, run_id,
                ),
            )

    def finish_run(self, run_id: int, status: str, fetched: int, inserted: int,
                   error: str = "", updated: int = 0) -> None:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE monitor_runs SET status=%s, total_fetched=%s,
                    total_inserted=%s, total_updated=%s, error_message=%s,
                    finished_at=NOW() WHERE id=%s""",
                    (status, fetched, inserted, updated, error or None, run_id),
                )
            conn.commit()
        finally:
            conn.close()

    def recent_runs(self, limit: int = 30, module_name: str = "") -> list[dict]:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                if module_name:
                    cursor.execute(
                        "SELECT * FROM monitor_runs WHERE module_name=%s ORDER BY id DESC LIMIT %s",
                        (module_name, limit),
                    )
                else:
                    cursor.execute("SELECT * FROM monitor_runs ORDER BY id DESC LIMIT %s", (limit,))
                rows = list(cursor.fetchall())
            for row in rows:
                row["options"] = _json_load(row.pop("options_json", None), {})
                row["source_results"] = _json_load(row.pop("source_results_json", None), {})
            return rows
        finally:
            conn.close()

    @staticmethod
    def _resource_filters(source_name: str, query: str) -> tuple[str, list[Any]]:
        where, params = [], []
        if source_name:
            where.append("source_key=%s")
            params.append(source_name)
        if query:
            where.append("JSON_CONTAINS(matched_queries_json, JSON_QUOTE(%s))")
            params.append(query)
        return (" WHERE " + " AND ".join(where) if where else ""), params

    def recent_resources(self, module_name: str = "", source_name: str = "",
                         query: str = "", limit: int = 50) -> list[dict]:
        modules = [module_name] if module_name else list(_MODULE_TABLES)
        rows: list[dict] = []
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                for module in modules:
                    table = _MODULE_TABLES.get(module)
                    if not table:
                        continue
                    clause, params = self._resource_filters(source_name, query)
                    cursor.execute(
                        f"""SELECT id, resource_uid, source_key AS source_name,
                        %s AS module_name, resource_type, title, url, summary,
                        publisher, published_at, language, first_seen_at, last_seen_at
                        FROM `{table}`{clause} ORDER BY last_seen_at DESC, id DESC LIMIT %s""",
                        (module, *params, limit),
                    )
                    rows.extend(cursor.fetchall())
            rows.sort(key=lambda row: (row["last_seen_at"], row["id"]), reverse=True)
            return rows[:limit]
        finally:
            conn.close()

    def recent_items(self, plugin: SourcePlugin, limit: int = 50,
                     query: str = "") -> list[dict]:
        table = _MODULE_TABLES[plugin.module]
        clause, params = self._resource_filters(plugin.name, query)
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM `{table}`{clause} ORDER BY last_seen_at DESC, id DESC LIMIT %s",
                    (*params, limit),
                )
                rows = list(cursor.fetchall())
            for row in rows:
                row["metadata"] = _json_load(row.pop("metadata_json", None), {})
                row["matched_queries"] = _json_load(row.pop("matched_queries_json", None), [])
                if "authors_json" in row:
                    row["authors"] = _json_load(row.pop("authors_json"), [])
            return rows
        finally:
            conn.close()

    def schema_version(self) -> int:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
                return int(cursor.fetchone()["version"])
        finally:
            conn.close()

    def get_sync_state(self, source_name: str, monitor_id: int) -> dict[str, Any]:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT cursor_json FROM monitor_sources
                    WHERE source_key=%s AND monitor_id=%s""",
                    (source_name, monitor_id),
                )
                row = cursor.fetchone()
                return _json_load(row["cursor_json"], {}) if row else {}
        finally:
            conn.close()

    def save_sync_state(self, source_name: str, state: dict[str, Any],
                        monitor_id: int, error: str = "") -> None:
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE monitor_sources SET cursor_json=%s, last_success_at=NOW(),
                    last_error=%s WHERE source_key=%s AND monitor_id=%s""",
                    (
                        json.dumps(state, ensure_ascii=False),
                        error or None, source_name, monitor_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(
                        f"monitor source does not exist: {monitor_id}/{source_name}"
                    )
            conn.commit()
        finally:
            conn.close()
