from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


PACKAGE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SUPPORTED_TYPES = {"string", "text", "integer", "decimal", "boolean", "date", "datetime", "array", "object"}
RESERVED_FIELDS = {
    "sys_id", "sys_resource_uid", "sys_identity_hash", "sys_content_hash",
    "sys_first_package_run_id", "sys_last_package_run_id",
    "sys_first_seen_at", "sys_last_seen_at",
}


class ProtocolError(ValueError):
    pass


def strict_json_loads(raw: str, context: str = "JSON") -> Any:
    def object_without_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError(f"{context} contains duplicate key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=object_without_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ProtocolError(f"{context} contains invalid number: {value}")
            ),
        )
    except ProtocolError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProtocolError(f"invalid {context}: {exc}") from exc


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    nullable: bool
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class PackageManifest:
    raw: dict[str, Any]
    package_key: str
    package_version: str
    protocol_version: str
    name: str
    description: str
    category: str
    python_version: str
    entrypoint: str
    dependencies: str
    incremental: bool
    parameters_schema: dict[str, Any]
    secret_names: tuple[str, ...]
    output_schema_version: int
    fields: tuple[FieldSpec, ...]
    identity_fields: tuple[str, ...]
    indexes: tuple[tuple[str, ...], ...]
    mapping: dict[str, str]

    @property
    def field_map(self) -> dict[str, FieldSpec]:
        return {field.name: field for field in self.fields}


