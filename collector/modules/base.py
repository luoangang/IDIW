"""Business-module metadata contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CollectionMode = Literal["search", "sync"]


@dataclass
class CollectorModule:
    name: str
    label: str
    description: str = ""
    resource_type: str = "document"
    supported_modes: tuple[CollectionMode, ...] = ("search",)
    query_label: str = "主题或关键词"
    sort_order: int = 100
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.supported_modes:
            raise ValueError("module must support at least one collection mode")
        unknown = set(self.supported_modes) - {"search", "sync"}
        if unknown:
            raise ValueError(f"unsupported collection modes: {sorted(unknown)}")

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "resource_type": self.resource_type,
            "supported_modes": list(self.supported_modes),
            "query_label": self.query_label,
            "sort_order": self.sort_order,
            "enabled": self.enabled,
        }
