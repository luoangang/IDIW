from __future__ import annotations

import json
import re
from pathlib import Path


SUBJECT_RULES = (
    ("医学健康", r"医学|临床|医院|护理|药学|药物|口腔|肿瘤|疾病|卫生|中医|健康|生物医学|基础医学"),
    ("农业生态", r"农业|农学|作物|园艺|林业|森林|畜牧|兽医|水产|渔业|植物保护|生态|环境"),
    ("信息智能", r"计算机|软件|信息|人工智能|智能|通信|电子|网络|自动化|控制|数据科学"),
    ("工程技术", r"机械|材料|制造|建筑|土木|交通|航空|航天|能源|电力|化工|冶金|工程|技术"),
    ("地球科学", r"地质|地理|地球|地震|气象|海洋|测绘|矿业|遥感|水文"),
    ("人文社科", r"经济|金融|管理|法律|法学|政治|社会|教育|文学|历史|哲学|艺术|文化|国际关系"),
    ("基础科学", r"数学|物理|化学|生物|生命科学|天文|力学"),
)


def subject_tags(name: str, declared: object = None) -> list[str]:
    if isinstance(declared, list) and declared and all(isinstance(tag, str) and tag.strip() for tag in declared):
        return list(dict.fromkeys(tag.strip()[:24] for tag in declared[:4]))
    matches = [label for label, pattern in SUBJECT_RULES if re.search(pattern, name)]
    return matches[:2] or ["综合/待细分"]


def load_journal_catalog(artifact: Path, schema: dict) -> list[dict[str, object]]:
    journal_keys = schema.get("properties", {}).get("journal_keys")
    if not isinstance(journal_keys, dict):
        return []
    path = artifact / "journals.json"
    if path.is_file():
        if not path.resolve().is_relative_to(artifact.resolve()):
            raise ValueError("journal catalog must stay inside package")
        if path.stat().st_size > 4_000_000:
            raise ValueError("journal catalog is too large")
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) > 5000:
            raise ValueError("invalid journal catalog")
    else:
        keys = journal_keys.get("items", {}).get("enum", [])
        rows = [{"journal_key": key, "name": str(key)} for key in keys]
    allowed = journal_keys.get("items", {}).get("enum")
    catalog = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key, name = row.get("journal_key"), row.get("name")
        if not isinstance(key, str) or not isinstance(name, str) or not key or not name or key in seen:
            continue
        if allowed is not None and key not in allowed:
            continue
        seen.add(key)
        catalog.append({"journal_key": key, "name": name, "tags": subject_tags(name, row.get("tags"))})
    return catalog