def load_manifest(package_dir: Path) -> PackageManifest:
    path = package_dir / "manifest.json"
    try:
        raw = strict_json_loads(path.read_text(encoding="utf-8-sig"), "manifest.json")
    except FileNotFoundError as exc:
        raise ProtocolError("manifest.json is required") from exc
    if not isinstance(raw, dict):
        raise ProtocolError("manifest must be an object")
    required = {
        "protocol_version", "package_key", "package_version", "name", "category",
        "runtime", "capabilities", "parameters_schema", "output_schema_version", "output_schema",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ProtocolError(f"manifest missing fields: {', '.join(missing)}")
    allowed = required | {"description", "secret_names"}
    unknown = sorted(raw.keys() - allowed)
    if unknown:
        raise ProtocolError(f"manifest has unknown fields: {', '.join(unknown)}")
    key = _require_string(raw, "package_key")
    if not PACKAGE_KEY_RE.fullmatch(key):
        raise ProtocolError("invalid package_key")
    version = _require_string(raw, "package_version")
    if not SEMVER_RE.fullmatch(version):
        raise ProtocolError("package_version must be numeric semver")
    if raw["protocol_version"] != "1.0":
        raise ProtocolError("only protocol_version 1.0 is supported")
    runtime = raw["runtime"]
    if not isinstance(runtime, dict) or runtime.get("type") != "python":
        raise ProtocolError("runtime.type must be python")
    python_version = runtime.get("python_version")
    if not isinstance(python_version, str) or not re.fullmatch(r"3\.(9|10|11|12)", python_version):
        raise ProtocolError("runtime.python_version must be a supported major.minor version")
    entrypoint = _safe_relative(runtime.get("entrypoint"), "runtime.entrypoint")
    dependencies = _safe_relative(runtime.get("dependencies"), "runtime.dependencies")
    for rel in (entrypoint, dependencies, "README.md"):
        if not (package_dir / rel).is_file():
            raise ProtocolError(f"required package file missing: {rel}")
    capabilities = raw["capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) - {"incremental"}:
        raise ProtocolError("capabilities may only declare incremental")
    params = raw["parameters_schema"]
    _validate_parameter_schema(params)
    secret_names = raw.get("secret_names", [])
    if not isinstance(secret_names, list) or any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", value)
        for value in secret_names
    ):
        raise ProtocolError("secret_names must contain uppercase identifiers")
    output = raw["output_schema"]
    if not isinstance(output, dict) or set(output) != {"fields", "identity_fields", "indexes", "mapping"}:
        raise ProtocolError("output_schema must contain fields, identity_fields, indexes and mapping")
    field_rows = output["fields"]
    if not isinstance(field_rows, list) or not 1 <= len(field_rows) <= 64:
        raise ProtocolError("output_schema.fields must contain 1 to 64 fields")
    fields = tuple(_parse_field(row) for row in field_rows)
    names = [field.name for field in fields]
    if len(set(names)) != len(names):
        raise ProtocolError("duplicate output field")
    identities = output["identity_fields"]
    if not isinstance(identities, list) or not identities:
        raise ProtocolError("identity_fields must be a non-empty array")
    by_name = {field.name: field for field in fields}
    for name in identities:
        field = by_name.get(name)
        if field is None or field.nullable or field.type not in {"string", "integer", "decimal", "boolean", "date", "datetime"}:
            raise ProtocolError(f"identity field must be a required scalar: {name}")
    indexes = _parse_indexes(output["indexes"], by_name)
    mapping = output["mapping"]
    if not isinstance(mapping, dict) or set(mapping) - {"title", "url", "summary", "published_at"}:
        raise ProtocolError("invalid output mapping")
    title_field = by_name.get(mapping.get("title", ""))
    if not title_field or title_field.type not in {"string", "text"}:
        raise ProtocolError("mapping.title must reference a string or text field")
    for target, allowed_types in {
        "url": {"string", "text"}, "summary": {"string", "text"}, "published_at": {"datetime", "date"}
    }.items():
        if target in mapping:
            field = by_name.get(mapping[target])
            if not field or field.type not in allowed_types:
                raise ProtocolError(f"mapping.{target} references an incompatible field")
    schema_version = raw["output_schema_version"]
    if not isinstance(schema_version, int) or schema_version < 1:
        raise ProtocolError("output_schema_version must be positive")
    return PackageManifest(
        raw=raw, package_key=key, package_version=version,
        protocol_version="1.0", name=_require_string(raw, "name"),
        description=str(raw.get("description", "")), category=_require_string(raw, "category"),
        python_version=python_version,
        entrypoint=entrypoint, dependencies=dependencies,
        incremental=bool(capabilities.get("incremental", False)),
        parameters_schema=params, secret_names=tuple(secret_names),
        output_schema_version=schema_version, fields=fields,
        identity_fields=tuple(identities), indexes=indexes, mapping=dict(mapping),
    )


def validate_upgrade(previous: PackageManifest, candidate: PackageManifest) -> None:
    if previous.package_key != candidate.package_key:
        raise ProtocolError("package_key cannot change during upgrade")
    if previous.identity_fields != candidate.identity_fields:
        raise ProtocolError("automatic upgrade may not change identity_fields")
    previous_fields = previous.field_map
    candidate_fields = candidate.field_map
    removed = sorted(previous_fields.keys() - candidate_fields.keys())
    if removed:
        raise ProtocolError(f"automatic upgrade may not remove fields: {', '.join(removed)}")
    for name, old in previous_fields.items():
        new = candidate_fields[name]
        if old != new:
            raise ProtocolError(f"automatic upgrade may not change existing field: {name}")
    for name in candidate_fields.keys() - previous_fields.keys():
        if not candidate_fields[name].nullable:
            raise ProtocolError(f"new upgrade field must be nullable: {name}")


def validate_runtime(manifest: PackageManifest) -> None:
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    if running != manifest.python_version:
        raise ProtocolError(
            f"package requires Python {manifest.python_version}, platform is running {running}"
        )


def validate_parameters(schema: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ProtocolError("parameters must be an object")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        unknown = sorted(values.keys() - properties.keys())
        if unknown:
            raise ProtocolError(f"unknown parameters: {', '.join(unknown)}")
    merged = {
        key: spec["default"] for key, spec in properties.items()
        if isinstance(spec, dict) and "default" in spec
    }
    merged.update(values)
    _validate_json_instance(merged, schema, "parameters")
    return merged


def validate_item(manifest: PackageManifest, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("item must be an object")
    unknown = sorted(value.keys() - manifest.field_map.keys())
    if unknown:
        raise ProtocolError(f"unknown item fields: {', '.join(unknown)}")
    result: dict[str, Any] = {}
    for field in manifest.fields:
        if field.name not in value:
            if not field.nullable:
                raise ProtocolError(f"missing required field: {field.name}")
            continue
        current = value[field.name]
        if current is None:
            if not field.nullable:
                raise ProtocolError(f"field may not be null: {field.name}")
            result[field.name] = None
            continue
        result[field.name] = _normalize_field(field, current)
    title = result.get(manifest.mapping["title"])
    if not isinstance(title, str) or not title.strip():
        raise ProtocolError("mapped title must be non-empty")
    return result


def identity_digest(manifest: PackageManifest, item: dict[str, Any]) -> bytes:
    values = [_json_safe(item[name]) for name in manifest.identity_fields]
    encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).digest()


def content_digest(item: dict[str, Any]) -> bytes:
    encoded = json.dumps(_json_safe(item), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).digest()


def package_digest(package_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(package_dir).as_posix()
        if relative.startswith(".venv/") or "__pycache__" in relative:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def schema_digest(manifest: PackageManifest) -> str:
    output = manifest.raw["output_schema"]
    encoded = json.dumps(output, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_field(row: Any) -> FieldSpec:
    if not isinstance(row, dict):
        raise ProtocolError("field declaration must be an object")
    allowed = {"name", "type", "nullable", "max_length", "precision", "scale", "schema"}
    if set(row) - allowed:
        raise ProtocolError(f"unknown field properties: {sorted(set(row) - allowed)}")
    name = row.get("name")
    kind = row.get("type")
    nullable = row.get("nullable")
    if not isinstance(name, str) or not FIELD_RE.fullmatch(name) or name.startswith("sys_") or name in RESERVED_FIELDS:
        raise ProtocolError(f"invalid output field name: {name}")
    if kind not in SUPPORTED_TYPES or not isinstance(nullable, bool):
        raise ProtocolError(f"invalid type or nullable flag for {name}")
    max_length = row.get("max_length")
    if kind == "string" and (not isinstance(max_length, int) or not 1 <= max_length <= 1000):
        raise ProtocolError(f"string field {name} requires max_length 1..1000")
    precision, scale = row.get("precision"), row.get("scale")
    if kind == "decimal" and (
        not isinstance(precision, int) or not isinstance(scale, int)
        or not 1 <= precision <= 38 or not 0 <= scale <= precision
    ):
        raise ProtocolError(f"decimal field {name} requires valid precision and scale")
    schema = row.get("schema")
    if kind in {"array", "object"} and not isinstance(schema, dict):
        raise ProtocolError(f"{kind} field {name} requires schema")
    if kind in {"array", "object"}:
        if schema.get("type") != kind:
            raise ProtocolError(f"{kind} field {name} requires a matching root schema type")
        _validate_json_schema(schema, f"field {name} schema")
    return FieldSpec(name, kind, nullable, max_length, precision, scale, schema)


def _parse_indexes(value: Any, fields: dict[str, FieldSpec]) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or len(value) > 8:
        raise ProtocolError("indexes must be an array with at most 8 entries")
    result = []
    for index in value:
        if not isinstance(index, list) or not 1 <= len(index) <= 3:
            raise ProtocolError("each index must contain 1 to 3 fields")
        for name in index:
            if name not in fields or fields[name].type not in {"string", "integer", "decimal", "boolean", "date", "datetime"}:
                raise ProtocolError(f"field cannot be indexed: {name}")
        result.append(tuple(index))
    return tuple(result)


def _validate_parameter_schema(schema: Any) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ProtocolError("parameters_schema must describe an object")
    if schema.get("additionalProperties") is not False:
        raise ProtocolError("parameters_schema.additionalProperties must be false")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ProtocolError("parameters_schema.properties must be an object")
    if _contains_remote_ref(schema):
        raise ProtocolError("remote $ref is not allowed")
    _validate_json_schema(schema, "parameters_schema")


def _contains_remote_ref(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "$ref" and isinstance(child, str) and not child.startswith("#"))
            or _contains_remote_ref(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_remote_ref(child) for child in value)
    return False


def _validate_json_schema(schema: dict[str, Any], context: str) -> None:
    if _contains_remote_ref(schema):
        raise ProtocolError(f"{context} contains a remote $ref")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ProtocolError(f"invalid {context}: {exc.message}") from exc


def _validate_json_instance(value: Any, schema: dict[str, Any], context: str) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(value)), None)
    if error is None:
        return
    location = "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}"
        for part in error.absolute_path
    )
    raise ProtocolError(f"{context}{location}: {error.message}")


def _normalize_field(field: FieldSpec, value: Any) -> Any:
    if field.type in {"string", "text"}:
        if not isinstance(value, str):
            raise ProtocolError(f"{field.name} must be a string")
        if field.max_length and len(value) > field.max_length:
            raise ProtocolError(f"{field.name} exceeds max_length")
        return value
    if field.type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value < 2**63:
            raise ProtocolError(f"{field.name} must be a signed 64-bit integer")
        return value
    if field.type == "decimal":
        if not isinstance(value, str):
            raise ProtocolError(f"{field.name} decimal must be encoded as a string")
        try:
            decimal = Decimal(value)
        except InvalidOperation as exc:
            raise ProtocolError(f"{field.name} is not a decimal") from exc
        if not decimal.is_finite():
            raise ProtocolError(f"{field.name} must be finite")
        return decimal
    if field.type == "boolean":
        if not isinstance(value, bool):
            raise ProtocolError(f"{field.name} must be boolean")
        return value
    if field.type == "date":
        if not isinstance(value, str):
            raise ProtocolError(f"{field.name} must be YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ProtocolError(f"{field.name} must be a valid date") from exc
    if field.type == "datetime":
        if not isinstance(value, str):
            raise ProtocolError(f"{field.name} must be RFC 3339 datetime")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProtocolError(f"{field.name} must be RFC 3339 datetime") from exc
        if parsed.tzinfo is None:
            raise ProtocolError(f"{field.name} must include timezone")
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    if field.type == "array":
        if not isinstance(value, list):
            raise ProtocolError(f"{field.name} must be an array")
        _validate_json_instance(value, field.schema or {}, field.name)
        return value
    if field.type == "object":
        if not isinstance(value, dict):
            raise ProtocolError(f"{field.name} must be an object")
        _validate_json_instance(value, field.schema or {}, field.name)
        return value
    raise ProtocolError(f"unsupported field type: {field.type}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value


def _safe_relative(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ProtocolError(f"{name} must be a safe relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ProtocolError(f"{name} must be a safe relative path")
    return path.as_posix()


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{key} must be a non-empty string")
    return value.strip()
