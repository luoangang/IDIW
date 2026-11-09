import json
from pathlib import Path
from unittest.mock import patch

from crawler_platform.api import create_app
from crawler_platform.config import SETTINGS
from crawler_platform.journal_catalog import load_journal_catalog, subject_tags
from crawler_platform.protocol import load_manifest
from crawler_platform.storage import PlatformStore


def test_subject_tags_are_conservative_and_allow_declared_tags():
    assert subject_tags("中国农业大学学报（社会科学版）") == ["农业生态", "人文社科"]
    assert subject_tags("某某大学学报") == ["综合/待细分"]
    assert subject_tags("医学研究", ["临床医学", "临床医学"]) == ["临床医学"]


def test_journal_catalog_reads_package_directory(tmp_path: Path):
    (tmp_path / "journals.json").write_text(json.dumps([
        {"journal_key": "a", "name": "计算机学报"},
        {"journal_key": "b", "name": "临床医学", "tags": ["医学", "临床"]},
        {"journal_key": "a", "name": "duplicate"},
    ], ensure_ascii=False), encoding="utf-8")
    schema = {"properties": {"journal_keys": {"items": {"type": "string"}}}}
    assert load_journal_catalog(tmp_path, schema) == [
        {"journal_key": "a", "name": "计算机学报", "tags": ["信息智能"]},
        {"journal_key": "b", "name": "临床医学", "tags": ["医学", "临床"]},
    ]


def test_journal_catalog_falls_back_to_manifest_enum(tmp_path: Path):
    schema = {"properties": {"journal_keys": {"items": {"enum": ["nature", "science"]}}}}
    assert [row["journal_key"] for row in load_journal_catalog(tmp_path, schema)] == ["nature", "science"]


def test_journal_catalog_endpoint_uses_installed_artifact(tmp_path: Path):
    (tmp_path / "journals.json").write_text('[{"journal_key":"a","name":"计算机学报"}]', encoding="utf-8")
    store = PlatformStore(SETTINGS)
    app = create_app(SETTINGS, store)
    with patch.object(store, "package", return_value={
        "active_artifact_path": str(tmp_path),
        "manifest": {"parameters_schema": {"properties": {"journal_keys": {"items": {"type": "string"}}}}},
    }):
        response = app.test_client().get("/api/v1/packages/example/journals")
    assert response.status_code == 200
    assert response.get_json()[0]["tags"] == ["信息智能"]


def test_all_delivered_chinese_journal_catalogs_can_be_listed():
    root = Path(__file__).resolve().parents[1] / "crawler_packages" / "academic"
    for key in ("cnki_cbpt", "magetech_journals", "qinyun_journals", "rhzh_journals", "sancai_journals"):
        artifact = root / key
        manifest = load_manifest(artifact)
        catalog = load_journal_catalog(artifact, manifest.parameters_schema)
        assert catalog, key
        assert len({row["journal_key"] for row in catalog}) == len(catalog), key
        assert all(row["tags"] for row in catalog), key
        defaults = manifest.parameters_schema["properties"]["journal_keys"]["default"]
        assert set(defaults) <= {row["journal_key"] for row in catalog}, key
