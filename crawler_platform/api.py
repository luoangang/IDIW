from __future__ import annotations

import stat
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file

from crawler_platform.config import Settings
from crawler_platform.importer import PackageImporter
from crawler_platform.protocol import ProtocolError
from crawler_platform.storage import PlatformStore


def json_response(value: Any, status: int = 200):
    def convert(item: Any):
        if isinstance(item, (datetime, date)):
            return item.isoformat() + ("Z" if isinstance(item, datetime) else "")
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
        status = 404 if isinstance(exc, KeyError) else 422 if isinstance(exc, (ValueError, ProtocolError)) else 500
        return jsonify({"error": type(exc).__name__, "message": str(exc)}), status

    @app.get("/health/live")
    def live():
        return jsonify({"status": "ok"})

    @app.get("/health/ready")
    def ready():
        store.list_packages()
        return jsonify({"status": "ready"})

    @app.get("/")
    def dashboard():
        return send_file(Path(__file__).with_name("dashboard.html"))

    @app.get("/api/v1/packages")
    @authenticated
    def packages():
        return json_response(store.list_packages())

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

    @app.get("/api/v1/packages/<package_key>/schema")
    @authenticated
    def package_schema(package_key):
        package = store.package(package_key)
        return json_response({"package_key": package_key, "manifest": package["manifest"]})

    @app.get("/api/v1/packages/<package_key>/records")
    @authenticated
    def package_records(package_key):
        return json_response(store.package_records(
            package_key, int(request.args.get("limit", 50)),
            int(request.args["after_id"]) if request.args.get("after_id") else None,
        ))

    @app.get("/api/v1/monitors")
    @authenticated
    def monitors():
        return json_response(store.list_monitors())

    @app.post("/api/v1/monitors")
    @authenticated
    def create_monitor():
        body = request.get_json(force=True)
        monitor_id = store.create_monitor(
            body["name"], body["query"], body.get("aliases", []),
            body.get("categories", []), body.get("package_keys"),
            body.get("schedule_type", "manual"), body.get("schedule_time"),
            body.get("weekday"), body.get("timezone", "Asia/Shanghai"),
        )
        return jsonify({"id": monitor_id}), 201

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
