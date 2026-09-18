"""Stable contracts shared by all source plugins."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

import requests

from collector.config import REQUEST_TIMEOUT, USER_AGENT


@dataclass(frozen=True)
class CollectionRequest:
    """One normalized request passed from the engine to every source."""

    module: str
    query: str
    limit: int
    config: dict[str, Any] = field(default_factory=dict)
    mode: str = "search"
    date_from: date | None = None
    date_to: date | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in {"search", "sync"}:
            raise ValueError(f"unsupported collection mode: {self.mode}")
        if self.mode == "search" and not self.query.strip():
            raise ValueError("search mode requires a query")
        if self.limit < 1:
            raise ValueError("limit must be positive")


@dataclass
class SourceItem:
    title: str
    url: str
    summary: str = ""
    content: str = ""
    author: str = ""
    publisher: str = ""
    published_at: datetime | None = None
    language: str = ""
    source_item_id: str = ""
    resource_type: str = "document"
    authors: list[str] = field(default_factory=list)
    identifiers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        self.url = self.url.strip()
        self.authors = [str(value).strip() for value in self.authors if str(value).strip()]
        if self.author and not self.authors:
            self.authors = [part.strip() for part in self.author.split(",") if part.strip()]
        elif self.authors and not self.author:
            self.author = ", ".join(self.authors)
        if not self.title:
            raise ValueError("source item title is required")
        if not self.url:
            raise ValueError("source item URL is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourcePlugin(ABC):
    module: str
    name: str
    label: str
    table_name: str
    default_limit: int = 10
    description: str = ""
    resource_type: str = "document"
    supported_modes: tuple[str, ...] = ("search",)
    contract_version: int = 1
    configurable: dict[str, dict[str, Any]] = {}

    @property
    def storage_table(self) -> str:
        tables = {
            "news": "news_resources",
            "paper": "paper_resources",
            "patent": "patent_resources",
        }
        try:
            return tables[self.module]
        except KeyError as exc:
            raise ValueError(f"module has no resource table: {self.module}") from exc

    def http(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
        return session

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        response = self.http().get(url, **kwargs)
        response.raise_for_status()
        return response

    @abstractmethod
    def collect(self, request: CollectionRequest) -> list[SourceItem]:
        """Collect at most ``request.limit`` normalized resources."""

    def validate_request(self, request: CollectionRequest) -> None:
        if request.module != self.module:
            raise ValueError(f"source {self.name} does not belong to module {request.module}")
        if request.mode not in self.supported_modes:
            raise ValueError(f"source {self.name} does not support {request.mode} mode")

    def identity_value(self, item: SourceItem) -> str:
        """Return a stable identity independent from the query that found it."""
        if item.source_item_id:
            return f"external:{item.source_item_id.strip()}"
        for key in ("doi", "patent_number", "canonical_id"):
            value = item.identifiers.get(key, "").strip()
            if value:
                return f"{key}:{value.lower()}"
        return f"url:{item.url.strip()}"

    def metadata(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "name": self.name,
            "label": self.label,
            # table_name is retained in the API for the existing dashboard.
            "table_name": self.storage_table,
            "storage_table": self.storage_table,
            "default_limit": self.default_limit,
            "description": self.description,
            "resource_type": self.resource_type,
            "supported_modes": list(self.supported_modes),
            "contract_version": self.contract_version,
            "configurable": self.configurable,
        }
