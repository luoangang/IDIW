from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default=r"C:\Users\86139\Desktop\期刊.zip")
    parser.add_argument("--target", default=str(Path(__file__).resolve().parents[1] / "journal_catalog" / "source" / "periodicals_2026-11-25"))
    args = parser.parse_args()
    source = Path(args.zip)
    target = Path(args.target)
    if not source.is_file():
        raise SystemExit(f"source zip not found: {source}")
    if target.exists():
        raise SystemExit(f"target already exists: {target}")
    with zipfile.ZipFile(source) as zipped:
        infos = zipped.infolist()
        total = sum(info.file_size for info in infos)
        if total > 1_500_000_000:
            raise SystemExit(f"archive too large after extraction: {total}")
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part not in ("", ".")]
            if name.startswith("/") or ".." in parts:
                raise SystemExit(f"unsafe archive path: {info.filename}")
            mode = stat.S_IFMT(info.external_attr >> 16)
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise SystemExit(f"archive contains link or special file: {info.filename}")
        target.mkdir(parents=True, exist_ok=False)
        zipped.extractall(target)
    counts = Counter()
    files = 0
    for path in target.rglob("*"):
        if path.is_file():
            files += 1
            rel = path.relative_to(target).parts
            counts[rel[0] if rel else "(root)"] += 1
    manifest = {
        "source_zip": str(source),
        "source_sha256": sha256(source),
        "source_size": source.stat().st_size,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "target": str(target),
        "entries": len(infos),
        "files": files,
        "uncompressed_bytes": total,
        "top_level_files": dict(counts),
    }
    (target / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
