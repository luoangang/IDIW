"""Automatic discovery for business modules."""
from __future__ import annotations

import importlib
import pkgutil
import re
from dataclasses import dataclass

from collector.modules.base import CollectorModule


_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class ModuleDiscoveryResult:
    modules: dict[str, CollectorModule]
    errors: dict[str, str]


def discover_modules() -> ModuleDiscoveryResult:
    package = importlib.import_module("collector.modules")
    modules: dict[str, CollectorModule] = {}
    errors: dict[str, str] = {}

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in {"base", "discovery"} or module_info.name.startswith("_"):
            continue
        module_name = f"{package.__name__}.{module_info.name}"
        try:
            python_module = importlib.import_module(module_name)
            collector_module = getattr(python_module, "MODULE", None)
            if not isinstance(collector_module, CollectorModule):
                raise ValueError("module must expose a CollectorModule instance named MODULE")
            if not _SAFE_NAME.fullmatch(collector_module.name):
                raise ValueError("module name must be a safe lowercase identifier")
            if collector_module.name in modules:
                raise ValueError(f"duplicate module name: {collector_module.name}")
            modules[collector_module.name] = collector_module
        except Exception as exc:
            errors[module_info.name] = str(exc)

    ordered = sorted(modules.items(), key=lambda row: (row[1].sort_order, row[0]))
    return ModuleDiscoveryResult(dict(ordered), errors)
