"""Stable data-type categories, independent of package identity and subject tags."""
from pathlib import Path

CATEGORIES = {
    "news": "新闻资讯",
    "academic": "学术文献",
    "patents": "专利",
    "reference": "知识资料",
    "entities": "主体信息",
    "community": "社区内容",
}
LEGACY_CATEGORIES = {"encyclopedia": "reference", "books": "reference", "paper": "academic"}


def normalize_category(value: str) -> str:
    category = LEGACY_CATEGORIES.get(value, value) if isinstance(value, str) else None
    if category not in CATEGORIES:
        raise ValueError("category must be one of: " + ", ".join(CATEGORIES))
    return category


def discover_packages(root: Path) -> list[Path]:
    """Discover standalone, legacy flat, or categorized source packages, not artifacts."""
    if (root / "manifest.json").is_file():
        return [root]
    paths = {path.parent for path in root.glob("*/manifest.json")}
    paths.update(path.parent for category in CATEGORIES for path in (root / category).glob("*/manifest.json"))
    return sorted(paths)
