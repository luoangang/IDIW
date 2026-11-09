"""Validate probe output with the platform contract without opening a database."""
import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.executor import PackageExecutor
from crawler_platform.protocol import identity_digest, load_manifest, validate_parameters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "crawler_platform_runtime" / "probes" / "rss-feedparser" / "results")
    args = parser.parse_args()
    manifest = load_manifest(ROOT / "crawler_packages" / "news" / "rss_multi_feed")
    for slug in ("all", "embodied", "military"):
        directory = args.output / slug
        request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        validate_parameters(manifest.parameters_schema, request["parameters"])
        result = PackageExecutor._read_result(directory / "output", request, 0, manifest.incremental)
        items, rejected = PackageExecutor._read_items(directory / "output", manifest, request["limit"])
        assert not rejected, rejected
        assert result["item_count"] == len(items)
        assert len({identity_digest(manifest, item) for item in items}) == len(items)
        print(f"{slug}: {len(items)} items validated; 0 rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
