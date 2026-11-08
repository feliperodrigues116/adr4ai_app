"""Response-conditioned support evaluation. Default is read-only offline preflight."""

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import time
import uuid

import protocol as p

OUTPUT_ROOT = p.HERE / 'outputs'


def now():
    return datetime.now(timezone.utc).isoformat()


def append(path, record):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def check_directory(directory):
    directory = Path(directory).resolve()
    p.require(directory.is_relative_to(OUTPUT_ROOT) and directory != OUTPUT_ROOT,
              f'Output directory must be a child of {OUTPUT_ROOT}')
    if directory.exists():
        p.require(directory.is_dir(), 'Output path is not a directory')
        p.require(all(not child.is_symlink() for child in directory.iterdir()),
                  'Symlink output entries are not permitted')
        allowed = {'.lock', 'manifest.json', 'attempts.jsonl', 'results.jsonl', 'events.jsonl'}
        p.require(all(child.is_file() and child.name in allowed for child in directory.iterdir()),
                  'Unknown files/directories in output path; use a fresh experiment directory')
    return directory


@contextmanager
def locked(directory):
    directory = check_directory(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another support runner holds this output directory') from error
        yield


def item_metadata(item):
    return {'user_story_id': p.key(item)[0], 'pattern_id': p.key(item)[1],
            'gpt_classification': item['gpt_assessment']['classification'],
            'input_sha256': p.digest(item), 'prompt_sha256': p.digest(p.build_prompt(item))}


def make_manifest(all_items, selected, mode, max_tokens, timeout):
    code_paths = [p.HERE / name for name in ('protocol.py', 'run_experiment.py', 'instructions.txt',
                                           'response_schema.json', 'source_baseline.json', 'requirements.txt',
                                           'protocol_revision.json')]
    return {
        'protocol_id': p.PROTOCOL_ID, 'protocol_version': p.PROTOCOL_VERSION,
        'response_conditioned': True, 'mode': mode,
        'configuration': p.request_config(max_tokens), 'timeout_seconds': timeout,
        'sdk_version': p.SDK_VERSION, 'sdk_max_retries': 0,
        'max_attempts_per_pair': p.MAX_ATTEMPTS_PER_PAIR,
        'retry_policy': 'stop on failure; explicit --retry-unfinished required; never repeat validated pairs',
        'source_file_sha256': p.verify_sources(),
        'source_code_sha256': {path.relative_to(p.ROOT).as_posix(): p.file_hash(path) for path in code_paths},
        'all_inputs_sha256': p.digest(all_items),
        'original_gpt_counts': dict(p.EXPECTED_COUNTS), 'all_pairs': len(all_items),
        'instructions_sha256': p.digest(p.INSTRUCTIONS), 'schema_sha256': p.digest(p.SCHEMA),
        'hash_encoding': 'source files: raw bytes; other hashes: sorted compact ensure_ascii=False JSON, UTF-8',
        'pilot_selection': [item_metadata(item) for item in p.pilot_items(all_items)],
        'planned_items': [{**item_metadata(item), 'prompt_text': p.build_prompt(item)} for item in selected],
    }


def resume_state(directory, manifest, items):
    """Read only. Never creates, repairs, normalizes, or truncates journals."""
    directory = check_directory(directory)
    manifest_path = directory / 'manifest.json'
    if not manifest_path.exists():
        p.require(not directory.exists() or not any(child.name != '.lock' for child in directory.iterdir()),
                  'Output files exist without a manifest')
        return {}, Counter(), set()
    saved = p.strict_json(manifest_path.read_text(encoding='utf-8'))
    p.require(saved['experiment'] == manifest, 'Manifest/provenance mismatch; use the original protocol or a new directory')
    planned = {p.key(item): item for item in items}
    p.require(len(planned) == len(items), 'Duplicate planned pairs')
    fingerprint = p.digest(manifest)
    events = p.read_rows(directory / 'events.jsonl', optional=True)
    starts = {}
    for event in events:
        p.require(event.get('experiment_sha256') == fingerprint, 'Event manifest hash mismatch')
        execution_id = event.get('execution_id')
        if event.get('event') == 'execution_started':
            p.require(execution_id not in starts, 'Duplicate execution ID')
            starts[execution_id] = event
        else:
            p.require(event.get('event') in ('execution_failed', 'execution_completed')
                      and execution_id in starts, 'Invalid execution event')
    attempts = p.read_rows(directory / 'attempts.jsonl', optional=True)
    attempts_by_id, counts = {}, Counter()
    for attempt in attempts:
        key = attempt.get('user_story_id'), attempt.get('pattern_id')
        p.require(key in planned, 'Unexpected attempt pair')
        attempt_id = attempt.get('attempt_id')
        p.require(isinstance(attempt_id, str) and attempt_id and attempt_id not in attempts_by_id,
                  'Missing or duplicate attempt ID')
        p.require(attempt.get('execution_id') in starts, 'Attempt has no execution-start event')
        expected = item_metadata(planned[key])
        p.require(all(attempt.get(k) == v for k, v in expected.items())
                  and attempt.get('experiment_sha256') == fingerprint, 'Attempt provenance mismatch')
        counts[key] += 1
        p.require(attempt.get('attempt_number') == counts[key] <= p.MAX_ATTEMPTS_PER_PAIR,
                  'Invalid attempt number or attempt limit exceeded')
        attempts_by_id[attempt_id] = attempt
    done, response_ids = {}, set()
    for record in p.read_rows(directory / 'results.jsonl', optional=True):
        key = record.get('user_story_id'), record.get('pattern_id')
        p.require(key in planned and key not in done, 'Unexpected or duplicate validated result')
        attempt = attempts_by_id.get(record.get('attempt_id'))
        p.require(attempt is not None and all(record.get(k) == v for k, v in attempt.items()),
                  'Result/attempt mismatch')
        judgment = {k: record.get(k) for k in p.SCHEMA['required']}
        p.validate_judgment(judgment, planned[key]['case'])
        p.require(p.strict_json(record.get('response_text', '')) == judgment, 'Raw structured response differs from saved judgment')
        p.require(record.get('validation_status') == 'validated'
                  and record.get('model') == record.get('response_model') == p.MODEL
                  and record.get('effort') == p.EFFORT and record.get('thinking') == {'type': 'adaptive'}
                  and record.get('stop_reason') == 'end_turn', 'Saved response configuration/status mismatch')
        response_id = record.get('response_id')
        p.require(isinstance(response_id, str) and response_id and response_id not in response_ids,
                  'Missing or duplicate response ID')
        response_ids.add(response_id)
        done[key] = record
    return done, counts, set(counts) - set(done)


def initialize(directory, manifest):
    path = directory / 'manifest.json'
    if not path.exists():
        with path.open('x', encoding='utf-8') as stream:
            json.dump({'created_at': now(), 'experiment': manifest}, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())


class ResponseValidationError(ValueError):
    def __init__(self, message, metadata):
        super().__init__(message)
        self.response_metadata = metadata


def judge(client, item, configuration):
    started = time.monotonic()
    response = client.messages.create(**configuration,
        messages=[{'role': 'user', 'content': p.build_prompt(item)}])
    # Preserve provider metadata and JSON answer, never hidden/summarized thinking.
    text_blocks = [block for block in response.content if block.type == 'text']
    metadata = {
        'response_id': response.id, 'response_model': response.model,
        'request_id': getattr(response, '_request_id', None), 'stop_reason': response.stop_reason,
        'usage': response.usage.model_dump(mode='json'),
        'content_block_types': [block.type for block in response.content],
        'raw_response_metadata': response.model_dump(mode='json', exclude={'content'}),
        'response_text': text_blocks[0].text if len(text_blocks) == 1 else None,
        'elapsed_seconds': time.monotonic() - started,
    }
    try:
        p.require(response.stop_reason == 'end_turn', f'Incomplete/refused response: {response.stop_reason}')
        p.require(response.model == p.MODEL, 'Actual model differs from fixed protocol model')
        p.require(all(block.type in ('thinking', 'redacted_thinking', 'text') for block in response.content),
                  'Unexpected content block type')
        p.require(len(text_blocks) == 1, 'Expected exactly one structured text block')
        judgment = p.strict_json(text_blocks[0].text)
        p.validate_judgment(judgment, item['case'])
    except ValueError as error:
        raise ResponseValidationError(str(error), metadata) from error
    return judgment, metadata


def failure_metadata(error):
    response = getattr(error, 'response', None)
    headers = getattr(response, 'headers', {})
    return {'error_type': type(error).__name__, 'status_code': getattr(error, 'status_code', None),
            'request_id': getattr(error, 'request_id', None), 'retry_after': headers.get('retry-after'),
            'response_metadata': getattr(error, 'response_metadata', None)}


def check_retry_policy(done, counts, pending, retry_unfinished):
    p.require(not pending or retry_unfinished,
              'Unfinished attempts exist; inspect events/attempts and explicitly use --retry-unfinished')
    p.require(all(counts[key] < p.MAX_ATTEMPTS_PER_PAIR for key in pending),
              'Attempt limit reached; do not discard or rewrite failed attempts')


def verify_manifest_sources(manifest):
    for group in ('source_file_sha256', 'source_code_sha256'):
        for name, expected in manifest[group].items():
            p.require(p.file_hash(p.ROOT / name) == expected,
                      f'Protocol/source changed after planning: {name}')


def execute(client, directory, manifest, items, retry_unfinished=False):
    """Caller supplies a client; CLI alone can construct a live one after preflight."""
    with locked(directory):
        directory = check_directory(directory)
        verify_manifest_sources(manifest)
        done, counts, pending = resume_state(directory, manifest, items)
        check_retry_policy(done, counts, pending, retry_unfinished)
        initialize(directory, manifest)
        fingerprint, execution_id = p.digest(manifest), str(uuid.uuid4())
        append(directory / 'events.jsonl', {'event': 'execution_started', 'execution_id': execution_id,
               'experiment_sha256': fingerprint, 'at': now(), 'already_completed': len(done),
               'retry_unfinished': retry_unfinished,
               'pending_pairs': [list(k) for k in sorted(pending)],
               'python': platform.python_version(), 'platform': platform.platform()})
        attempt = None
        try:
            for item in items:
                key = p.key(item)
                if key in done:
                    continue
                attempt = {**item_metadata(item), 'attempt_id': str(uuid.uuid4()),
                           'execution_id': execution_id, 'experiment_sha256': fingerprint,
                           'attempt_number': counts[key] + 1, 'started_at': now()}
                append(directory / 'attempts.jsonl', attempt)
                judgment, metadata = judge(client, item, manifest['configuration'])
                record = {**attempt, **judgment, **metadata, 'completed_at': now(),
                          'model': p.MODEL, 'effort': p.EFFORT, 'thinking': {'type': 'adaptive'},
                          'validation_status': 'validated'}
                append(directory / 'results.jsonl', record)
                done[key] = record
                counts[key] += 1
                print(f'Validated support judgment {len(done)}/{len(items)}: {key[0]} × {key[1]}', flush=True)
            verify_manifest_sources(manifest)
            final_done, _, unresolved = resume_state(directory, manifest, items)
            p.require(set(final_done) == {p.key(item) for item in items} and not unresolved,
                      'Final coverage validation failed')
        except BaseException as error:
            append(directory / 'events.jsonl', {'event': 'execution_failed', 'execution_id': execution_id,
                   'experiment_sha256': fingerprint, 'at': now(),
                   'attempt_id': attempt['attempt_id'] if attempt else None, **failure_metadata(error)})
            raise
        append(directory / 'events.jsonl', {'event': 'execution_completed', 'execution_id': execution_id,
               'experiment_sha256': fingerprint, 'at': now(), 'validated_results': len(done),
               'coverage_validated': True})
        return done


def prepare(mode, max_tokens, timeout, directory=None):
    p.require(type(max_tokens) is int and max_tokens > 0, 'max-tokens must be a positive integer')
    p.require(type(timeout) in (float, int) and math.isfinite(timeout) and timeout > 0,
              'timeout must be finite and positive')
    p.require(mode in ('technical_pilot', 'full'), 'Unknown experiment scope')
    all_items = p.load_items()
    items = p.pilot_items(all_items) if mode == 'technical_pilot' else all_items
    directory = check_directory(directory or OUTPUT_ROOT / p.MODEL / p.PROTOCOL_VERSION / mode)
    manifest = make_manifest(all_items, items, mode, max_tokens, timeout)
    state = resume_state(directory, manifest, items)
    return directory, manifest, items, state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preflight', '--dry-run', action='store_true', help='Read-only offline checks (default)')
    mode.add_argument('--pilot', action='store_true', help='Explicitly launch exactly three category-stratified cases')
    mode.add_argument('--full-run', action='store_true', help='Explicitly launch all 840 support judgments')
    parser.add_argument('--max-tokens', type=int, default=p.DEFAULT_MAX_TOKENS)
    parser.add_argument('--timeout', type=float, default=p.DEFAULT_TIMEOUT)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--retry-unfinished', action='store_true')
    args = parser.parse_args(argv)
    scope = 'technical_pilot' if args.pilot else 'full'
    directory, manifest, items, (done, counts, pending) = prepare(scope, args.max_tokens, args.timeout, args.output_dir)
    print('Response-conditioned support evaluation: NOT blind classification or ground truth.')
    print('Protocol: ' + p.PROTOCOL_ID + '; instructions SHA256 (canonical JSON): ' + p.digest(p.INSTRUCTIONS))
    print('Original coverage: 840 unique pairs; 12 stories × 70 patterns; 4 systems.')
    print('Original GPT counts: ' + json.dumps(p.EXPECTED_COUNTS, sort_keys=True))
    print('Model/configuration: ' + p.MODEL + '; effort=high; thinking=adaptive; '
          + f'max_tokens={args.max_tokens}; timeout={args.timeout}; SDK={p.SDK_VERSION}; SDK retries=0')
    print('Deterministic pilot: ' + json.dumps([[r['user_story_id'], r['pattern_id'], r['gpt_classification']]
                                              for r in manifest['pilot_selection']]))
    print('Protocol manifest SHA256: ' + p.digest(manifest))
    print(f'Output: {directory}; validated={len(done)}; pending={len(pending)}')
    if not args.pilot and not args.full_run:
        print('OFFLINE PREFLIGHT PASSED: no client, API calls, or output files created.')
        return
    check_retry_policy(done, counts, pending, args.retry_unfinished)
    p.require(bool(os.environ.get('ANTHROPIC_API_KEY')), 'ANTHROPIC_API_KEY is required for explicit live execution')
    # Deferred import keeps default/preflight completely offline and SDK-independent.
    import anthropic
    p.require(importlib.metadata.version('anthropic') == p.SDK_VERSION,
              f'Install this experiment\'s requirements.txt (anthropic=={p.SDK_VERSION})')
    with anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'], max_retries=0,
                             timeout=args.timeout, base_url='https://api.anthropic.com') as client:
        execute(client, directory, manifest, items, args.retry_unfinished)


if __name__ == '__main__':
    main()
