from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from crawler_platform.config import Settings
from crawler_platform.categories import CATEGORIES, normalize_category
from crawler_platform.protocol import (
    FieldSpec, PackageManifest, ProtocolError, content_digest, identity_digest,
    load_manifest, validate_item, validate_parameters,
)
from crawler_platform.proxy_pool import check_proxy_connection, validate_proxy_url
from crawler_platform.weekly_report import BEIJING, MAX_EVIDENCE, previous_week, week_bounds


SAFE_DATABASE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SAFE_TABLE = re.compile(r"^pkg_data_\d{6,20}$")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def json_load(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def cursor_is_stalled(previous_cursor: Any, result: dict[str, Any]) -> bool:
    return bool(result.get("has_more") and result.get("next_cursor") == previous_cursor)


class MonitorNameConflict(ValueError):
    pass


def monitor_name_key(name: str) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 255:
        raise ValueError("monitor name must be 1-255 characters")
    normalized = unicodedata.normalize("NFKC", " ".join(name.split())).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class PlatformStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self, with_database: bool = True):
        kwargs = dict(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=8,
            init_command="SET time_zone = '+00:00'",
        )
        if with_database:
            kwargs["database"] = self.settings.mysql_database
        return pymysql.connect(**kwargs)

    def initialize(self) -> None:
        if not SAFE_DATABASE.fullmatch(self.settings.mysql_database):
            raise ValueError("unsafe platform database name")
        connection = self.connect(False)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.settings.mysql_database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            connection.commit()
        finally:
            connection.close()
        sql_path = Path(__file__).with_name("schema.sql")
        statements = [part.strip() for part in sql_path.read_text(encoding="utf-8").split(";") if part.strip()]
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
                checksum = hashlib.sha256(sql_path.read_bytes()).hexdigest()
                cursor.execute(
                    """INSERT INTO schema_migrations(version,name,checksum)
                    VALUES('1','initial package platform',%s)
                    ON DUPLICATE KEY UPDATE checksum=VALUES(checksum)""",
                    (checksum,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        migration_path = Path(__file__).with_name("migrations") / "002_proxy_pool.sql"
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                for statement in migration_path.read_text(encoding="utf-8").split(";"):
                    if statement.strip():
                        cursor.execute(statement.strip())
                cursor.execute(
                    """INSERT INTO schema_migrations(version,name,checksum)
                    VALUES('2','platform proxy pool',%s)
                    ON DUPLICATE KEY UPDATE checksum=VALUES(checksum)""",
                    (hashlib.sha256(migration_path.read_bytes()).hexdigest(),),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        report_migration = Path(__file__).with_name("migrations") / "003_weekly_reports.sql"
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s "
                    "AND TABLE_NAME='monitors' AND COLUMN_NAME='weekly_report_enabled'",
                    (self.settings.mysql_database,),
                )
                statements = [part.strip() for part in report_migration.read_text(encoding="utf-8").split(";") if part.strip()]
                if not cursor.fetchone():
                    cursor.execute(statements[0])
                cursor.execute(statements[1])
                cursor.execute(
                    """INSERT INTO schema_migrations(version,name,checksum)
                    VALUES('3','weekly intelligence reports',%s)
                    ON DUPLICATE KEY UPDATE checksum=VALUES(checksum)""",
                    (hashlib.sha256(report_migration.read_bytes()).hexdigest(),),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        self._migrate_monitor_archive()
        for directory in (
            self.settings.runtime_dir, self.settings.packages_dir,
            self.settings.environments_dir, self.settings.runs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        for category in CATEGORIES:
            (self.settings.packages_dir / category).mkdir(parents=True, exist_ok=True)

    def _migrate_monitor_archive(self) -> None:
        migration_path = Path(__file__).with_name("migrations") / "004_monitor_archive.sql"
        statements = [part.strip() for part in migration_path.read_text(encoding="utf-8").split(";") if part.strip()]
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s "
                    "AND TABLE_NAME='monitors' AND COLUMN_NAME IN ('archived_at','active_name_key')",
                    (self.settings.mysql_database,),
                )
                columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
                if not columns:
                    cursor.execute(statements[0])
                elif columns != {"archived_at", "active_name_key"}:
                    raise ValueError("incomplete monitor archive migration")
                cursor.execute("SELECT id,name,archived_at,active_name_key FROM monitors ORDER BY id")
                monitors = cursor.fetchall()
                keys: dict[str, int] = {}
                updates = []
                for monitor in monitors:
                    key = None if monitor["archived_at"] is not None else monitor_name_key(monitor["name"])
                    if key is not None and key in keys:
                        raise ValueError(
                            f"duplicate active monitor names: #{keys[key]} and #{monitor['id']}; "
                            "archive or rename one before migration"
                        )
                    if key is not None:
                        keys[key] = monitor["id"]
                    if key != monitor["active_name_key"]:
                        updates.append((key, monitor["id"]))
                for key, monitor_id in updates:
                    cursor.execute("UPDATE monitors SET active_name_key=%s WHERE id=%s", (key, monitor_id))
                cursor.execute(
                    "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s "
                    "AND TABLE_NAME='monitors' AND INDEX_NAME='uk_monitors_active_name' LIMIT 1",
                    (self.settings.mysql_database,),
                )
                if not cursor.fetchone():
                    cursor.execute(statements[1])
                cursor.execute(
                    """INSERT INTO schema_migrations(version,name,checksum)
                    VALUES('4','monitor archive and active names',%s)
                    ON DUPLICATE KEY UPDATE checksum=VALUES(checksum)""",
                    (hashlib.sha256(migration_path.read_bytes()).hexdigest(),),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_proxies(self) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,name,proxy_url,enabled,last_selected_at,selected_count,created_at "
                               "FROM proxy_endpoints ORDER BY id")
                return list(cursor.fetchall())
        finally:
            connection.close()

    def create_proxy(self, name: str, proxy_url: str, enabled: bool = True) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
            raise ValueError("proxy name must be 1-128 characters")
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        proxy_url = validate_proxy_url(proxy_url)
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO proxy_endpoints(name,proxy_url,enabled) VALUES(%s,%s,%s)",
                               (name.strip(), proxy_url, enabled))
                proxy_id = cursor.lastrowid
            connection.commit()
            return {"id": proxy_id, "name": name.strip(), "proxy_url": proxy_url, "enabled": enabled}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def check_proxy(self, proxy_id: int) -> dict[str, Any]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT proxy_url FROM proxy_endpoints WHERE id=%s", (proxy_id,))
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(f"proxy not found: {proxy_id}")
        finally:
            connection.close()
        return {"id": proxy_id, "tcp_reachable": check_proxy_connection(row["proxy_url"])}

    def update_proxy(self, proxy_id: int, name: str, proxy_url: str, enabled: bool) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
            raise ValueError("proxy name must be 1-128 characters")
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        proxy_url = validate_proxy_url(proxy_url)
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT proxy_url,selected_count FROM proxy_endpoints WHERE id=%s FOR UPDATE",
                               (proxy_id,))
                existing = cursor.fetchone()
                if existing is None:
                    raise KeyError(f"proxy not found: {proxy_id}")
                if existing["selected_count"] and existing["proxy_url"] != proxy_url:
                    raise ValueError("used proxy address cannot change; disable this node and add a new one")
                cursor.execute("UPDATE proxy_endpoints SET name=%s,proxy_url=%s,enabled=%s WHERE id=%s",
                               (name.strip(), proxy_url, enabled, proxy_id))
            connection.commit()
            return {"id": proxy_id, "name": name.strip(), "proxy_url": proxy_url, "enabled": enabled}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def assign_proxy(self, package_run_id: int) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT p.id,p.name,p.proxy_url FROM proxy_run_assignments a "
                    "JOIN proxy_endpoints p ON p.id=a.proxy_endpoint_id "
                    "WHERE a.package_run_id=%s", (package_run_id,),
                )
                assigned = cursor.fetchone()
                if assigned:
                    return assigned
                cursor.execute(
                    "SELECT id,name,proxy_url FROM proxy_endpoints WHERE enabled=1 "
                    "ORDER BY last_selected_at IS NOT NULL,last_selected_at,id LIMIT 1 FOR UPDATE"
                )
                selected = cursor.fetchone()
                if selected:
                    cursor.execute("UPDATE proxy_endpoints SET last_selected_at=NOW(6),"
                                   "selected_count=selected_count+1 WHERE id=%s", (selected["id"],))
                    cursor.execute("INSERT INTO proxy_run_assignments(package_run_id,proxy_endpoint_id) "
                                   "VALUES(%s,%s)", (package_run_id, selected["id"]))
            connection.commit()
            return selected
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def register_installing(self, manifest: PackageManifest, artifact_digest: str, schema_hash: str,
                            artifact_path: Path) -> dict[str, Any]:
        defaults = validate_parameters(manifest.parameters_schema, {})
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM crawler_packages WHERE package_key=%s FOR UPDATE",
                    (manifest.package_key,),
                )
                existing = cursor.fetchone()
                if existing and existing["active_version"] == manifest.package_version:
                    if existing["artifact_digest"] == artifact_digest and existing["status"] == "ready":
                        connection.rollback()
                        return {**existing, "idempotent": True}
                    if existing["artifact_digest"] != artifact_digest:
                        raise ProtocolError("same package version has a different artifact digest")
                state = {"stage": "registered", "candidate_version": manifest.package_version}
                if existing:
                    cursor.execute(
                        """UPDATE crawler_packages SET name=%s,description=%s,category=%s,
                        protocol_version=%s,manifest_json=%s,default_config_json=%s,
                        status='installing',install_state_json=%s,updated_at=NOW(6)
                        WHERE id=%s""",
                        (
                            manifest.name, manifest.description, manifest.category,
                            manifest.protocol_version, json_dump(manifest.raw), json_dump(defaults),
                            json_dump(state), existing["id"],
                        ),
                    )
                    package_id = existing["id"]
                else:
                    cursor.execute(
                        """INSERT INTO crawler_packages
                        (package_key,name,description,category,protocol_version,manifest_json,
                         default_config_json,secret_refs_json,status,install_state_json)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,'{}','installing',%s)""",
                        (
                            manifest.package_key, manifest.name, manifest.description,
                            manifest.category, manifest.protocol_version, json_dump(manifest.raw),
                            json_dump(defaults), json_dump(state),
                        ),
                    )
                    package_id = cursor.lastrowid
                table_name = existing.get("table_name") if existing else None
                if not table_name:
                    table_name = f"pkg_data_{package_id:06d}"
                    cursor.execute(
                        "UPDATE crawler_packages SET table_name=%s WHERE id=%s",
                        (table_name, package_id),
                    )
            connection.commit()
            return {
                "id": package_id, "table_name": table_name,
                "artifact_path": str(artifact_path), "schema_hash": schema_hash,
                "artifact_digest": artifact_digest, "idempotent": False,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_or_upgrade_package_table(self, table_name: str, manifest: PackageManifest) -> None:
        self._assert_table(table_name)
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                    (self.settings.mysql_database, table_name),
                )
                exists = bool(cursor.fetchone()["n"])
                if not exists:
                    cursor.execute(self._create_table_sql(table_name, manifest))
                else:
                    cursor.execute(
                        """SELECT column_name FROM information_schema.columns
                        WHERE table_schema=%s AND table_name=%s""",
                        (self.settings.mysql_database, table_name),
                    )
                    current = {row["column_name"] for row in cursor.fetchall()}
                    declared = {field.name for field in manifest.fields}
                    missing = declared - current
                    removed = {
                        name for name in current
                        if not name.startswith("sys_") and name not in declared
                    }
                    if removed:
                        raise ProtocolError(f"automatic upgrade may not remove fields: {sorted(removed)}")
                    for field in manifest.fields:
                        if field.name in missing:
                            if not field.nullable:
                                raise ProtocolError(f"new fields must be nullable: {field.name}")
                            cursor.execute(
                                f"ALTER TABLE `{table_name}` ADD COLUMN `{field.name}` {self._field_sql(field)} NULL"
                            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def activate_package(self, package_id: int, manifest: PackageManifest, artifact_digest: str,
                         schema_hash: str, artifact_path: Path) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE crawler_packages SET active_version=%s,output_schema_version=%s,
                    manifest_json=%s,schema_hash=%s,artifact_digest=%s,active_artifact_path=%s,
                    status='ready',install_state_json=%s,updated_at=NOW(6) WHERE id=%s""",
                    (
                        manifest.package_version, manifest.output_schema_version,
                        json_dump(manifest.raw), schema_hash, artifact_digest, str(artifact_path),
                        json_dump({"stage": "ready", "version": manifest.package_version}), package_id,
                    ),
                )
                cursor.execute(
                    """INSERT INTO monitor_packages
                    (monitor_id,package_id,enabled,item_limit,config_json)
                    SELECT id,%s,1,100,'{}' FROM monitors
                    WHERE auto_include_new_packages=1
                      AND JSON_CONTAINS(selected_categories_json,JSON_QUOTE(%s))
                    ON DUPLICATE KEY UPDATE monitor_id=monitor_id""",
                    (package_id, manifest.category),
                )
            connection.commit()
        finally:
            connection.close()

    def fail_install(self, package_key: str, message: str) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE crawler_packages SET status='install_failed',install_state_json=%s
                    WHERE package_key=%s""",
                    (json_dump({"stage": "failed", "error": message[:2000]}), package_key),
                )
            connection.commit()
        finally:
            connection.close()

    def assert_package_idle(self, package_key: str) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT pr.id FROM package_runs pr JOIN crawler_packages p ON p.id=pr.package_id
                    WHERE p.package_key=%s AND pr.status IN ('queued','running') LIMIT 1""",
                    (package_key,),
                )
                if cursor.fetchone():
                    raise ValueError("package has queued or running tasks; retry after completion")
        finally:
            connection.close()

    def list_packages(self) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id,package_key,name,description,category,active_version,
                    protocol_version,output_schema_version,table_name,status,created_at,updated_at
                    FROM crawler_packages ORDER BY id"""
                )
                return list(cursor.fetchall())
        finally:
            connection.close()

    def package(self, key_or_id: str | int) -> dict[str, Any]:
        column = "id" if isinstance(key_or_id, int) else "package_key"
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM crawler_packages WHERE {column}=%s", (key_or_id,))
                row = cursor.fetchone()
            if not row:
                raise KeyError(f"package not found: {key_or_id}")
            row["manifest"] = json_load(row.pop("manifest_json"), {})
            row["default_config"] = json_load(row.pop("default_config_json"), {})
            row["install_state"] = json_load(row.pop("install_state_json"), {})
            row["secret_refs"] = json_load(row.pop("secret_refs_json"), {})
            return row
        finally:
            connection.close()

    def package_default_config(self, package_key: str) -> dict[str, Any]:
        package = self.package(package_key)
        schema = package["manifest"]["parameters_schema"]
        return {
            "package_key": package_key, "name": package["name"],
            "parameters_schema": schema,
            "config": validate_parameters(schema, package["default_config"]),
        }

    def update_package_default_config(self, package_key: str, config: dict[str, Any]) -> dict[str, Any]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name,manifest_json FROM crawler_packages WHERE package_key=%s FOR UPDATE",
                    (package_key,),
                )
                package = cursor.fetchone()
                if not package:
                    raise KeyError(f"package not found: {package_key}")
                schema = json_load(package["manifest_json"], {})["parameters_schema"]
                normalized = validate_parameters(schema, config)
                cursor.execute(
                    "UPDATE crawler_packages SET default_config_json=%s,updated_at=NOW(6) WHERE package_key=%s",
                    (json_dump(normalized), package_key),
                )
            connection.commit()
            return {"package_key": package_key, "name": package["name"],
                    "parameters_schema": schema, "config": normalized}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_monitor(self, name: str, query: str, aliases: list[str], categories: list[str],
                       package_keys: list[str] | None, schedule_type: str = "manual",
                       schedule_time: str | None = None, weekday: int | None = None,
                       timezone_name: str = "Asia/Shanghai",
                       package_settings: list[dict[str, Any]] | None = None) -> int:
        categories = list(dict.fromkeys(normalize_category(value) for value in categories))
        if schedule_type not in {"manual", "daily", "weekly"}:
            raise ValueError("invalid schedule_type")
        if timezone_name != "Asia/Shanghai":
            raise ValueError("timezone must be Asia/Shanghai")
        name_key = monitor_name_key(name)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("name and query are required")
        settings_by_key: dict[str, dict[str, Any]] = {}
        if package_settings is not None:
            if not isinstance(package_settings, list) or not package_settings:
                raise ValueError("at least one package setting is required")
            for setting in package_settings:
                if not isinstance(setting, dict) or not isinstance(setting.get("package_key"), str):
                    raise ValueError("invalid package setting")
                package_key = setting["package_key"]
                if package_key in settings_by_key:
                    raise ValueError(f"duplicate package setting: {package_key}")
                settings_by_key[package_key] = setting
            if not any(setting.get("enabled", True) is True for setting in package_settings):
                raise ValueError("at least one package must be enabled")
            package_keys = list(settings_by_key)
        next_run = None
        if schedule_type != "manual":
            if not schedule_time:
                raise ValueError("scheduled monitor requires schedule_time")
            next_run = self._next_run(schedule_type, schedule_time, weekday)
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO monitors(name,query_text,aliases_json,selected_categories_json,
                    schedule_type,schedule_time,weekday,timezone,next_run_at,active_name_key)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        name.strip(), query.strip(), json_dump(aliases), json_dump(categories),
                        schedule_type, schedule_time, weekday, timezone_name, next_run, name_key,
                    ),
                )
                monitor_id = cursor.lastrowid
                if package_keys:
                    placeholders = ",".join(["%s"] * len(package_keys))
                    cursor.execute(
                        f"""SELECT id,package_key,manifest_json,default_config_json
                        FROM crawler_packages WHERE status='ready' AND package_key IN ({placeholders})""",
                        package_keys,
                    )
                else:
                    cursor.execute(
                        """SELECT id,package_key,manifest_json,default_config_json
                        FROM crawler_packages WHERE status='ready'
                        AND JSON_CONTAINS(%s,JSON_QUOTE(category))""",
                        (json_dump(categories),),
                    )
                rows = cursor.fetchall()
                if settings_by_key:
                    found = {row["package_key"] for row in rows}
                    missing = sorted(set(settings_by_key) - found)
                    if missing:
                        raise ValueError(f"packages are missing or not ready: {missing}")
                for row in rows:
                    setting = settings_by_key.get(row["package_key"], {})
                    enabled = setting.get("enabled", True)
                    if not isinstance(enabled, bool):
                        raise ValueError(f"enabled must be boolean: {row['package_key']}")
                    item_limit = self._item_limit(setting.get("item_limit", 100))
                    config = setting.get("config", {})
                    if not isinstance(config, dict):
                        raise ValueError(f"config must be an object: {row['package_key']}")
                    manifest = json_load(row["manifest_json"], {})
                    merged = json_load(row["default_config_json"], {})
                    merged.update(config)
                    normalized_config = validate_parameters(manifest["parameters_schema"], merged)
                    cursor.execute(
                        """INSERT INTO monitor_packages
                        (monitor_id,package_id,enabled,item_limit,config_json)
                        VALUES(%s,%s,%s,%s,%s)""",
                        (monitor_id, row["id"], enabled, item_limit, json_dump(normalized_config)),
                    )
            connection.commit()
            return monitor_id
        except pymysql.IntegrityError as exc:
            connection.rollback()
            if exc.args and exc.args[0] == 1062:
                raise MonitorNameConflict("active monitor name already exists") from exc
            raise
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_monitors(self, status: str = "active") -> list[dict[str, Any]]:
        if status not in {"active", "archived", "all"}:
            raise ValueError("status must be active, archived or all")
        where = {"active": "WHERE archived_at IS NULL", "archived": "WHERE archived_at IS NOT NULL", "all": ""}[status]
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM monitors {where} ORDER BY id DESC")
                rows = list(cursor.fetchall())
            for row in rows:
                row["aliases"] = json_load(row.pop("aliases_json"), [])
                row["selected_categories"] = json_load(row.pop("selected_categories_json"), [])
                row.pop("active_name_key", None)
            return rows
        finally:
            connection.close()

    def archive_monitor(self, monitor_id: int) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,archived_at FROM monitors WHERE id=%s FOR UPDATE", (monitor_id,))
                monitor = cursor.fetchone()
                if monitor is None:
                    raise KeyError(f"monitor not found: {monitor_id}")
                if monitor["archived_at"] is not None:
                    connection.rollback()
                    return
                cursor.execute(
                    "SELECT id FROM monitor_runs WHERE monitor_id=%s AND status IN ('queued','running') LIMIT 1",
                    (monitor_id,),
                )
                if cursor.fetchone():
                    raise ValueError("monitor has an active collection; archive after it finishes")
                cursor.execute(
                    "SELECT id FROM weekly_reports WHERE monitor_id=%s AND status='running' LIMIT 1",
                    (monitor_id,),
                )
                if cursor.fetchone():
                    raise ValueError("monitor has an active weekly report; archive after it finishes")
                cursor.execute(
                    "UPDATE monitors SET archived_at=NOW(6),active_name_key=NULL,enabled=0,next_run_at=NULL WHERE id=%s",
                    (monitor_id,),
                )
                cursor.execute(
                    "UPDATE weekly_reports SET status='cancelled',finished_at=NOW(6),"
                    "error_message='monitor archived' WHERE monitor_id=%s AND status='queued'",
                    (monitor_id,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def restore_monitor(self, monitor_id: int, name: str | None = None) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,name,archived_at FROM monitors WHERE id=%s FOR UPDATE", (monitor_id,))
                monitor = cursor.fetchone()
                if monitor is None:
                    raise KeyError(f"monitor not found: {monitor_id}")
                if monitor["archived_at"] is None:
                    raise ValueError("monitor is not archived")
                restored_name = name if name is not None else monitor["name"]
                name_key = monitor_name_key(restored_name)
                cursor.execute(
                    "UPDATE monitors SET name=%s,active_name_key=%s,archived_at=NULL,"
                    "enabled=0,next_run_at=NULL WHERE id=%s",
                    (restored_name.strip(), name_key, monitor_id),
                )
            connection.commit()
        except pymysql.IntegrityError as exc:
            connection.rollback()
            if exc.args and exc.args[0] == 1062:
                raise MonitorNameConflict("active monitor name already exists; enter another name to restore") from exc
            raise
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def monitor_package_settings(self, monitor_id: int) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM monitors WHERE id=%s", (monitor_id,))
                if not cursor.fetchone():
                    raise KeyError(f"monitor not found: {monitor_id}")
                cursor.execute(
                    """SELECT p.package_key,p.name,p.description,p.category,
                    p.default_config_json,p.manifest_json,
                    mp.monitor_id,mp.enabled,mp.item_limit,mp.config_json,
                    mp.cursor_version,mp.last_success_at,mp.last_error
                    FROM crawler_packages p
                    LEFT JOIN monitor_packages mp
                      ON mp.package_id=p.id AND mp.monitor_id=%s
                    WHERE p.status='ready' ORDER BY p.id""",
                    (monitor_id,),
                )
                rows = list(cursor.fetchall())
            output = []
            for row in rows:
                manifest = json_load(row.pop("manifest_json"), {})
                defaults = json_load(row.pop("default_config_json"), {})
                configured = json_load(row.pop("config_json"), {})
                defaults.update(configured)
                attached = row.pop("monitor_id") is not None
                row["attached"] = attached
                row["enabled"] = bool(row["enabled"]) if attached else False
                row["item_limit"] = int(row["item_limit"]) if attached else 100
                row["config"] = defaults
                row["parameters_schema"] = manifest.get("parameters_schema", {
                    "type": "object", "properties": {}, "additionalProperties": False,
                })
                output.append(row)
            return output
        finally:
            connection.close()

    def update_monitor_packages(self, monitor_id: int,
                                package_settings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(package_settings, list) or not package_settings:
            raise ValueError("at least one package setting is required")
        by_key: dict[str, dict[str, Any]] = {}
        for setting in package_settings:
            if not isinstance(setting, dict) or not isinstance(setting.get("package_key"), str):
                raise ValueError("invalid package setting")
            key = setting["package_key"]
            if key in by_key:
                raise ValueError(f"duplicate package setting: {key}")
            by_key[key] = setting
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,archived_at FROM monitors WHERE id=%s FOR UPDATE", (monitor_id,))
                monitor = cursor.fetchone()
                if not monitor:
                    raise KeyError(f"monitor not found: {monitor_id}")
                if monitor["archived_at"] is not None:
                    raise ValueError("archived monitor cannot change package settings")
                placeholders = ",".join(["%s"] * len(by_key))
                cursor.execute(
                    f"""SELECT id,package_key,manifest_json,default_config_json
                    FROM crawler_packages WHERE status='ready'
                    AND package_key IN ({placeholders}) FOR UPDATE""",
                    list(by_key),
                )
                packages = cursor.fetchall()
                found = {row["package_key"] for row in packages}
                missing = sorted(set(by_key) - found)
                if missing:
                    raise ValueError(f"packages are missing or not ready: {missing}")
                for package in packages:
                    setting = by_key[package["package_key"]]
                    enabled = setting.get("enabled", True)
                    if not isinstance(enabled, bool):
                        raise ValueError(f"enabled must be boolean: {package['package_key']}")
                    item_limit = self._item_limit(setting.get("item_limit", 100))
                    config = setting.get("config", {})
                    if not isinstance(config, dict):
                        raise ValueError(f"config must be an object: {package['package_key']}")
                    manifest = json_load(package["manifest_json"], {})
                    merged = json_load(package["default_config_json"], {})
                    merged.update(config)
                    normalized_config = validate_parameters(manifest["parameters_schema"], merged)
                    cursor.execute(
                        """INSERT INTO monitor_packages
                        (monitor_id,package_id,enabled,item_limit,config_json)
                        VALUES(%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE enabled=VALUES(enabled),
                        item_limit=VALUES(item_limit),config_json=VALUES(config_json),
                        updated_at=NOW(6)""",
                        (
                            monitor_id, package["id"], enabled, item_limit,
                            json_dump(normalized_config),
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.monitor_package_settings(monitor_id)

    @staticmethod
    def _item_limit(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000:
            raise ValueError("item_limit must be an integer from 1 to 10000")
        return value

    def enqueue_monitor(self, monitor_id: int, trigger: str = "manual",
                        dedupe_key: str | None = None,
                        expected_due: datetime | None = None) -> int:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM monitors WHERE id=%s FOR UPDATE", (monitor_id,))
                monitor = cursor.fetchone()
                if not monitor or not monitor["enabled"] or monitor["archived_at"] is not None:
                    raise ValueError("monitor is missing or disabled")
                if trigger == "scheduled":
                    if expected_due is None or monitor["next_run_at"] != expected_due:
                        raise ValueError("scheduled slot has changed")
                    if expected_due > datetime.now(timezone.utc).replace(tzinfo=None):
                        raise ValueError("scheduled slot is not due")
                cursor.execute(
                    "SELECT id FROM monitor_runs WHERE monitor_id=%s AND status IN ('queued','running') LIMIT 1",
                    (monitor_id,),
                )
                active = cursor.fetchone()
                if active:
                    raise ValueError(f"monitor already has active run: {active['id']}")
                cursor.execute(
                    """SELECT mp.*,p.package_key,p.active_version,p.output_schema_version,
                    p.artifact_digest,p.active_artifact_path,p.default_config_json,p.manifest_json
                    FROM monitor_packages mp JOIN crawler_packages p ON p.id=mp.package_id
                    WHERE mp.monitor_id=%s AND mp.enabled=1 AND p.status='ready' ORDER BY p.id""",
                    (monitor_id,),
                )
                packages = cursor.fetchall()
                if not packages:
                    raise ValueError("monitor has no runnable packages")
                snapshot = {
                    "query": monitor["query_text"],
                    "aliases": json_load(monitor["aliases_json"], []),
                    "packages": [row["package_key"] for row in packages],
                }
                key = dedupe_key or str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO monitor_runs
                    (monitor_id,trigger_type,dedupe_key,status,request_snapshot_json,scheduled_for)
                    VALUES(%s,%s,%s,'queued',%s,%s)""",
                    (monitor_id, trigger, key, json_dump(snapshot), expected_due),
                )
                run_id = cursor.lastrowid
                for row in packages:
                    repair_lock = (self.settings.environments_dir / row["package_key"]
                                   / (row["active_version"] + ".repair.lock"))
                    if repair_lock.exists():
                        raise ValueError(f"package environment is being rebuilt: {row['package_key']}")
                    manifest = json_load(row["manifest_json"], {})
                    merged = json_load(row["default_config_json"], {})
                    merged.update(json_load(row["config_json"], {}))
                    request = {
                        "protocol_version": "1.0",
                        "execution_id": str(uuid.uuid4()),
                        "package_key": row["package_key"],
                        "package_version": row["active_version"],
                        "query": monitor["query_text"],
                        "aliases": snapshot["aliases"],
                        "limit": int(row["item_limit"]),
                        "parameters": validate_parameters(manifest["parameters_schema"], merged),
                        "cursor": None if trigger == "scheduled" else json_load(row["cursor_json"], None),
                        "cursor_version": int(row["cursor_version"]),
                        "time_range": {"from": None, "to": None},
                    }
                    cursor.execute(
                        """INSERT INTO package_runs
                        (run_id,package_id,attempt_no,execution_id,package_version,schema_version,
                         artifact_digest,artifact_path,request_snapshot_json,status)
                        VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,'queued')""",
                        (
                            run_id, row["package_id"], request["execution_id"],
                            row["active_version"], row["output_schema_version"],
                            row["artifact_digest"], row["active_artifact_path"], json_dump(request),
                        ),
                    )
                cursor.execute(
                    "UPDATE monitor_runs SET status='running',started_at=NOW(6) WHERE id=%s",
                    (run_id,),
                )
                cursor.execute(
                    "UPDATE monitors SET last_run_at=NOW(6) WHERE id=%s", (monitor_id,)
                )
                if trigger == "scheduled":
                    next_run = self._next_run(
                        monitor["schedule_type"], str(monitor["schedule_time"]),
                        monitor["weekday"], after=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                    cursor.execute(
                        "UPDATE monitors SET next_run_at=%s WHERE id=%s",
                        (next_run, monitor_id),
                    )
            connection.commit()
            return run_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue_due_monitors(self) -> list[int]:
        connection = self.connect()
        monitor_ids: list[int] = []
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT m.id,m.next_run_at FROM monitors m
                    WHERE m.enabled=1 AND m.archived_at IS NULL AND m.schedule_type<>'manual' AND m.next_run_at<=NOW(6)
                    AND NOT EXISTS (
                        SELECT 1 FROM monitor_runs r WHERE r.monitor_id=m.id
                        AND r.status IN ('queued','running')
                    )
                    ORDER BY m.next_run_at LIMIT 20"""
                )
                due = cursor.fetchall()
            connection.rollback()
        finally:
            connection.close()
        for row in due:
            slot = row["next_run_at"]
            try:
                run_id = self.enqueue_monitor(
                    row["id"], "scheduled", f"schedule:{row['id']}:{slot.isoformat()}",
                    expected_due=slot,
                )
                monitor_ids.append(run_id)
            except (ValueError, pymysql.IntegrityError):
                continue
        return monitor_ids

    def update_monitor_schedule(self, monitor_id: int, schedule_type: str,
                                schedule_time: str | None, weekday: int | None = None,
                                enabled: bool = True) -> None:
        if schedule_type not in {"manual", "daily", "weekly"} or not isinstance(enabled, bool):
            raise ValueError("invalid schedule settings")
        if schedule_type != "manual" and not schedule_time:
            raise ValueError("scheduled monitor requires schedule_time")
        next_run = self._next_run(schedule_type, schedule_time, weekday) if schedule_type != "manual" else None
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,archived_at FROM monitors WHERE id=%s FOR UPDATE", (monitor_id,))
                monitor = cursor.fetchone()
                if not monitor:
                    raise KeyError(f"monitor not found: {monitor_id}")
                if monitor["archived_at"] is not None:
                    raise ValueError("archived monitor cannot be scheduled")
                cursor.execute(
                    """UPDATE monitors SET schedule_type=%s,schedule_time=%s,weekday=%s,
                    enabled=%s,next_run_at=%s WHERE id=%s""",
                    (schedule_type, schedule_time if schedule_type != "manual" else None,
                     weekday if schedule_type == "weekly" else None, enabled, next_run, monitor_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_package_run(self, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id FROM package_runs
                    WHERE status='queued' AND available_at<=NOW(6)
                    ORDER BY id LIMIT 1 FOR UPDATE"""
                )
                row = cursor.fetchone()
                if not row:
                    connection.rollback()
                    return None
                token = str(uuid.uuid4())
                cursor.execute(
                    """UPDATE package_runs SET status='running',worker_id=%s,lease_token=%s,
                    lease_expires_at=DATE_ADD(NOW(6),INTERVAL %s SECOND),heartbeat_at=NOW(6),
                    started_at=COALESCE(started_at,NOW(6)) WHERE id=%s""",
                    (worker_id, token, lease_seconds, row["id"]),
                )
                cursor.execute(
                    """SELECT pr.*,mr.monitor_id,p.package_key,p.table_name,p.manifest_json
                    FROM package_runs pr
                    JOIN monitor_runs mr ON mr.id=pr.run_id
                    JOIN crawler_packages p ON p.id=pr.package_id WHERE pr.id=%s""",
                    (row["id"],),
                )
                claimed = cursor.fetchone()
            connection.commit()
            claimed["request"] = json_load(claimed.pop("request_snapshot_json"), {})
            claimed["manifest"] = json_load(claimed.pop("manifest_json"), {})
            return claimed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def renew_package_run_lease(self, package_run_id: int, lease_token: str,
                                lease_seconds: int = 120) -> bool:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE package_runs SET heartbeat_at=NOW(6),
                    lease_expires_at=DATE_ADD(NOW(6),INTERVAL %s SECOND)
                    WHERE id=%s AND status='running' AND lease_token=%s
                    AND lease_expires_at>NOW(6)""",
                    (lease_seconds, package_run_id, lease_token),
                )
                renewed = cursor.rowcount == 1
            connection.commit()
            return renewed
        finally:
            connection.close()

    @staticmethod
    def _queue_retry(cursor, row: dict[str, Any], max_attempts: int = 3) -> bool:
        cursor.execute(
            """SELECT status,request_snapshot_json FROM package_runs
            WHERE run_id=%s AND package_id=%s AND attempt_no<=%s
            ORDER BY attempt_no DESC LIMIT %s""",
            (row["run_id"], row["package_id"], row["attempt_no"], max_attempts),
        )
        request = json_load(row["request_snapshot_json"], {})
        failures = 0
        for previous in cursor.fetchall():
            prior = json_load(previous["request_snapshot_json"], {})
            if (previous["status"] not in {"failed", "timed_out"} or
                prior.get("cursor") != request.get("cursor") or
                prior.get("cursor_version") != request.get("cursor_version")):
                break
            failures += 1
        if failures >= max_attempts:
            return False
        request["execution_id"] = str(uuid.uuid4())
        cursor.execute(
            """INSERT INTO package_runs
            (run_id,package_id,attempt_no,execution_id,package_version,schema_version,
             artifact_digest,artifact_path,request_snapshot_json,status,available_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',DATE_ADD(NOW(6),INTERVAL %s SECOND))""",
            (row["run_id"], row["package_id"], row["attempt_no"] + 1,
             request["execution_id"], row["package_version"], row["schema_version"],
             row["artifact_digest"], row["artifact_path"], json_dump(request), 30 * failures),
        )
        return True

    def recover_expired_package_runs(self, max_attempts: int = 3) -> int:
        connection = self.connect()
        recovered = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM package_runs WHERE status='running'
                    AND (lease_expires_at<NOW(6) OR
                         (lease_expires_at IS NULL AND started_at<DATE_SUB(NOW(6),INTERVAL 1 HOUR)))
                    ORDER BY started_at LIMIT 20 FOR UPDATE"""
                )
                expired = list(cursor.fetchall())
                for row in expired:
                    cursor.execute(
                        """UPDATE package_runs SET status='timed_out',error_code='LEASE_EXPIRED',
                        error_message='Worker stopped renewing its lease',finished_at=NOW(6),
                        lease_token=NULL,lease_expires_at=NULL WHERE id=%s""",
                        (row["id"],),
                    )
                    recovered += int(self._queue_retry(cursor, row, max_attempts))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT r.id FROM monitor_runs r WHERE r.status='running'
                    AND NOT EXISTS (SELECT 1 FROM package_runs p WHERE p.run_id=r.id
                                    AND p.status IN ('queued','running'))
                    ORDER BY r.id LIMIT 20"""
                )
                orphan_ids = [row["id"] for row in cursor.fetchall()]
        finally:
            connection.close()
        for run_id in orphan_ids:
            self.finalize_parent_run(run_id)
        return recovered

    def fail_package_run(self, package_run_id: int, lease_token: str, status: str,
                         code: str, message: str, exit_code: int | None,
                         work_dir: Path, log_path: Path, retryable: bool = False) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE package_runs SET status=%s,error_code=%s,error_message=%s,
                    exit_code=%s,work_dir=%s,log_path=%s,finished_at=NOW(6),
                    lease_expires_at=NULL WHERE id=%s AND status='running' AND lease_token=%s""",
                    (status, code, message[:8000], exit_code, str(work_dir), str(log_path), package_run_id, lease_token),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    return
                if retryable:
                    cursor.execute("SELECT * FROM package_runs WHERE id=%s", (package_run_id,))
                    self._queue_retry(cursor, cursor.fetchone())
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        self.finalize_parent_for_package_run(package_run_id)

    def ingest(self, claimed: dict[str, Any], manifest: PackageManifest,
               valid_items: list[dict[str, Any]], rejected: int,
               result: dict[str, Any], exit_code: int, work_dir: Path, log_path: Path) -> dict[str, int]:
        table = claimed["table_name"]
        self._assert_table(table)
        package_status = result["status"]
        final_status = "partial" if rejected or package_status == "partial" else "completed"
        connection = self.connect()
        stats = {"fetched": len(valid_items) + rejected, "inserted": 0, "updated": 0, "unchanged": 0, "rejected": rejected, "batch_duplicates": 0}
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM package_runs WHERE id=%s FOR UPDATE", (claimed["id"],)
                )
                active = cursor.fetchone()
                if not active or active["status"] != "running" or active["lease_token"] != claimed["lease_token"]:
                    raise RuntimeError("package run lease is no longer valid")
                cursor.execute(
                    """SELECT * FROM monitor_packages WHERE monitor_id=%s AND package_id=%s FOR UPDATE""",
                    (claimed["monitor_id"], claimed["package_id"]),
                )
                link = cursor.fetchone()
                expected_cursor_version = int(claimed["request"].get("cursor_version", 0))
                if not link or int(link["cursor_version"]) != expected_cursor_version:
                    raise RuntimeError("monitor package cursor changed during execution")
                stalled = cursor_is_stalled(claimed["request"].get("cursor"), result)
                if stalled:
                    final_status = "partial"
                    result["warnings"].append({
                        "code": "CURSOR_STALLED",
                        "message": "has_more is true but next_cursor did not advance",
                    })
                if final_status == "completed" and result.get("has_more") and claimed["attempt_no"] >= 100:
                    final_status = "partial"
                    result["warnings"].append({
                        "code": "PAGE_LIMIT", "message": "scheduled collection stopped after 100 pages",
                    })
                deduped: dict[bytes, dict[str, Any]] = {}
                for item in valid_items:
                    digest = identity_digest(manifest, item)
                    if digest in deduped:
                        stats["batch_duplicates"] += 1
                    deduped[digest] = item
                for identity_hash, item in deduped.items():
                    cursor.execute(
                        f"SELECT * FROM `{table}` WHERE sys_identity_hash=%s FOR UPDATE",
                        (identity_hash,),
                    )
                    existing = cursor.fetchone()
                    now = datetime.utcnow()
                    if existing:
                        merged = {
                            field.name: existing.get(field.name) for field in manifest.fields
                        }
                        merged.update(item)
                        new_hash = content_digest(merged)
                        changed = new_hash != existing["sys_content_hash"]
                        assignments = [f"`{name}`=%s" for name in item]
                        values = [self._db_value(manifest.field_map[name], value) for name, value in item.items()]
                        assignments.extend([
                            "sys_content_hash=%s", "sys_last_package_run_id=%s", "sys_last_seen_at=%s",
                        ])
                        values.extend([new_hash, claimed["id"], now, existing["sys_id"]])
                        cursor.execute(
                            f"UPDATE `{table}` SET {','.join(assignments)} WHERE sys_id=%s", values,
                        )
                        uid = existing["sys_resource_uid"]
                        stats["updated" if changed else "unchanged"] += 1
                    else:
                        uid = str(uuid.uuid4())
                        full = {field.name: item.get(field.name) for field in manifest.fields}
                        new_hash = content_digest(full)
                        columns = [field.name for field in manifest.fields]
                        values = [self._db_value(field, full[field.name]) for field in manifest.fields]
                        columns.extend([
                            "sys_resource_uid", "sys_identity_hash", "sys_content_hash",
                            "sys_first_package_run_id", "sys_last_package_run_id",
                            "sys_first_seen_at", "sys_last_seen_at",
                        ])
                        values.extend([uid, identity_hash, new_hash, claimed["id"], claimed["id"], now, now])
                        placeholders = ",".join(["%s"] * len(values))
                        cursor.execute(
                            f"INSERT INTO `{table}` ({','.join(f'`{name}`' for name in columns)}) VALUES({placeholders})",
                            values,
                        )
                        stats["inserted"] += 1
                    cursor.execute(
                        """INSERT INTO monitor_resource_matches
                        (monitor_id,package_id,resource_uid,first_run_id,last_run_id,
                         first_package_run_id,last_package_run_id)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                          match_count=match_count+IF(last_run_id<>VALUES(last_run_id),1,0),
                          last_run_id=VALUES(last_run_id),last_package_run_id=VALUES(last_package_run_id),
                          last_matched_at=NOW(6)""",
                        (
                            claimed["monitor_id"], claimed["package_id"], uid,
                            claimed["run_id"], claimed["run_id"], claimed["id"], claimed["id"],
                        ),
                    )
                if final_status == "completed":
                    next_cursor = result.get("next_cursor")
                    cursor.execute(
                        """UPDATE monitor_packages SET cursor_json=%s,cursor_version=cursor_version+1,
                        last_success_at=NOW(6),last_error=NULL WHERE monitor_id=%s AND package_id=%s""",
                        (json_dump(next_cursor) if next_cursor is not None else None, claimed["monitor_id"], claimed["package_id"]),
                    )
                    if result.get("has_more"):
                        continuation = dict(claimed["request"])
                        continuation["execution_id"] = str(uuid.uuid4())
                        continuation["cursor"] = next_cursor
                        continuation["cursor_version"] = expected_cursor_version + 1
                        cursor.execute(
                            """INSERT INTO package_runs
                            (run_id,package_id,attempt_no,execution_id,package_version,schema_version,
                             artifact_digest,artifact_path,request_snapshot_json,status)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued')""",
                            (claimed["run_id"], claimed["package_id"], claimed["attempt_no"] + 1,
                             continuation["execution_id"], claimed["package_version"],
                             claimed["schema_version"], claimed["artifact_digest"],
                             claimed["artifact_path"], json_dump(continuation)),
                        )
                else:
                    cursor.execute(
                        "UPDATE monitor_packages SET last_error=%s WHERE monitor_id=%s AND package_id=%s",
                        (
                            "cursor_stalled; cursor retained" if stalled else "partial result; cursor retained",
                            claimed["monitor_id"], claimed["package_id"],
                        ),
                    )
                cursor.execute(
                    """UPDATE package_runs SET status=%s,exit_code=%s,fetched=%s,inserted=%s,
                    updated=%s,unchanged=%s,rejected=%s,batch_duplicates=%s,result_json=%s,
                    work_dir=%s,log_path=%s,finished_at=NOW(6),lease_expires_at=NULL
                    WHERE id=%s AND lease_token=%s""",
                    (
                        final_status, exit_code, stats["fetched"], stats["inserted"], stats["updated"],
                        stats["unchanged"], stats["rejected"], stats["batch_duplicates"],
                        json_dump(result), str(work_dir), str(log_path), claimed["id"], claimed["lease_token"],
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        self.finalize_parent_for_package_run(claimed["id"])
        return stats

    def finalize_parent_for_package_run(self, package_run_id: int) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT run_id FROM package_runs WHERE id=%s", (package_run_id,))
                row = cursor.fetchone()
                if not row:
                    return
                run_id = row["run_id"]
        finally:
            connection.close()
        self.finalize_parent_run(run_id)

    def finalize_parent_run(self, run_id: int) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,status FROM monitor_runs WHERE id=%s FOR UPDATE", (run_id,))
                parent = cursor.fetchone()
                if not parent or parent["status"] != "running":
                    connection.rollback()
                    return
                cursor.execute("SELECT * FROM package_runs WHERE run_id=%s", (run_id,))
                children = cursor.fetchall()
                if any(child["status"] in {"queued", "running"} for child in children):
                    return
                latest = {}
                for child in children:
                    latest[child["package_id"]] = child
                final_children = list(latest.values())
                good = [child for child in children if child["status"] in {"completed", "partial"}]
                if final_children and all(child["status"] == "completed" for child in final_children):
                    status = "completed"
                elif good:
                    status = "partial"
                else:
                    status = "failed"
                totals = {
                    key: sum(int(child[key]) for child in children)
                    for key in ("fetched", "inserted", "updated", "unchanged", "rejected")
                }
                errors = "; ".join(
                    f"{child['error_code']}: {child['error_message']}"
                    for child in final_children if child.get("error_message")
                )
                cursor.execute(
                    """UPDATE monitor_runs SET status=%s,fetched=%s,inserted=%s,updated=%s,
                    unchanged=%s,rejected=%s,error_message=%s,finished_at=NOW(6) WHERE id=%s""",
                    (
                        status, totals["fetched"], totals["inserted"], totals["updated"],
                        totals["unchanged"], totals["rejected"], errors or None, run_id,
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    def run(self, run_id: int) -> dict[str, Any]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM monitor_runs WHERE id=%s", (run_id,))
                run = cursor.fetchone()
                if not run:
                    raise KeyError(f"run not found: {run_id}")
                cursor.execute(
                    """SELECT pr.id,pr.package_id,p.package_key,pr.attempt_no,pr.execution_id,
                    pr.status,pr.fetched,pr.inserted,pr.updated,pr.unchanged,pr.rejected,
                    pr.error_code,pr.error_message,pr.started_at,pr.finished_at,
                    pe.id AS proxy_id,pe.name AS proxy_name
                    FROM package_runs pr JOIN crawler_packages p ON p.id=pr.package_id
                    LEFT JOIN proxy_run_assignments pa ON pa.package_run_id=pr.id
                    LEFT JOIN proxy_endpoints pe ON pe.id=pa.proxy_endpoint_id
                    WHERE pr.run_id=%s ORDER BY pr.id""",
                    (run_id,),
                )
                run["packages"] = list(cursor.fetchall())
            run["request_snapshot"] = json_load(run.pop("request_snapshot_json"), {})
            return run
        finally:
            connection.close()

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT r.id,r.monitor_id,m.name AS monitor_name,r.trigger_type,r.status,
                    r.fetched,r.inserted,r.updated,r.unchanged,r.rejected,
                    r.started_at,r.finished_at,r.created_at
                    FROM monitor_runs r JOIN monitors m ON m.id=r.monitor_id
                    ORDER BY r.id DESC LIMIT %s""",
                    (max(1, min(limit, 200)),),
                )
                return list(cursor.fetchall())
        finally:
            connection.close()

    def package_records(self, package_key: str, limit: int = 50, after_id: int | None = None) -> list[dict[str, Any]]:
        package = self.package(package_key)
        table = package["table_name"]
        self._assert_table(table)
        manifest = load_manifest(Path(package["active_artifact_path"]))
        columns = ["sys_id", "sys_resource_uid", "sys_first_seen_at", "sys_last_seen_at"] + [field.name for field in manifest.fields]
        where = "WHERE sys_id < %s" if after_id else ""
        params: list[Any] = [after_id] if after_id else []
        params.append(max(1, min(limit, 500)))
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {','.join(f'`{column}`' for column in columns)} FROM `{table}` {where} ORDER BY sys_id DESC LIMIT %s",
                    params,
                )
                return list(cursor.fetchall())
        finally:
            connection.close()

    def monitor_records(self, monitor_id: int, limit: int = 50) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT m.package_id,p.package_key,p.table_name,p.active_artifact_path,
                    m.resource_uid,m.first_matched_at,m.last_matched_at,m.match_count
                    FROM monitor_resource_matches m JOIN crawler_packages p ON p.id=m.package_id
                    WHERE m.monitor_id=%s ORDER BY m.first_matched_at DESC,m.package_id,m.resource_uid LIMIT %s""",
                    (monitor_id, max(1, min(limit, 500))),
                )
                matches = list(cursor.fetchall())
                output = []
                for match in matches:
                    self._assert_table(match["table_name"])
                    manifest = load_manifest(Path(match["active_artifact_path"]))
                    mapping = manifest.mapping
                    selected = ["sys_resource_uid"] + list(dict.fromkeys(mapping.values()))
                    cursor.execute(
                        f"SELECT {','.join(f'`{name}`' for name in selected)} FROM `{match['table_name']}` WHERE sys_resource_uid=%s",
                        (match["resource_uid"],),
                    )
                    record = cursor.fetchone()
                    if record:
                        output.append({
                            "package_key": match["package_key"],
                            "resource_uid": match["resource_uid"],
                            "common": {key: record.get(field) for key, field in mapping.items()},
                            "first_matched_at": match["first_matched_at"],
                            "last_matched_at": match["last_matched_at"],
                            "match_count": match["match_count"],
                        })
                return output
        finally:
            connection.close()

    def set_weekly_report_enabled(self, monitor_id: int, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,archived_at FROM monitors WHERE id=%s", (monitor_id,))
                monitor = cursor.fetchone()
                if monitor is None:
                    raise KeyError(f"monitor not found: {monitor_id}")
                if monitor["archived_at"] is not None:
                    raise ValueError("archived monitor cannot change weekly report settings")
                cursor.execute("UPDATE monitors SET weekly_report_enabled=%s WHERE id=%s", (enabled, monitor_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue_weekly_report(self, monitor_id: int, week_start: date) -> int:
        week_bounds(week_start)
        if week_start > previous_week():
            raise ValueError("only completed weeks can be reported")
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,archived_at FROM monitors WHERE id=%s", (monitor_id,))
                monitor = cursor.fetchone()
                if not monitor:
                    raise KeyError(f"monitor not found: {monitor_id}")
                if monitor["archived_at"] is not None:
                    raise ValueError("archived monitor cannot generate weekly reports")
                cursor.execute("INSERT IGNORE INTO weekly_reports(monitor_id,week_start) VALUES(%s,%s)",
                               (monitor_id, week_start))
                cursor.execute("SELECT id,status FROM weekly_reports WHERE monitor_id=%s AND week_start=%s",
                               (monitor_id, week_start))
                row = cursor.fetchone()
                if row["status"] == "failed":
                    cursor.execute("UPDATE weekly_reports SET status='queued',attempts=0,available_at=NOW(6),"
                                   "error_message=NULL WHERE id=%s", (row["id"],))
            connection.commit()
            return row["id"]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue_due_weekly_reports(self) -> int:
        local = datetime.now(timezone.utc).astimezone(BEIJING)
        if local.weekday() == 0 and local.hour < 10:
            return 0
        start = previous_week(local.date())
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT IGNORE INTO weekly_reports(monitor_id,week_start) "
                    "SELECT id,%s FROM monitors WHERE enabled=1 AND archived_at IS NULL "
                    "AND weekly_report_enabled=1",
                    (start,),
                )
                count = cursor.rowcount
            connection.commit()
            return count
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_weekly_report(self) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE weekly_reports SET status='failed',error_message='worker interrupted after final attempt',"
                    "finished_at=NOW(6) WHERE status='running' AND attempts>=3 "
                    "AND started_at<DATE_SUB(NOW(6),INTERVAL 15 MINUTE)"
                )
                cursor.execute(
                    "SELECT r.id,r.monitor_id,r.week_start,r.attempts,m.query_text "
                    "FROM weekly_reports r JOIN monitors m ON m.id=r.monitor_id "
                    "WHERE m.archived_at IS NULL AND (r.status='queued' AND r.available_at<=NOW(6) OR "
                    "r.status='running' AND r.started_at<DATE_SUB(NOW(6),INTERVAL 15 MINUTE)) "
                    "AND r.attempts<3 ORDER BY r.week_start,r.id LIMIT 1 FOR UPDATE"
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE weekly_reports SET status='running',attempts=attempts+1,"
                                   "started_at=NOW(6),error_message=NULL WHERE id=%s", (row["id"],))
            connection.commit()
            return row
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def weekly_evidence(self, monitor_id: int, week_start: date) -> tuple[int, list[dict]]:
        beginning, ending = week_bounds(week_start)
        start_utc = beginning.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = ending.astimezone(timezone.utc).replace(tzinfo=None)
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM monitor_resource_matches "
                    "WHERE monitor_id=%s AND first_matched_at>=%s AND first_matched_at<%s",
                    (monitor_id, start_utc, end_utc),
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    "SELECT p.package_key,p.table_name,p.active_artifact_path,m.resource_uid,m.first_matched_at "
                    "FROM monitor_resource_matches m JOIN crawler_packages p ON p.id=m.package_id "
                    "WHERE m.monitor_id=%s AND m.first_matched_at>=%s AND m.first_matched_at<%s "
                    "ORDER BY m.first_matched_at DESC,m.package_id,m.resource_uid LIMIT %s",
                    (monitor_id, start_utc, end_utc, MAX_EVIDENCE),
                )
                matches = list(cursor.fetchall())
                evidence = []
                for match in matches:
                    self._assert_table(match["table_name"])
                    manifest = load_manifest(Path(match["active_artifact_path"]))
                    mapping = manifest.mapping
                    columns = [mapping["title"]] + [mapping[key] for key in ("url", "summary", "published_at") if key in mapping]
                    cursor.execute(
                        f"SELECT {','.join(f'`{name}`' for name in dict.fromkeys(columns))} "
                        f"FROM `{match['table_name']}` WHERE sys_resource_uid=%s",
                        (match["resource_uid"],),
                    )
                    record = cursor.fetchone()
                    if not record:
                        continue
                    evidence.append({
                        "id": len(evidence) + 1, "package_key": match["package_key"],
                        "resource_uid": match["resource_uid"], "title": str(record[mapping["title"]])[:1000],
                        "url": str(record.get(mapping["url"]))[:2048] if "url" in mapping and record.get(mapping["url"]) else None,
                        "summary": str(record.get(mapping["summary"]))[:600] if "summary" in mapping and record.get(mapping["summary"]) else None,
                        "published_at": record.get(mapping["published_at"]) if "published_at" in mapping else None,
                    })
                return total, evidence
        finally:
            connection.close()

    def finish_weekly_report(self, report_id: int, attempt: int, *, source_count: int, evidence: list[dict],
                             content: dict, model: str | None, usage: dict) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE weekly_reports SET status='completed',source_count=%s,evidence_json=%s,"
                    "content_json=%s,model=%s,usage_json=%s,error_message=NULL,finished_at=NOW(6) "
                    "WHERE id=%s AND status='running' AND attempts=%s",
                    (source_count, json_dump(evidence), json_dump(content), model, json_dump(usage), report_id, attempt),
                )
                if cursor.rowcount != 1:
                    raise ValueError("weekly report claim expired")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fail_weekly_report(self, report_id: int, attempt: int, error: str) -> None:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE weekly_reports SET status=IF(attempts>=3,'failed','queued'),"
                    "available_at=DATE_ADD(NOW(6),INTERVAL 10 MINUTE),error_message=%s,"
                    "finished_at=NOW(6) WHERE id=%s AND status='running' AND attempts=%s",
                    (error[:1000], report_id, attempt),
                )
            connection.commit()
        finally:
            connection.close()

    def list_weekly_reports(self, monitor_id: int | None = None) -> list[dict]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                where = "WHERE r.monitor_id=%s" if monitor_id is not None else ""
                cursor.execute(
                    "SELECT r.id,r.monitor_id,m.name AS monitor_name,r.week_start,r.status,"
                    "r.attempts,r.source_count,r.model,r.error_message,r.created_at,r.finished_at "
                    "FROM weekly_reports r JOIN monitors m ON m.id=r.monitor_id "
                    f"{where} ORDER BY r.week_start DESC,r.id DESC LIMIT 100",
                    (monitor_id,) if monitor_id is not None else (),
                )
                return list(cursor.fetchall())
        finally:
            connection.close()

    def weekly_report(self, report_id: int) -> dict:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT r.*,m.name AS monitor_name,m.query_text "
                               "FROM weekly_reports r JOIN monitors m ON m.id=r.monitor_id WHERE r.id=%s",
                               (report_id,))
                row = cursor.fetchone()
                if not row:
                    raise KeyError(f"weekly report not found: {report_id}")
                for key in ("evidence_json", "content_json", "usage_json"):
                    fallback = [] if key == "evidence_json" else (None if key == "content_json" else {})
                    row[key[:-5]] = json_load(row.pop(key), fallback)
                return row
        finally:
            connection.close()

    def preview_records(self, monitor_id: int | None = None, package_key: str | None = None,
                        query: str = "", page: int = 1, limit: int = 25) -> dict[str, Any]:
        if page < 1 or limit < 1 or limit > 100:
            raise ValueError("page must be positive and limit must be 1..100")
        query = query.strip()
        if len(query) > 200:
            raise ValueError("search query must not exceed 200 characters")
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                if monitor_id is not None:
                    cursor.execute("SELECT id FROM monitors WHERE id=%s", (monitor_id,))
                    if not cursor.fetchone():
                        raise KeyError(f"monitor not found: {monitor_id}")
                selection = " AND package_key=%s" if package_key else ""
                cursor.execute(
                    "SELECT id,package_key,name,table_name,active_artifact_path FROM crawler_packages "
                    "WHERE active_artifact_path IS NOT NULL" + selection + " ORDER BY id",
                    (package_key,) if package_key else (),
                )
                packages = list(cursor.fetchall())
                if package_key and not packages:
                    raise KeyError(f"installed package not found: {package_key}")
                selects, counts, select_params, count_params = [], [], [], []
                for package in packages:
                    self._assert_table(package["table_name"])
                    manifest = load_manifest(Path(package["active_artifact_path"]))
                    mapping = manifest.mapping
                    title = f"r.`{mapping['title']}`"
                    url = f"r.`{mapping['url']}`" if "url" in mapping else "NULL"
                    summary = f"SUBSTRING(r.`{mapping['summary']}`,1,600)" if "summary" in mapping else "NULL"
                    published = f"r.`{mapping['published_at']}`" if "published_at" in mapping else "NULL"
                    from_sql = f"FROM `{package['table_name']}` r"
                    params = []
                    if monitor_id is not None:
                        from_sql += (" JOIN monitor_resource_matches m ON m.resource_uid=r.sys_resource_uid "
                                     "AND m.package_id=%s AND m.monitor_id=%s")
                        params.extend([package["id"], monitor_id])
                    if query:
                        from_sql += f" WHERE {title} LIKE %s"
                        pattern = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                        params.append(f"%{pattern}%")
                    last_seen = "m.last_matched_at" if monitor_id is not None else "r.sys_last_seen_at"
                    selects.append(
                        f"SELECT %s AS package_key,%s AS package_name,r.sys_resource_uid AS resource_uid,"
                        f"{title} AS title,{url} AS url,{summary} AS summary,{published} AS published_at,"
                        f"{last_seen} AS last_seen_at {from_sql}"
                    )
                    select_params.extend([package["package_key"], package["name"], *params])
                    counts.append(f"SELECT COUNT(*) AS n {from_sql}")
                    count_params.extend(params)
                if not selects:
                    return {"items": [], "total": 0, "page": page, "limit": limit}
                cursor.execute("SELECT SUM(n) AS total FROM (" + " UNION ALL ".join(counts) + ") counted", count_params)
                total = int(cursor.fetchone()["total"] or 0)
                cursor.execute(
                    "SELECT * FROM (" + " UNION ALL ".join(selects) + ") records "
                    "ORDER BY last_seen_at DESC,package_key,resource_uid LIMIT %s OFFSET %s",
                    [*select_params, limit, (page - 1) * limit],
                )
                return {"items": list(cursor.fetchall()), "total": total, "page": page, "limit": limit}
        finally:
            connection.close()

    def record_detail(self, package_key: str, resource_uid: str) -> dict[str, Any]:
        try:
            uuid.UUID(resource_uid)
        except ValueError as exc:
            raise ValueError("invalid resource UID") from exc
        package = self.package(package_key)
        if not package["active_artifact_path"]:
            raise KeyError(f"installed package not found: {package_key}")
        self._assert_table(package["table_name"])
        manifest = load_manifest(Path(package["active_artifact_path"]))
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM `{package['table_name']}` WHERE sys_resource_uid=%s", (resource_uid,),
                )
                record = cursor.fetchone()
                if not record:
                    raise KeyError("record not found")
                for field in manifest.fields:
                    if field.type in {"array", "object"}:
                        record[field.name] = json_load(record.get(field.name), record.get(field.name))
                record.pop("sys_identity_hash", None)
                record.pop("sys_content_hash", None)
                cursor.execute(
                    """SELECT m.id,m.name,m.query_text,mrm.match_count,mrm.first_matched_at,mrm.last_matched_at
                    FROM monitor_resource_matches mrm JOIN monitors m ON m.id=mrm.monitor_id
                    WHERE mrm.package_id=%s AND mrm.resource_uid=%s ORDER BY m.id""",
                    (package["id"], resource_uid),
                )
                return {"package_key": package_key, "package_name": package["name"],
                        "record": record, "fields": manifest.raw["output_schema"]["fields"],
                        "mapping": manifest.mapping, "monitors": list(cursor.fetchall())}
        finally:
            connection.close()

    @staticmethod
    def _field_sql(field: FieldSpec) -> str:
        return {
            "string": f"VARCHAR({field.max_length})",
            "text": "LONGTEXT", "integer": "BIGINT",
            "decimal": f"DECIMAL({field.precision},{field.scale})",
            "boolean": "TINYINT(1)", "date": "DATE", "datetime": "DATETIME(6)",
            "array": "JSON", "object": "JSON",
        }[field.type]

    def _create_table_sql(self, table: str, manifest: PackageManifest) -> str:
        columns = [
            "sys_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY",
            "sys_resource_uid CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE",
            "sys_identity_hash BINARY(32) NOT NULL UNIQUE",
            "sys_content_hash BINARY(32) NOT NULL",
            "sys_first_package_run_id BIGINT UNSIGNED NOT NULL",
            "sys_last_package_run_id BIGINT UNSIGNED NOT NULL",
            "sys_first_seen_at DATETIME(6) NOT NULL",
            "sys_last_seen_at DATETIME(6) NOT NULL",
        ]
        for field in manifest.fields:
            null = "NULL" if field.nullable else "NOT NULL"
            columns.append(f"`{field.name}` {self._field_sql(field)} {null}")
        columns.extend([
            "INDEX idx_last_seen (sys_last_seen_at,sys_id)",
            "INDEX idx_first_run (sys_first_package_run_id)",
            "INDEX idx_last_run (sys_last_package_run_id)",
            f"CONSTRAINT fk_{table}_first_run FOREIGN KEY (sys_first_package_run_id) REFERENCES package_runs(id) ON DELETE RESTRICT",
            f"CONSTRAINT fk_{table}_last_run FOREIGN KEY (sys_last_package_run_id) REFERENCES package_runs(id) ON DELETE RESTRICT",
        ])
        for number, index in enumerate(manifest.indexes, 1):
            columns.append(f"INDEX idx_declared_{number} ({','.join(f'`{name}`' for name in index)})")
        return f"CREATE TABLE `{table}` ({','.join(columns)}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

    @staticmethod
    def _db_value(field: FieldSpec, value: Any) -> Any:
        if value is None:
            return None
        if field.type in {"array", "object"}:
            return json_dump(value)
        return value

    @staticmethod
    def _assert_table(table: str) -> None:
        if not isinstance(table, str) or not SAFE_TABLE.fullmatch(table):
            raise ValueError("unsafe package table name")

    @staticmethod
    def _next_run(schedule_type: str, schedule_time: str, weekday: int | None,
                  after: datetime | None = None) -> datetime:
        if schedule_type not in {"daily", "weekly"}:
            raise ValueError("invalid scheduled type")
        parts = str(schedule_time).split(":")
        if len(parts) not in {2, 3} or any(not part.isdigit() for part in parts):
            raise ValueError("schedule_time must be HH:MM or HH:MM:SS")
        hour, minute = map(int, parts[:2])
        second = int(parts[2]) if len(parts) == 3 else 0
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError("invalid schedule_time")
        if schedule_type == "weekly" and (type(weekday) is not int or not 1 <= weekday <= 7):
            raise ValueError("weekday must be 1 to 7")
        utc_now = after or datetime.now(timezone.utc).replace(tzinfo=None)
        china = timezone(timedelta(hours=8))
        local_now = utc_now.replace(tzinfo=timezone.utc).astimezone(china)
        candidate = local_now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if schedule_type == "weekly":
            candidate += timedelta(days=(weekday - 1 - candidate.weekday()) % 7)
            if candidate <= local_now:
                candidate += timedelta(days=7)
        elif candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc).replace(tzinfo=None)
