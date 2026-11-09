"""Copy immutable artifacts into category directories and atomically repoint metadata."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from crawler_platform.categories import CATEGORIES, normalize_category
from crawler_platform.protocol import ProtocolError, load_manifest, package_digest
from crawler_platform.storage import json_dump, json_load


def copy_categorized_artifact(packages_root: Path, source: Path) -> Path:
    root, source = packages_root.resolve(), source.resolve()
    if not source.is_relative_to(root):
        raise ProtocolError("artifact path is outside packages directory")
    manifest = load_manifest(source)
    digest = package_digest(source)
    # Preserve the registered digest directory: moving does not change package bytes.
    target = root / manifest.category / manifest.package_key / manifest.package_version / source.name
    if not target.resolve().is_relative_to(root):
        raise ProtocolError("categorized artifact path is outside packages directory")
    if source == target:
        return target
    if target.exists():
        if package_digest(target) != digest:
            raise ProtocolError("categorized artifact already exists with different contents")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".copying-" + uuid.uuid4().hex)
    shutil.copytree(source, staging)
    if package_digest(staging) != digest:
        raise ProtocolError("artifact copy verification failed; original preserved")
    staging.rename(target)
    return target


def migrate_package_layout(settings, store) -> dict:
    """Old files remain valid for processes that captured their paths before migration."""
    for category in CATEGORIES:
        (settings.packages_dir / category).mkdir(parents=True, exist_ok=True)
    connection = store.connect()
    changes = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id,category,active_artifact_path FROM crawler_packages ORDER BY id FOR UPDATE")
            packages = cursor.fetchall()
            cursor.execute("SELECT id,artifact_path FROM package_runs ORDER BY id FOR UPDATE")
            runs = cursor.fetchall()
            cursor.execute("SELECT id,selected_categories_json FROM monitors ORDER BY id FOR UPDATE")
            monitors = cursor.fetchall()
            paths = {row["active_artifact_path"] for row in packages if row["active_artifact_path"]}
            paths.update(row["artifact_path"] for row in runs)
            # Include inactive installed versions, so the directory tree is consistently organized.
            paths.update(str(path.parent) for path in settings.packages_dir.glob("*/*/*/manifest.json"))
            mapping = {path: str(copy_categorized_artifact(settings.packages_dir, Path(path)))
                       for path in sorted(paths)}
            for row in packages:
                old_path = row["active_artifact_path"]
                category = (load_manifest(Path(mapping[old_path])).category if old_path else
                            normalize_category(row["category"]))
                new_path = mapping.get(old_path, old_path)
                if category != row["category"] or new_path != old_path:
                    cursor.execute("UPDATE crawler_packages SET category=%s,active_artifact_path=%s WHERE id=%s",
                                   (category, new_path, row["id"]))
                    changes.append(row["id"])
            for row in runs:
                new_path = mapping[row["artifact_path"]]
                if new_path != row["artifact_path"]:
                    cursor.execute("UPDATE package_runs SET artifact_path=%s WHERE id=%s", (new_path, row["id"]))
            for row in monitors:
                old = json_load(row["selected_categories_json"], [])
                categories = list(dict.fromkeys(normalize_category(value) for value in old))
                if categories != old:
                    cursor.execute("UPDATE monitors SET selected_categories_json=%s WHERE id=%s",
                                   (json_dump(categories), row["id"]))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"updated_package_ids": changes, "artifact_paths": len(mapping), "legacy_copies_preserved": True}
