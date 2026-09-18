"""Pluggable intelligence collector and Windows runtime bootstrap."""
from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES = []


def _prepare_windows_runtime() -> None:
    """Make base-Python native DLLs visible inside an Anaconda virtualenv."""
    if os.name != "nt":
        return

    candidates = [
        Path(sys.base_prefix) / "Library" / "bin",
        Path(sys.base_prefix) / "DLLs",
    ]
    existing = [str(path) for path in candidates if path.is_dir()]
    if not existing:
        return

    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    missing = [path for path in existing if path.lower() not in {part.lower() for part in path_parts}]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing + path_parts)

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory:
        for path in existing:
            _DLL_DIRECTORY_HANDLES.append(add_dll_directory(path))


_prepare_windows_runtime()

__version__ = "2.0.0"
