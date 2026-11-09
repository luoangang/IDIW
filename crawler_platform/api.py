from __future__ import annotations

import stat
import os
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file

from crawler_platform.config import Settings
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import ProtocolError, strict_json_loads
from crawler_platform.storage import MonitorNameConflict, PlatformStore
from crawler_platform.categories import CATEGORIES
from crawler_platform.journal_catalog import load_journal_catalog
from crawler_platform.weekly_report import previous_week
from crawler_platform.assistant import AssistantUnavailable, TaskAssistant


def json_response(value: Any, status: int = 200):
    def convert(item: Any):
        if isinstance(item, (datetime, date)):
            return item.isoformat() + ("Z" if isinstance(item, datetime) else "")
        if isinstance(item, timedelta):
            seconds = int(item.total_seconds())
            return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        if isinstance(item, bytes):
            return item.hex()
        if isinstance(item, Decimal):
            return format(item, "f")
        raise TypeError
    return app_jsonify(value, convert), status


def app_jsonify(value: Any, converter):
    from flask import current_app
    import json
    return current_app.response_class(
        json.dumps(value, ensure_ascii=False, default=converter),
        mimetype="application/json",
    )


def create_app(settings: Settings, store: PlatformStore) -> Flask:
    app = Flask(__name__)
    importer = PackageImporter(settings, store)
    assistant = TaskAssistant(store)
    app.extensions["task_assistant"] = assistant

    def authenticated(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if settings.token:
                supplied = request.headers.get("Authorization", "")
                if supplied != f"Bearer {settings.token}":
                    return jsonify({"error": "unauthorized"}), 401
            return function(*args, **kwargs)
        return wrapped

    @app.errorhandler(Exception)
    def handle_error(exc):
        status = (503 if isinstance(exc, AssistantUnavailable) else 404 if isinstance(exc, KeyError) else 409 if isinstance(exc, MonitorNameConflict)
                  else 422 if isinstance(exc, (ValueError, ProtocolError)) else 500)
        return jsonify({"error": type(exc).__name__, "message": str(exc)}), status

    @app.get("/health/live")
    def live():
        return jsonify({"status": "ok"})

    @app.get("/health/ready")
    def ready():
        store.list_packages()
        return jsonify({"status": "ready"})

    @app.get("/")
    @app.get("/sources")
    @app.get("/proxies")
    @app.get("/monitors")
    @app.get("/monitors/new")
    @app.get("/monitors/<int:monitor_id>/sources")
    @app.get("/runs")
    @app.get("/runs/<int:run_id>")
    @app.get("/data")
    @app.get("/reports")
    @app.get("/reports/<int:report_id>")
    @app.get("/assistant")
    def dashboard(**route_parameters):
        return send_file(Path(__file__).with_name("dashboard.html"))

    @app.get("/assets/task-assistant.js")
    def assistant_script():
        return send_file(Path(__file__).with_name("task-assistant.js"))

    @app.get("/api/v1/packages")
    @authenticated
    def packages():
        return json_response(store.list_packages())

    @app.get("/api/v1/categories")
    @authenticated
    def categories():
        return json_response([{"key": key, "label": label} for key, label in CATEGORIES.items()])

    def assistant_body(allowed, required):
        if request.content_length is not None and request.content_length > 128000:
            raise ValueError("助手请求过大，请开始新对话")
        raw = request.stream.read(128001)
        if len(raw) > 128000:
            raise ValueError("助手请求过大，请开始新对话")
        body = strict_json_loads(raw, "assistant request")
        if not isinstance(body, dict) or set(body) - allowed or not required <= set(body):
            raise ValueError("助手请求字段无效")
        return body

    @app.get("/api/v1/assistant/catalog")
    @authenticated
    def assistant_catalog():
        return json_response({"configured": bool(os.getenv("DEEPSEEK_API_KEY")),
                              "model": os.getenv("DEEPSEEK_ASSISTANT_MODEL", "deepseek-flash"),
                              "sources": assistant.catalog()})

    @app.post("/api/v1/assistant/chat")
    @authenticated
    def assistant_chat():
        body = assistant_body({"messages", "draft"}, {"messages"})
        return json_response(assistant.chat(body["messages"], body.get("draft")))

    @app.post("/api/v1/assistant/preview")
    @authenticated
    def assistant_preview():
        body = assistant_body({"draft"}, {"draft"})
        return json_response(assistant.preview(body["draft"]))

    @app.post("/api/v1/assistant/monitors")
    @authenticated
    def assistant_create_monitor():
        body = assistant_body({"draft", "confirmation_token", "confirmed"},
                              {"draft", "confirmation_token", "confirmed"})
        monitor_id = assistant.confirm(body["draft"], body["confirmation_token"], body["confirmed"])
        return json_response({"id": monitor_id}, 201)

    @app.get("/api/v1/proxies")
    @authenticated
    def proxies():
        return json_response(store.list_proxies())

    @app.post("/api/v1/proxies")
    @authenticated
    def create_proxy():
        body = request.get_json(force=True)
        if (not isinstance(body, dict) or not {"name", "proxy_url"} <= set(body)
                or set(body) - {"name", "proxy_url", "enabled"}):
            raise ValueError("invalid proxy fields")
        return json_response(store.create_proxy(body["name"], body["proxy_url"], body.get("enabled", True)), 201)

    @app.put("/api/v1/proxies/<int:proxy_id>")
    @authenticated
    def update_proxy(proxy_id):
        body = request.get_json(force=True)
        if not isinstance(body, dict) or set(body) != {"name", "proxy_url", "enabled"}:
            raise ValueError("name, proxy_url and enabled are required")
        return json_response(store.update_proxy(proxy_id, body["name"], body["proxy_url"], body["enabled"]))

    @app.post("/api/v1/proxies/<int:proxy_id>/check")
    @authenticated
    def check_proxy(proxy_id):
        return json_response(store.check_proxy(proxy_id))

    @app.post("/api/v1/packages/import")
    @authenticated
    def import_package():
        if "package" in request.files:
            upload = request.files["package"]
            with tempfile.TemporaryDirectory(prefix="crawler-package-") as temporary:
                archive = Path(temporary) / "package.zip"
                upload.save(archive)
                package_dir = _safe_extract(archive, Path(temporary) / "content")
                return json_response(importer.install(package_dir), 201)
        body = request.get_json(force=True)
        return json_response(importer.install(Path(body["path"])), 201)

    @app.get("/api/v1/packages/<package_key>/environment")
    @authenticated
    def package_environment(package_key):
        from crawler_platform.protocol import load_manifest
        package = store.package(package_key)
        artifact = Path(package["active_artifact_path"])
        return json_response(importer.environment_health(load_manifest(artifact), artifact))

    @app.post("/api/v1/packages/<package_key>/environment/rebuild")
    @authenticated
    def rebuild_package_environment(package_key):
        return json_response(importer.rebuild_environment(package_key))

    @app.get("/api/v1/packages/<package_key>/default-config")
    @authenticated
    def package_default_config(package_key):
        return json_response(store.package_default_config(package_key))

    @app.put("/api/v1/packages/<package_key>/default-config")
    @authenticated
    def update_package_default_config(package_key):
        body = request.get_json(force=True)
        if not isinstance(body, dict) or set(body) != {"config"}:
            raise ValueError("request must contain only config")
        return json_response(store.update_package_default_config(package_key, body["config"]))

    @app.get("/api/v1/packages/<package_key>/schema")
    @authenticated
    def package_schema(package_key):
        package = store.package(package_key)
        return json_response({"package_key": package_key, "manifest": package["manifest"]})

    @app.get("/api/v1/packages/<package_key>/journals")
    @authenticated
    def package_journals(package_key):
        package = store.package(package_key)
        return json_response(load_journal_catalog(
            Path(package["active_artifact_path"]), package["manifest"]["parameters_schema"],
        ))

    @app.get("/api/v1/packages/<package_key>/records")
    @authenticated
    def package_records(package_key):
        return json_response(store.package_records(
            package_key, int(request.args.get("limit", 50)),
            int(request.args["after_id"]) if request.args.get("after_id") else None,
        ))

    @app.get("/api/v1/data")
    @authenticated
    def preview_data():
        return json_response(store.preview_records(
            monitor_id=int(request.args["monitor"]) if request.args.get("monitor") else None,
            package_key=request.args.get("source") or None,
            query=request.args.get("q", ""), page=int(request.args.get("page", 1)),
            limit=int(request.args.get("limit", 25)),
        ))

    @app.get("/api/v1/packages/<package_key>/records/<resource_uid>")
    @authenticated
    def record_detail(package_key, resource_uid):
        return json_response(store.record_detail(package_key, resource_uid))

    @app.get("/api/v1/monitors")
    @authenticated
    def monitors():
        return json_response(store.list_monitors(request.args.get("status", "active")))

    @app.post("/api/v1/monitors")
    @authenticated
    def create_monitor():
        body = request.get_json(force=True)
        monitor_id = store.create_monitor(
            name=body["name"], query=body["query"], aliases=body.get("aliases", []),
            categories=body.get("categories", []), package_keys=body.get("package_keys"),
            schedule_type=body.get("schedule_type", "manual"),
            schedule_time=body.get("schedule_time"), weekday=body.get("weekday"),
            timezone_name=body.get("timezone", "Asia/Shanghai"),
            package_settings=body.get("packages"),
        )
        return jsonify({"id": monitor_id}), 201

    @app.post("/api/v1/monitors/<int:monitor_id>/archive")
    @authenticated
    def archive_monitor(monitor_id):
        store.archive_monitor(monitor_id)
        return json_response({"id": monitor_id, "archived": True})

    @app.post("/api/v1/monitors/<int:monitor_id>/restore")
    @authenticated
    def restore_monitor(monitor_id):
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or set(body) - {"name"}:
            raise ValueError("restore accepts only an optional name")
        store.restore_monitor(monitor_id, body.get("name"))
        return json_response({"id": monitor_id, "archived": False})

    @app.patch("/api/v1/monitors/<int:monitor_id>/schedule")
    @authenticated
    def update_monitor_schedule(monitor_id):
        body = request.get_json(force=True)
        store.update_monitor_schedule(
            monitor_id, body["schedule_type"], body.get("schedule_time"),
            body.get("weekday"), body.get("enabled", True),
        )
        return json_response({"id": monitor_id, "updated": True})

    @app.get("/api/v1/monitors/<int:monitor_id>/packages")
    @authenticated
    def monitor_packages(monitor_id):
        return json_response(store.monitor_package_settings(monitor_id))

    @app.put("/api/v1/monitors/<int:monitor_id>/packages")
    @authenticated
    def update_monitor_packages(monitor_id):
        body = request.get_json(force=True)
        return json_response(store.update_monitor_packages(monitor_id, body.get("packages")))

    @app.post("/api/v1/monitors/<int:monitor_id>/runs")
    @authenticated
    def start_run(monitor_id):
        run_id = store.enqueue_monitor(
            monitor_id, "manual", request.headers.get("Idempotency-Key"),
        )
        return jsonify({"run_id": run_id, "status": "queued"}), 202

    @app.get("/api/v1/monitors/<int:monitor_id>/records")
    @authenticated
    def monitor_records(monitor_id):
        return json_response(store.monitor_records(monitor_id, int(request.args.get("limit", 50))))

    @app.patch("/api/v1/monitors/<int:monitor_id>/weekly-report-settings")
    @authenticated
    def update_weekly_report_settings(monitor_id):
        body = request.get_json(force=True)
        if not isinstance(body, dict) or set(body) != {"enabled"} or type(body["enabled"]) is not bool:
            raise ValueError("request must contain only enabled")
        store.set_weekly_report_enabled(monitor_id, body["enabled"])
        return json_response({"id": monitor_id, "weekly_report_enabled": body["enabled"]})

    @app.post("/api/v1/monitors/<int:monitor_id>/weekly-reports")
    @authenticated
    def enqueue_weekly_report(monitor_id):
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise ValueError("DEEPSEEK_API_KEY is not configured")
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or set(body) - {"week_start"}:
            raise ValueError("invalid weekly report request")
        if "week_start" in body and not isinstance(body["week_start"], str):
            raise ValueError("week_start must be an ISO date")
        start = date.fromisoformat(body["week_start"]) if "week_start" in body else previous_week()
        report_id = store.enqueue_weekly_report(monitor_id, start)
        return json_response({"id": report_id, "status": "queued"}, 202)

    @app.get("/api/v1/weekly-reports")
    @authenticated
    def weekly_reports():
        monitor_id = int(request.args["monitor"]) if request.args.get("monitor") else None
        return json_response(store.list_weekly_reports(monitor_id))

    @app.get("/api/v1/weekly-reports/<int:report_id>")
    @authenticated
    def weekly_report(report_id):
        return json_response(store.weekly_report(report_id))

    @app.get("/api/v1/runs/<int:run_id>")
    @authenticated
    def run(run_id):
        return json_response(store.run(run_id))

    @app.get("/api/v1/runs")
    @authenticated
    def runs():
        return json_response(store.list_runs(int(request.args.get("limit", 30))))

    return app


def _safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        if len(zipped.infolist()) > 5000:
            raise ProtocolError("archive has too many files")
        total = 0
        for info in zipped.infolist():
            total += info.file_size
            if total > 250 * 1024 * 1024:
                raise ProtocolError("archive is too large after extraction")
            if info.create_system == 3:
                file_type = stat.S_IFMT(info.external_attr >> 16)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ProtocolError("archive contains a link or special file")
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ProtocolError("archive contains unsafe path")
            target = (destination / member).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ProtocolError("archive path escapes destination")
        zipped.extractall(destination)
    children = [path for path in destination.iterdir() if path.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination
