"""Replay real USPTO query output through platform validation and ingestion twice."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crawler_platform.config import SETTINGS
from crawler_platform.storage import PlatformStore
from crawler_platform.protocol import load_manifest
from crawler_platform.executor import PackageExecutor


def main():
    sample = ROOT / 'crawler_platform_runtime/verification/uspto-six-20261013-final'
    result = json.loads((sample / 'result.json').read_text(encoding='utf-8'))
    if result['status'] != 'completed' or result['item_count'] != 6:
        raise RuntimeError('Require six completed live USPTO results before ingestion')
    store = PlatformStore(SETTINGS)
    connection = store.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM package_runs WHERE status IN ('queued','running')")
            if cursor.fetchone()['n']:
                raise RuntimeError('Existing platform work is active; do not claim unrelated jobs')
    finally:
        connection.close()
    request = json.loads((ROOT / 'crawler_packages/patents/uspto_number_lookup/tests/request.json').read_text(encoding='utf-8'))
    monitor_id = store.create_monitor('USPTO 六号码验收 2026-10-13', request['query'], [], [], ['uspto_number_lookup'])
    stats = []
    for index in range(2):
        run_id = store.enqueue_monitor(monitor_id)
        claimed = store.claim_package_run('uspto-verified-output-replay', lease_seconds=300)
        if claimed is None or claimed['run_id'] != run_id:
            raise RuntimeError('Unexpected concurrent queue claim')
        manifest = load_manifest(Path(claimed['artifact_path']))
        output = SETTINGS.runs_dir / claimed['execution_id'] / 'verified_output_replay'
        output.mkdir(parents=True, exist_ok=True)
        (output / 'items.jsonl').write_bytes((sample / 'items.jsonl').read_bytes())
        replay_result = {**result, 'execution_id': claimed['execution_id']}
        (output / 'result.json').write_text(json.dumps(replay_result, ensure_ascii=False), encoding='utf-8')
        log = output / 'replay.log'
        log.write_text('Replayed verified live USPTO output; no second network query.\n', encoding='utf-8')
        parsed = PackageExecutor._read_result(output, claimed['request'], 0, True)
        valid, rejected = PackageExecutor._read_items(output, manifest, claimed['request']['limit'])
        if rejected or len(valid) != 6:
            raise RuntimeError('USPTO output failed platform validation')
        counts = store.ingest(claimed, manifest, valid, 0, parsed, 0, output, log)
        stats.append({'run_id': run_id, **counts})
    report = {'monitor_id': monitor_id, 'mode': 'verified_live_output_replay', 'runs': stats}
    (sample / 'platform_ingestion.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
