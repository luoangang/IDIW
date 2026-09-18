"""Automatic source discovery with validation and isolated import failures."""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from dataclasses import dataclass

from collector.sources.base import SourcePlugin
from collector.modules.discovery import discover_modules


_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class DiscoveryResult:
    plugins: dict[str, SourcePlugin]
    errors: dict[str, str]


def discover_plugins() -> DiscoveryResult:
    registered_modules = discover_modules().modules
    plugins: dict[str, SourcePlugin] = {}
    errors: dict[str, str] = {}

    for collector_module_name in registered_modules:
        package_name = f"collector.sources.{collector_module_name}"
        try:
            package = importlib.import_module(package_name)
        except Exception as exc:
            errors[collector_module_name] = f"source package unavailable: {exc}"
            continue

        for module_info in pkgutil.iter_modules(package.__path__):
            if module_info.name.startswith("_"):
                continue
            plugin_module_name = f"{package.__name__}.{module_info.name}"
            error_key = f"{collector_module_name}.{module_info.name}"
            try:
                plugin_module = importlib.import_module(plugin_module_name)
                classes = [
                    obj for _, obj in inspect.getmembers(plugin_module, inspect.isclass)
                    if issubclass(obj, SourcePlugin)
                    and obj is not SourcePlugin
                    and obj.__module__ == plugin_module_name
                ]
                if len(classes) != 1:
                    raise ValueError("a source module must expose exactly one SourcePlugin subclass")
                plugin = classes[0]()
                if plugin.module != collector_module_name:
                    raise ValueError(
                        f"source is stored under {collector_module_name} but declares {plugin.module}"
                    )
                if not _SAFE_NAME.fullmatch(plugin.name):
                    raise ValueError("plugin name must be a safe lowercase identifier")
                registered_module = registered_modules[collector_module_name]
                unknown_modes = set(plugin.supported_modes) - set(registered_module.supported_modes)
                if unknown_modes:
                    raise ValueError(
                        f"source modes are not supported by module: {sorted(unknown_modes)}"
                    )
                if plugin.contract_version < 1:
                    raise ValueError("source contract_version must be positive")
                if plugin.name in plugins:
                    raise ValueError(f"duplicate plugin name: {plugin.name}")
                plugins[plugin.name] = plugin
            except Exception as exc:
                errors[error_key] = str(exc)

    return DiscoveryResult(dict(sorted(plugins.items())), errors)
