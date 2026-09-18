"""Flask control panel and JSON API."""
from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from collector.config import PANEL_TOKEN, SERVER_HOST, SERVER_PORT
from collector.engine import collect_query
from collector.modules.discovery import discover_modules
from collector.sources.discovery import discover_plugins
from collector.storage import MySQLStore


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def create_app(initialize_database: bool = True) -> Flask:
    app = Flask(__name__)
    module_discovery = discover_modules()
    modules = module_discovery.modules
    discovery = discover_plugins()
    plugins = discovery.plugins
    store = MySQLStore()
    jobs: dict[str, dict[str, Any]] = {}
    jobs_lock = threading.Lock()

    if initialize_database:
        store.initialize()
        store.sync_catalog(modules, plugins)

    @app.before_request
    def authorize():
        if not PANEL_TOKEN or request.path == "/":
            return None
        token = request.headers.get("X-Panel-Token") or request.args.get("token", "")
        if token != PANEL_TOKEN:
            return jsonify({"error": "unauthorized"}), 401
        return None

    @app.errorhandler(Exception)
    def handle_error(exc: Exception):
        if isinstance(exc, HTTPException):
            return jsonify({"error": exc.description}), exc.code
        app.logger.exception("request failed")
        return jsonify({"error": str(exc)}), 500

    @app.get("/")
    def dashboard():
        return send_file(Path(__file__).with_name("dashboard.html"))

    @app.get("/api/health")
    def health():
        return jsonify({
            "ok": True,
            "schema_version": store.schema_version() if initialize_database else None,
            "module_count": len(modules),
            "plugin_count": len(plugins),
            "module_errors": module_discovery.errors,
            "plugin_errors": discovery.errors,
        })

    @app.get("/api/modules")
    def list_modules():
        rows = []
        registered = {row["name"]: row for row in store.list_modules()}
        for collector_module in modules.values():
            row = collector_module.metadata()
            row.update(registered.get(collector_module.name, {}))
            row["source_count"] = sum(
                1 for plugin in plugins.values()
                if plugin.module == collector_module.name
            )
            rows.append(row)
        return jsonify({"modules": rows, "module_errors": module_discovery.errors})

    @app.get("/api/sources")
    def list_sources():
        module_name = request.args.get("module", "").strip()
        settings = store.list_settings()
        rows = []
        for plugin in plugins.values():
            if module_name and plugin.module != module_name:
                continue
            row = plugin.metadata()
            row.update(settings.get(plugin.name, {}))
            rows.append(row)
        return jsonify({"sources": rows, "plugin_errors": discovery.errors})

    @app.get("/api/modules/<module_name>/sources")
    def list_module_sources(module_name: str):
        if module_name not in modules:
            return jsonify({"error": "unknown module"}), 404
        settings = store.list_settings()
        rows = []
        for plugin in plugins.values():
            if plugin.module == module_name:
                row = plugin.metadata()
                row.update(settings.get(plugin.name, {}))
                rows.append(row)
        return jsonify({"module": module_name, "sources": rows})

    @app.put("/api/sources/<source_name>")
    def update_source(source_name: str):
        plugin = plugins.get(source_name)
        if not plugin:
            return jsonify({"error": "unknown source"}), 404
        data = request.get_json(silent=True) or {}
        item_limit = max(1, min(int(data.get("item_limit", plugin.default_limit)), 500))
        config = data.get("config", {})
        if not isinstance(config, dict):
            return jsonify({"error": "config must be an object"}), 400
        validated = {}
        for key, spec in plugin.configurable.items():
            value = config.get(key, spec.get("default"))
            if spec.get("type") == "select" and value not in spec.get("options", []):
                return jsonify({"error": f"invalid value for {key}"}), 400
            validated[key] = bool(value) if spec.get("type") == "boolean" else value
        store.update_setting(source_name, bool(data.get("enabled", True)), item_limit, validated)
        return jsonify({"ok": True})

    @app.post("/api/collect")
    def start_collection():
        data = request.get_json(silent=True) or {}
        query = str(data.get("query", "")).strip()
        module_name = str(data.get("module", "news")).strip()
        mode = str(data.get("mode", "search")).strip()
        options = data.get("options", {})
        if mode == "search" and not query:
            return jsonify({"error": "query is required"}), 400
        if len(query) > 255:
            return jsonify({"error": "query is too long"}), 400
        if module_name not in modules or not modules[module_name].enabled:
            return jsonify({"error": "unknown or disabled module"}), 400
        if mode not in modules[module_name].supported_modes:
            return jsonify({"error": "collection mode is not supported by this module"}), 400
        if not isinstance(options, dict):
            return jsonify({"error": "options must be an object"}), 400
        compatible = [
            plugin for plugin in plugins.values()
            if plugin.module == module_name and mode in plugin.supported_modes
        ]
        if not compatible:
            return jsonify({"error": "this module has no source for the selected mode"}), 409
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id, "module": module_name, "mode": mode, "query": query,
            "status": "queued", "logs": deque(maxlen=1000), "result": None,
        }
        with jobs_lock:
            jobs[job_id] = job

        def run_job() -> None:
            job["status"] = "running"

            def append_log(message: str) -> None:
                job["logs"].append({"time": datetime.now().strftime("%H:%M:%S"), "message": message})

            try:
                job["result"] = collect_query(
                    query, plugins, store, append_log, module_name=module_name,
                    mode=mode, options=options,
                )
                job["status"] = job["result"]["status"]
            except Exception as exc:
                append_log(f"任务失败：{exc}")
                job["status"] = "failed"
                job["result"] = {"error": str(exc)}

        threading.Thread(target=run_job, daemon=True, name=f"collector-{job_id[:8]}").start()
        return jsonify({"job_id": job_id, "status": "queued"}), 202

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str):
        with jobs_lock:
            job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify(_json_safe({**job, "logs": list(job["logs"])}))

    @app.get("/api/runs")
    def list_runs():
        limit = max(1, min(int(request.args.get("limit", 30)), 200))
        module_name = request.args.get("module", "").strip()
        return jsonify({"runs": _json_safe(store.recent_runs(limit, module_name))})

    @app.get("/api/resources")
    def list_resources():
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
        module_name = request.args.get("module", "").strip()
        source_name = request.args.get("source", "").strip()
        query = request.args.get("query", "").strip()
        if module_name and module_name not in modules:
            return jsonify({"error": "unknown module"}), 400
        if source_name and source_name not in plugins:
            return jsonify({"error": "unknown source"}), 400
        rows = store.recent_resources(module_name, source_name, query, limit)
        return jsonify({"resources": _json_safe(rows)})

    @app.get("/api/items")
    def list_items():
        source_name = request.args.get("source", "")
        plugin = plugins.get(source_name)
        if not plugin:
            return jsonify({"error": "source query parameter is required"}), 400
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
        query = request.args.get("query", "").strip()
        rows = store.recent_items(plugin, limit, query)
        return jsonify({"module": plugin.module, "source": source_name, "items": _json_safe(rows)})

    return app


def start_server() -> None:
    app = create_app()
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)
