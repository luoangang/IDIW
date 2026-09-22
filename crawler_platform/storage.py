from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from crawler_platform.config import Settings
from crawler_platform.protocol import (
    FieldSpec, PackageManifest, ProtocolError, content_digest, identity_digest,
    load_manifest, validate_item, validate_parameters,
)


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
        for directory in (
            self.settings.runtime_dir, self.settings.packages_dir,
            self.settings.environments_dir, self.settings.runs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

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

    def create_monitor(self, name: str, query: str, aliases: list[str], categories: list[str],
                       package_keys: list[str] | None, schedule_type: str = "manual",
                       schedule_time: str | None = None, weekday: int | None = None,
                       timezone_name: str = "Asia/Shanghai") -> int:
        if schedule_type not in {"manual", "daily", "weekly"}:
            raise ValueError("invalid schedule_type")
        if not name.strip() or not query.strip():
            raise ValueError("name and query are required")
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
                    schedule_type,schedule_time,weekday,timezone,next_run_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        name.strip(), query.strip(), json_dump(aliases), json_dump(categories),
                        schedule_type, schedule_time, weekday, timezone_name, next_run,
                    ),
                )
                monitor_id = cursor.lastrowid
                if package_keys:
                    placeholders = ",".join(["%s"] * len(package_keys))
                    cursor.execute(
                        f"SELECT id FROM crawler_packages WHERE status='ready' AND package_key IN ({placeholders})",
                        package_keys,
                    )
                else:
                    cursor.execute(
                        "SELECT id FROM crawler_packages WHERE status='ready' AND JSON_CONTAINS(%s,JSON_QUOTE(category))",
                        (json_dump(categories),),
                    )
                rows = cursor.fetchall()
                for row in rows:
                    cursor.execute(
                        """INSERT INTO monitor_packages
                        (monitor_id,package_id,enabled,item_limit,config_json)
                        VALUES(%s,%s,1,100,'{}')""",
                        (monitor_id, row["id"]),
                    )
            connection.commit()
            return monitor_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_monitors(self) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM monitors ORDER BY id DESC")
                rows = list(cursor.fetchall())
            for row in rows:
                row["aliases"] = json_load(row.pop("aliases_json"), [])
                row["selected_categories"] = json_load(row.pop("selected_categories_json"), [])
            return rows
        finally:
            connection.close()

    def enqueue_monitor(self, monitor_id: int, trigger: str = "manual",
                        dedupe_key: str | None = None) -> int:
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM monitors WHERE id=%s FOR UPDATE", (monitor_id,))
                monitor = cursor.fetchone()
                if not monitor or not monitor["enabled"]:
                    raise ValueError("monitor is missing or disabled")
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
                    (monitor_id, trigger, key, json_dump(snapshot), monitor.get("next_run_at")),
                )
                run_id = cursor.lastrowid
                for row in packages:
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
                        "cursor": json_load(row["cursor_json"], None),
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
                    """SELECT id,schedule_type,schedule_time,weekday FROM monitors
                    WHERE enabled=1 AND schedule_type<>'manual' AND next_run_at<=NOW(6)
                    ORDER BY next_run_at LIMIT 20"""
                )
                due = cursor.fetchall()
            connection.rollback()
        finally:
            connection.close()
        for row in due:
            slot = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
            try:
                run_id = self.enqueue_monitor(row["id"], "scheduled", f"schedule:{row['id']}:{slot}")
                monitor_ids.append(run_id)
                self.advance_schedule(row["id"], row["schedule_type"], row["schedule_time"], row["weekday"])
            except (ValueError, pymysql.IntegrityError):
                continue
        return monitor_ids

    def advance_schedule(self, monitor_id: int, schedule_type: str, schedule_time: Any,
                         weekday: int | None) -> None:
        value = schedule_time.strftime("%H:%M:%S") if hasattr(schedule_time, "strftime") else str(schedule_time)
        next_run = self._next_run(schedule_type, value, weekday)
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE monitors SET next_run_at=%s WHERE id=%s", (next_run, monitor_id))
            connection.commit()
        finally:
            connection.close()

    def claim_package_run(self, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
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

    def fail_package_run(self, package_run_id: int, lease_token: str, status: str,
                         code: str, message: str, exit_code: int | None,
                         work_dir: Path, log_path: Path) -> None:
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
                    raise RuntimeError("package run lease is no longer valid")
            connection.commit()
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
                stalled = cursor_is_stalled(json_load(link["cursor_json"], None), result)
                if stalled:
                    final_status = "partial"
                    result["warnings"].append({
                        "code": "CURSOR_STALLED",
                        "message": "has_more is true but next_cursor did not advance",
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
                cursor.execute("SELECT * FROM package_runs WHERE run_id=%s", (run_id,))
                children = cursor.fetchall()
                if any(child["status"] in {"queued", "running"} for child in children):
                    return
                good = [child for child in children if child["status"] in {"completed", "partial"}]
                if good and all(child["status"] == "completed" for child in children):
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
                    for child in children if child.get("error_message")
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
                    pr.error_code,pr.error_message,pr.started_at,pr.finished_at
                    FROM package_runs pr JOIN crawler_packages p ON p.id=pr.package_id
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
    def _next_run(schedule_type: str, schedule_time: str, weekday: int | None) -> datetime:
        hour, minute, second = [int(part) for part in schedule_time.split(":")]
        now = datetime.utcnow()
        candidate = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        if schedule_type == "weekly":
            target = int(weekday or 1) - 1
            candidate += timedelta(days=(target - candidate.weekday()) % 7)
            if candidate <= now:
                candidate += timedelta(days=7)
        return candidate
