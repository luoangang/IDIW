from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore

STATE = ROOT / ".local" / "platform-package-sample-test-2026-11-25.json"
NAME = "国内分包抽样-2026-11-25"
QUERY = "最新一期"

# 每包优先选近期 live 复核通过的刊，只验证平台链路，不覆盖站点级失败
SAMPLES = {
    "cnki_cbpt": [
        ("18ff7eeafd81f5dd", "卫生研究"),
        ("3c825e6fbb774765", "征信"),
        ("b3ddfb2a9885ff20", "林产工业"),
        ("ea65f5faeeb80978", "自然辩证法研究"),
    ],
    "custom_toc_journals": [
        ("1d60dcb3973c11ae", "临床与实验病理学杂志"),
        ("43a070455a87e589", "华东理工大学学报（社会科学版）"),
        ("6821b508283964be", "商业经济研究"),
        ("b7e3d503a0194ead", "载人航天"),
        ("8c731fa085826699", "北京大学教育评论"),
    ],
    "magetech_journals": [
        ("a62db5bce84d6648", "中华临床医师杂志电子版"),
        ("76cbd2c2e92766c0", "中华介入放射学电子杂志"),
        ("575e623ba276c71e", "中华关节外科杂志（电子版）"),
        ("3591dbe91e051d14", "农学学报"),
        ("f9a38aa7f90d7a7b", "耐火材料"),
    ],
    "qinyun_journals": [
        ("ed8ab90b0cc756be", "兵工自动化"),
        ("8059cc0c71987788", "医用生物力学"),
        ("20515da4e88d71c5", "军事护理"),
        ("76391421314f5f5c", "农业机械学报"),
        ("e18133e715dd9a00", "南京信息工程大学学报自然科学版"),
    ],
    "rhzh_journals": [
        ("93ca63312c8f76e5", "临床心血管病杂志"),
        ("af49e3bb99250fd7", "临床急诊杂志"),
        ("6ccc47ea838ad245", "临床泌尿外科杂志"),
        ("952e8958b44a5441", "机械工程材料"),
        ("70286bd199a747de", "现代应用物理"),
    ],
    "founder_journals": [
        ("a35dcec1ee3d9611", "四川大学学报. 自然科学版"),
        ("fe47986a55a5437a", "新疆石油地质"),
        ("ebc4f4ac47c9f6d5", "测试技术学报"),
        ("bd94f1daf342f852", "电焊机"),
        ("e35ea24cb6e08c8d", "饲料研究"),
    ],
    "paperonce_journals": [
        ("0f9b35919718185a", "断块油气田"),
        ("897131ec50bcdcfc", "现代检验医学杂志"),
        ("e33331401daffeed", "邮电设计技术"),
    ],
    "oa_rss_journals": [
        ("817e0fdddbace580", "集美大学学报（自然科学版）"),
        ("36d74fb9189ffe5b", "内蒙古社会科学"),
        ("7934fe4fdd274b89", "体育科学研究"),
    ],
    "vsb_journals": [
        ("e245799434449a85", "井冈山大学学报（社会科学版）"),
        ("dc5782791704b55f", "社会科学家"),
        ("3d1be8e2beaa84f3", "职业技术教育"),
    ],
    "hep_mirror_journals": [
        ("06bac1afda20be41", "中国普通外科杂志"),
        ("81165204138844f6", "中国石油大学学报. 自然科学版"),
        ("6df402f7eb36627d", "重庆医科大学学报"),
    ],
    "sancai_journals": [
        ("1d43330d46323f18", "安徽师范大学学报（社会科学版）"),
        ("7371a30d9aa7945b", "合肥师范学院学报"),
    ],
    "sciengine_journals": [
        ("a2a415ad37482923", "中国科学数据中英文网络版"),
        ("8b235c89e71721e7", "分子科学学报"),
        ("85b4c55efb8b5ad7", "原子核物理评论"),
        ("93228fce19fb1a2e", "古生物学报"),
        ("b091eaadec1bbf73", "环境工程学报"),
    ],
}


def main() -> None:
    store = PlatformStore(SETTINGS)
    existing = {row["name"] for row in store.list_monitors("all")}
    if NAME in existing:
        raise SystemExit(f"monitor already exists: {NAME}")
    package_settings = []
    for package_key, samples in SAMPLES.items():
        package_dir = ROOT / "crawler_packages" / "academic" / package_key
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        properties = manifest["parameters_schema"]["properties"]
        keys = [journal_key for journal_key, _ in samples]
        config = {"journal_keys": keys, "collect_mode": "latest_issue"}
        if "per_journal_limit" in properties:
            config["per_journal_limit"] = 2
        if "timeout_seconds" in properties:
            config["timeout_seconds"] = 15
        if "enrich_abstract" in properties:
            config["enrich_abstract"] = False
        if "abstract_enrich_limit" in properties:
            config["abstract_enrich_limit"] = 0
        if "request_delay_ms" in properties:
            config["request_delay_ms"] = 0
        if "follow_latest" in properties:
            config["follow_latest"] = True
        package_settings.append({
            "package_key": package_key,
            "enabled": True,
            "item_limit": max(1, len(keys) * 2),
            "config": config,
        })
        print(f"{package_key:24s} {len(keys)} 本  item_limit={len(keys) * 2}")
    monitor_id = store.create_monitor(
        name=NAME,
        query=QUERY,
        aliases=[],
        categories=[],
        package_keys=[row["package_key"] for row in package_settings],
        schedule_type="manual",
        package_settings=package_settings,
    )
    run_id = store.enqueue_monitor(monitor_id)
    state = {
        "monitor_id": monitor_id,
        "run_id": run_id,
        "name": NAME,
        "packages": {key: samples for key, samples in SAMPLES.items()},
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("monitor_id", monitor_id, "run_id", run_id, "state", STATE)


if __name__ == "__main__":
    main()
