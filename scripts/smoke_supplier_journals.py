"""Low-volume live check for the three supplier packages."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crawler_platform.protocol import load_manifest, validate_item


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", choices=["qinyun_journals", "rhzh_journals", "sancai_journals"])
    parser.add_argument("--query", default="人工智能")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--journal-key")
    args = parser.parse_args()
    package = ROOT / "crawler_packages" / "academic" / args.package
    module_spec = importlib.util.spec_from_file_location(f"{args.package}_smoke", package / "crawler.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    manifest = load_manifest(package)
    rows = json.loads((package / "journals.json").read_text(encoding="utf-8"))
    defaults = manifest.parameters_schema["properties"]["journal_keys"]["default"]
    if args.journal_key:
        defaults = [args.journal_key]
    request = {"query": args.query, "limit": args.limit, "parameters": {"journal_keys": defaults, "timeout_seconds": 20}}
    items, warnings, successful = module.collect(request, {row["journal_key"]: row for row in rows})
    for item in items:
        validate_item(manifest, item)
    print(json.dumps({
        "package": args.package, "query": args.query, "journal_keys": defaults,
        "successful_journals": successful, "item_count": len(items), "warnings": warnings,
        "first_item": items[0] if items else None,
    }, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
