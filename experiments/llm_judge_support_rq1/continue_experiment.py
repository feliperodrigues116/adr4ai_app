"""Opt-in operational amendment; frozen scientific v1.1 runner remains unchanged."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('support_scientific_v1_1_runner', HERE / 'run_experiment.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
p = legacy.p
OPERATION_ROOT = HERE / 'operational_outputs'
POLICY_PATH = HERE / 'operational_policy.json'
POLICY = p.strict_json(POLICY_PATH.read_text(encoding='utf-8'))


def operation_sources():
    return {str(path.relative_to(p.ROOT)): p.file_hash(path) for path in
            (Path(__file__).resolve(), POLICY_PATH, HERE / 'technical_corrections.py')}


def error_for_response(metadata, item):
    """Replay the unchanged validator on a preserved response; no corrections."""
    try:
        p.require(metadata.get('stop_reason') == 'end_turn',
                  f"Incomplete/refused response: {metadata.get('stop_reason')}")
        p.require(metadata.get('response_model') == p.MODEL, 'Actual model differs from fixed protocol model')
        types = metadata.get('content_block_types', [])
        p.require(all(kind in ('thinking', 'redacted_thinking', 'text') for kind in types),
                  'Unexpected content block type')
        p.require(types.count('text') == 1, 'Expected exactly one structured text block')
        value = p.strict_json(metadata['response_text'])
        p.validate_judgment(value, item['case'])
    except (ValueError, TypeError, KeyError) as error:
        return str(error)
    return None


def inspect(directory, manifest, items):
    legacy.verify_manifest_sources(manifest)
    p.require(manifest['protocol_id'] == POLICY['scientific_protocol_id'], 'Operational amendment is only for scientific v1.1')
    state = legacy.resume_state(directory, manifest, items)
    checked = {}
    for event in p.read_rows(Path(directory) / 'events.jsonl', optional=True):
        if event.get('event') != 'execution_started' or 'operational_policy_id' not in event:
            continue
        operation_id = event.get('operation_id')
        p.require(isinstance(operation_id, str) and str(uuid.UUID(operation_id)) == operation_id,
                  'Invalid operation ID')
        if operation_id in checked:
            p.require(event.get('operational_amendment_sha256') == checked[operation_id],
                      'Inconsistent amendment hash across execution segments')
            continue
        amendment_path = OPERATION_ROOT / operation_id / 'amendment.json'
        p.require(p.file_hash(amendment_path) == event.get('operational_amendment_sha256'),
                  'Operational amendment hash mismatch')
        amendment = p.strict_json(amendment_path.read_text(encoding='utf-8'))
        p.require(amendment['operational_policy'] == POLICY
                  and event['operational_policy_id'] == POLICY['policy_id']
                  and amendment['operation_id'] == operation_id
                  and amendment['scientific_experiment_sha256'] == p.digest(manifest)
                  and amendment['scientific_manifest_sha256'] == p.file_hash(Path(directory) / 'manifest.json')
                  and amendment['frozen_scientific_source_sha256'] == manifest['source_code_sha256']
                  and amendment['operational_source_sha256'] == operation_sources(),
                  'Operational amendment compatibility/provenance mismatch')
        for name, expected in amendment['pre_operation_file_sha256'].items():
            prefix = (Path(directory) / name).read_bytes()[:amendment['pre_operation_file_bytes'][name]]
            p.require(hashlib.sha256(prefix).hexdigest() == expected, 'Historical journal prefix was altered')
        checked[operation_id] = event['operational_amendment_sha256']
    return state


def validation_summary(directory, manifest, items):
    done, counts, pending = inspect(directory, manifest, items)
    directory = Path(directory)
    attempts = p.read_rows(directory / 'attempts.jsonl', optional=True)
    events = p.read_rows(directory / 'events.jsonl', optional=True)
    by_attempt = {a['attempt_id']: a for a in attempts}
    by_pair = {p.key(item): item for item in items}
    failures = {}
    for number, event in enumerate(events, 1):
        attempt = by_attempt.get(event.get('attempt_id'))
        if attempt is None:
            continue
        key = attempt['user_story_id'], attempt['pattern_id']
        metadata = event.get('response_metadata')
        if event.get('error_type') != 'ResponseValidationError' or not isinstance(metadata, dict):
            continue
        exact = error_for_response(metadata, by_pair[key])
        p.require(exact is not None, 'A recorded validation failure passes the frozen validator; investigate before continuing')
        if 'validation_error' in event:
            p.require(event['validation_error'] == exact, 'Recorded validation error does not match frozen validator replay')
        failures[event['attempt_id']] = {
            'attempt_id': attempt['attempt_id'], 'attempt_number': attempt['attempt_number'],
            'error_type': event['error_type'], 'validation_error': exact,
            'error_source': 'recorded_and_replayed' if 'validation_error' in event else 'replayed_from_preserved_raw_response',
            'event_line': number, 'raw_response_file': str(directory / 'events.jsonl'),
            'raw_response_json_pointer': f'/{number - 1}/response_metadata',
            'raw_text_field': 'response_metadata.response_text',
            'response_id': metadata.get('response_id'), 'request_id': metadata.get('request_id'),
            'raw_response_sha256': p.digest(metadata.get('response_text')),
        }
    missing = []
    for item in items:
        key = p.key(item)
        if key in done:
            continue
        pair_attempts = [a for a in attempts if (a['user_story_id'], a['pattern_id']) == key]
        pair_failures = [failures[a['attempt_id']] for a in pair_attempts if a['attempt_id'] in failures]
        missing.append({
            'user_story_id': key[0], 'pattern_id': key[1],
            'gpt_classification': item['gpt_assessment']['classification'],
            'status': 'invalid' if pair_failures else ('pending_unfinished' if counts[key] else 'never_attempted'),
            'attempts': counts[key], 'attempt_limit': manifest['max_attempts_per_pair'],
            'attempt_limit_reached': counts[key] >= manifest['max_attempts_per_pair'],
            'validation_failures': pair_failures,
            'other_unvalidated_attempt_ids': [a['attempt_id'] for a in pair_attempts if a['attempt_id'] not in failures],
        })
    states = Counter(row['status'] for row in missing)
    snapshots = {name: p.file_hash(directory / name) for name in
                 ('manifest.json', 'results.jsonl', 'attempts.jsonl', 'events.jsonl') if (directory / name).exists()}
    return {
        'scientific_protocol_id': manifest['protocol_id'], 'operational_policy_id': POLICY['policy_id'],
        'scientific_manifest_sha256': p.file_hash(directory / 'manifest.json') if (directory / 'manifest.json').exists() else None,
        'scientific_experiment_sha256': p.digest(manifest), 'official_directory': str(directory),
        'source_snapshot_sha256': snapshots, 'total_expected_pairs': len(items),
        'validated_judgments': len(done), 'invalid_or_pending_pairs': len(missing),
        'invalid_pairs': states['invalid'], 'unfinished_pairs': states['pending_unfinished'],
        'never_attempted_pairs': states['never_attempted'], 'total_attempts': len(attempts),
        'complete': len(done) == len(items), 'pending_pairs': missing,
    }


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def csv_summary(summary):
    stream = io.StringIO(newline='')
    fields = ['user_story_id', 'pattern_id', 'gpt_classification', 'status', 'attempts',
              'attempt_limit', 'attempt_limit_reached', 'validation_failures', 'other_unvalidated_attempt_ids']
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in summary['pending_pairs']:
        writer.writerow({**row, 'validation_failures': json.dumps(row['validation_failures'], ensure_ascii=False),
                         'other_unvalidated_attempt_ids': json.dumps(row['other_unvalidated_attempt_ids'])})
    return stream.getvalue()


def safe_operation_path(path):
    path = Path(path).resolve()
    p.require(path.is_relative_to(OPERATION_ROOT.resolve()) and path != OPERATION_ROOT.resolve(),
              'Operational output must be a child of the separate operational_outputs tree')
    p.require(not path.exists(), 'Operational output exists; never overwrite an operation or summary')
    return path


def write_new(path, text):
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def save_summary(path, summary):
    write_new(path / 'validation_summary.json', json_text(summary))
    write_new(path / 'validation_summary.csv', csv_summary(summary))


def start_segment(directory, fingerprint, operation_id, amendment_sha256, done_count, pending):
    execution = str(uuid.uuid4())
    legacy.append(directory / 'events.jsonl', {
        'event': 'execution_started', 'execution_id': execution, 'at': legacy.now(),
        'experiment_sha256': fingerprint, 'already_completed': done_count,
        'retry_unfinished': False, 'pending_pairs': [list(k) for k in sorted(pending)],
        'operational_policy_id': POLICY['policy_id'], 'operation_id': operation_id,
        'operational_amendment_sha256': amendment_sha256,
        'continue_on_validation_error': True, 'python': platform.python_version(),
        'platform': platform.platform(),
    })
    return execution


class CaptureClient:
    """Retain every answer text block before legacy parsing; never alter a response."""
    def __init__(self, client):
        self.client = client
        self.messages = self
        self.text_blocks = []

    def create(self, **kwargs):
        response = self.client.messages.create(**kwargs)
        self.text_blocks = [block.text for block in response.content if block.type == 'text']
        return response


def execute_continuation(client, directory, manifest, items, enabled=False):
    p.require(enabled, 'Continuation requires explicit --continue-on-validation-error')
    with legacy.locked(directory):
        done, counts, pending = inspect(directory, manifest, items)
        fingerprint = p.digest(manifest)
        # All existing attempted/unvalidated pairs are deferred, even below the cap.
        work = [item for item in items if p.key(item) not in done and counts[p.key(item)] == 0]
        if not (Path(directory) / 'manifest.json').exists():
            legacy.initialize(Path(directory), manifest)
        preexisting = {name: p.file_hash(Path(directory) / name) for name in
                       ('manifest.json', 'results.jsonl', 'attempts.jsonl', 'events.jsonl')
                       if (Path(directory) / name).exists()}
        operation_id = str(uuid.uuid4())
        opdir = safe_operation_path(OPERATION_ROOT / operation_id)
        opdir.mkdir(parents=True, exist_ok=False)
        amendment = {
            'operational_policy': POLICY, 'operation_id': operation_id, 'created_at': legacy.now(),
            'scientific_protocol_unchanged': True, 'scientific_experiment_sha256': fingerprint,
            'scientific_manifest_sha256': preexisting.get('manifest.json'),
            'official_directory': str(directory), 'pre_operation_file_sha256': preexisting,
            'pre_operation_file_bytes': {name: (Path(directory) / name).stat().st_size for name in preexisting},
            'frozen_scientific_source_sha256': manifest['source_code_sha256'],
            'operational_source_sha256': operation_sources(),
            'deferred_attempted_pairs': [list(k) for k in sorted(pending)],
            'skipped_validated_pairs': len(done), 'planned_new_attempts': [list(p.key(i)) for i in work],
        }
        write_new(opdir / 'amendment.json', json_text(amendment))
        # No scientific manifest is rewritten or amended. Events link to this sidecar.
        amendment_hash = p.file_hash(opdir / 'amendment.json')
        segment = start_segment(directory, fingerprint, operation_id, amendment_hash, len(done), pending)
        attempt = None
        capture = CaptureClient(client)
        fatal = None
        try:
            for item in work:
                key = p.key(item)
                p.require(counts[key] < manifest['max_attempts_per_pair'], 'Attempt limit reached')
                attempt = {**legacy.item_metadata(item), 'attempt_id': str(uuid.uuid4()),
                           'execution_id': segment, 'experiment_sha256': fingerprint,
                           'attempt_number': counts[key] + 1, 'started_at': legacy.now()}
                legacy.append(Path(directory) / 'attempts.jsonl', attempt)
                counts[key] += 1
                try:
                    judgment, metadata = legacy.judge(capture, item, manifest['configuration'])
                except legacy.ResponseValidationError as error:
                    metadata = {**error.response_metadata, 'raw_text_blocks': capture.text_blocks}
                    legacy.append(Path(directory) / 'events.jsonl', {
                        'event': 'execution_failed', 'execution_id': segment, 'at': legacy.now(),
                        'experiment_sha256': fingerprint, 'attempt_id': attempt['attempt_id'],
                        **legacy.failure_metadata(error), 'response_metadata': metadata,
                        'validation_error': str(error), 'validation_status': 'invalid',
                        'failure_scope': 'pair', 'operation_id': operation_id,
                    })
                    pending.add(key)
                    segment = start_segment(directory, fingerprint, operation_id, amendment_hash, len(done), pending)
                    attempt = None
                    continue
                record = {**attempt, **judgment, **metadata, 'completed_at': legacy.now(),
                          'model': p.MODEL, 'effort': p.EFFORT, 'thinking': {'type': 'adaptive'},
                          'validation_status': 'validated'}
                legacy.append(Path(directory) / 'results.jsonl', record)
                done[key] = record
                print(f'Validated {len(done)}/{len(items)}: {key[0]} × {key[1]}', flush=True)
            legacy.verify_manifest_sources(manifest)
        except BaseException as error:
            fatal = error
            legacy.append(Path(directory) / 'events.jsonl', {
                'event': 'execution_failed', 'execution_id': segment, 'at': legacy.now(),
                'experiment_sha256': fingerprint, 'attempt_id': attempt['attempt_id'] if attempt else None,
                **legacy.failure_metadata(error), 'operation_id': operation_id,
            })
        if fatal is None:
            complete = len(done) == len(items)
            legacy.append(Path(directory) / 'events.jsonl', {
                'event': 'execution_completed', 'execution_id': segment, 'at': legacy.now(),
                'experiment_sha256': fingerprint, 'validated_results': len(done),
                'coverage_validated': complete, 'status': 'complete' if complete else 'finished_with_pending',
                'operation_id': operation_id,
            })
        summary = validation_summary(directory, manifest, items)
        save_summary(opdir, summary)
        write_new(opdir / 'operation_result.json', json_text({
            'operation_id': operation_id, 'complete': summary['complete'],
            'fatal_error_type': type(fatal).__name__ if fatal else None,
            'summary_sha256': p.file_hash(opdir / 'validation_summary.json'),
        }))
        if fatal:
            raise fatal
        return summary, opdir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--full-run', action='store_true')
    mode.add_argument('--summarize-only', action='store_true', help='Write a derived validation summary; no API calls')
    parser.add_argument('--continue-on-validation-error', action='store_true')
    parser.add_argument('--max-tokens', type=int, default=p.DEFAULT_MAX_TOKENS)
    parser.add_argument('--timeout', type=float, default=float(p.DEFAULT_TIMEOUT))
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    directory, manifest, items, state = legacy.prepare('full', args.max_tokens, args.timeout, args.output_dir)
    summary = validation_summary(directory, manifest, items)
    print(json_text({k: v for k, v in summary.items() if k != 'pending_pairs'}))
    print('Existing attempted/unvalidated pairs will be DEFERRED without another attempt.')
    if args.summarize_only:
        path = safe_operation_path(OPERATION_ROOT / ('summary-' + p.digest(summary)))
        path.mkdir(parents=True, exist_ok=False)
        save_summary(path, summary)
        print(f'Summary: {path}')
        return
    if not args.full_run:
        print('Read-only offline preflight; no API client or output files created.')
        return
    p.require(args.continue_on_validation_error, 'Live continuation requires --continue-on-validation-error')
    p.require(bool(os.environ.get('ANTHROPIC_API_KEY')), 'ANTHROPIC_API_KEY is required')
    import anthropic
    p.require(importlib.metadata.version('anthropic') == p.SDK_VERSION, 'Install pinned scientific SDK requirements')
    with anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'], max_retries=0,
                             timeout=args.timeout, base_url='https://api.anthropic.com') as client:
        result, path = execute_continuation(client, directory, manifest, items, enabled=True)
    print(f"Validated={result['validated_judgments']}; pending={result['invalid_or_pending_pairs']}; summary={path}")


if __name__ == '__main__':
    main()
