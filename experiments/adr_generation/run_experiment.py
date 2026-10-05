"""Preflight or explicitly execute independent ADRs; stop on any failure, never retry."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import string
import sys
import tempfile

import generate_adr as pilot


OUTPUTS = pilot.OUTPUT.parent
ATTEMPTS = OUTPUTS / 'attempts'
EXPECTED_COUNT = 36
PILOT_PAIR = (pilot.USER_STORY_ID, pilot.PATTERN_ID)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pair_of(row):
    return row['user_story_id'], row['pattern_id']


def filename(pair):
    return f'{pair[0]}_P{pair[1]}.json'


def prompt_for(row):
    # Exactly the pilot's substitutions and input validation; no RAG fields.
    pilot.validate_input(row)
    if not re.fullmatch(r'SYS\d+-US\d+', row['user_story_id']):
        raise ValueError('Unsafe user story identifier')
    if not re.fullmatch(r'\d{3}', row['pattern_id']):
        raise ValueError('Unsafe pattern identifier')
    placeholders = {name for _, name, _, _ in
                    string.Formatter().parse(pilot.PROMPT_TEMPLATE) if name is not None}
    if placeholders != set(pilot.INPUT_FIELDS):
        raise ValueError('Prompt placeholders do not match allowed input fields')
    return pilot.PROMPT_TEMPLATE.format(**{f: row[f] for f in pilot.INPUT_FIELDS})


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'),
                      object_pairs_hook=pilot.reject_duplicate_keys)


def validate_completed(artifact, prompts, source_hash):
    if not isinstance(artifact, dict):
        raise ValueError('Output must be an object')
    pair = pair_of(artifact)
    if pair not in prompts:
        raise ValueError('Output pair is not an expected applicable pair')
    required = {
        'model': pilot.MODEL, 'reasoning_effort': pilot.REASONING_EFFORT,
        'source_file': str(pilot.SOURCE.relative_to(pilot.ROOT)),
        'source_sha256': source_hash,
        'prompt_sha256': digest(prompts[pair].encode('utf-8')),
    }
    for field, value in required.items():
        if artifact.get(field) != value:
            raise ValueError(f'Incorrect metadata: {field}')
    if type(artifact.get('api_calls')) is not int or artifact['api_calls'] != 1:
        raise ValueError('Expected api_calls = 1')
    response_id = artifact.get('response_id')
    if not isinstance(response_id, str) or not response_id.strip():
        raise ValueError('Missing response_id')
    structured = artifact.get('structured_outputs')
    if not isinstance(structured, dict) or any(
            structured.get(f) is not True for f in ('strict', 'validation_succeeded')):
        raise ValueError('Missing strict Structured Outputs validation')
    adr = artifact.get('adr')
    if not isinstance(adr, dict) or set(adr) != set(pilot.FIELDS) | {'status'}:
        raise ValueError('Incorrect ADR fields')
    if adr['status'] != 'Proposed':
        raise ValueError('ADR status must be Proposed')
    pilot.validate_adr({f: adr[f] for f in pilot.FIELDS})
    return pair


def next_attempt(pair, retry_failed=False):
    """Authorize only recorded failures; retain every claim and failure verbatim."""
    original = ATTEMPTS / filename(pair)
    stem = original.stem
    attempts = [(1, original)] if original.exists() else []
    for path in ATTEMPTS.glob(f'{stem}.retry-*.json'):
        match = re.fullmatch(re.escape(stem) + r'\.retry-(\d+)\.json', path.name)
        if match:
            attempts.append((int(match[1]), path))
    if not attempts:
        return original, None
    number, previous = max(attempts)
    if not retry_failed:
        raise ValueError(f'Unresolved prior attempt for {pair}; automatic retry is forbidden')
    claim = read_json(previous)
    failure = read_json(previous.with_name(f'{previous.stem}.failure.json'))
    if (pair_of(claim) != pair or claim.get('state') != 'started'
            or pair_of(failure) != pair or failure.get('state') != 'failed'
            or not isinstance(failure.get('error'), str) or not failure['error'].strip()):
        raise ValueError(f'Prior attempt for {pair} has no valid recorded failure')
    return ATTEMPTS / f'{stem}.retry-{number + 1}.json', previous


def preflight(retry_failed=False):
    source_hash = digest(pilot.SOURCE.read_bytes())
    with pilot.SOURCE.open(encoding='utf-8', newline='') as source:
        rows = [r for r in csv.DictReader(source) if r.get('classification') == 'applicable']
    counts = Counter(pair_of(r) for r in rows)
    duplicates = [p for p, count in counts.items() if count > 1]
    errors = []
    if len(rows) != EXPECTED_COUNT:
        errors.append(f'Expected {EXPECTED_COUNT} applicable rows; found {len(rows)}')
    if duplicates:
        errors.append(f'Duplicate expected pairs: {duplicates}')
    if PILOT_PAIR not in counts:
        errors.append('Approved pilot pair is missing from source')
    prompts = {}
    for row in rows:
        try:
            prompts[pair_of(row)] = prompt_for(row)
        except Exception as error:
            errors.append(f'Invalid source row {pair_of(row)}: {error}')
    completed = set()
    invalid = []
    pilot_valid = False
    for path in sorted(OUTPUTS.glob('*.json')):
        try:
            pair = validate_completed(read_json(path), prompts, source_hash)
            if path == pilot.OUTPUT and pair != PILOT_PAIR:
                raise ValueError('Approved pilot file contains a different pair')
            if pair in completed:
                raise ValueError('Duplicate completed pair')
            completed.add(pair)
            if path == pilot.OUTPUT:
                pilot_valid = True
        except Exception as error:
            invalid.append(f'{path.name}: {error}')
    if not pilot_valid:
        errors.append('Approved pilot file is missing or invalid; regeneration is forbidden')
    errors.extend(invalid)
    pending = sorted(set(counts) - completed)
    authorized = []
    for pair in pending:
        try:
            _, previous = next_attempt(pair, retry_failed)
            if previous is not None:
                authorized.append(pair)
        except Exception as error:
            errors.append(str(error))
        if (OUTPUTS / filename(pair)).exists():
            errors.append(f'Pending output path already exists: {filename(pair)}')
    print(f'Expected ADRs: {len(rows)}')
    print(f'Completed ADRs: {len(completed)}')
    print(f'Pending ADRs: {len(pending)}')
    print(f'API calls required: {len(pending)}')
    print(f'Duplicate expected pairs: {len(duplicates)}')
    print(f'Invalid completed outputs: {len(invalid)}')
    print('API calls made: 0')
    if retry_failed:
        print(f'Failed attempts explicitly authorized for retry: {len(authorized)}')
        for pair in authorized:
            print(f'Retry authorized: {pair[0]} x {pair[1]}')
    for error in errors:
        print(f'Preflight error: {error}')
    print(f'Preflight validation: {"FAILED" if errors else "PASSED"}')
    if errors:
        raise ValueError('Preflight failed; execution blocked')
    return prompts, pending, source_hash


def save_exclusive(path, artifact):
    """Publish a fully written artifact atomically without replacing existing files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(artifact, output, ensure_ascii=False, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def execute(prompts, pending, source_hash, retry_failed=False):
    # A persistent claim prevents a interrupted/failed request from silently being
    # retried on a later invocation. Completed claims are ignored by preflight.
    calls = 0
    for pair in pending:
        path = OUTPUTS / filename(pair)
        attempt, previous = next_attempt(pair, retry_failed)
        if path.exists() or digest(pilot.SOURCE.read_bytes()) != source_hash:
            raise ValueError('Output exists or source changed; execution stopped')
        save_exclusive(attempt, {'user_story_id': pair[0], 'pattern_id': pair[1],
                                 'state': 'started', 'automatic_retry': False,
                                 'manual_retry_authorized': previous is not None,
                                 'prior_attempt': previous.name if previous else None})
        try:
            adr, response_id = pilot.generate(prompts[pair])
            calls += 1
            pilot.validate_adr(adr)
            artifact = {
                'user_story_id': pair[0], 'pattern_id': pair[1],
                'model': pilot.MODEL, 'reasoning_effort': pilot.REASONING_EFFORT,
                'response_id': response_id, 'api_calls': 1,
                'source_file': str(pilot.SOURCE.relative_to(pilot.ROOT)),
                'source_sha256': source_hash,
                'prompt_sha256': digest(prompts[pair].encode('utf-8')),
                'structured_outputs': {'strict': True, 'validation_succeeded': True},
                'adr': {'title': adr['title'], 'context': adr['context'],
                        'decision': adr['decision'], 'status': 'Proposed',
                        'consequences': adr['consequences']},
            }
            validate_completed(artifact, prompts, source_hash)
            save_exclusive(path, artifact)
            print(f'Saved: {path}', flush=True)
        except Exception as error:
            message = str(error)
            key = os.environ.get('OPENAI_API_KEY')
            if key:
                message = message.replace(key, '[REDACTED]')
            save_exclusive(attempt.with_name(f'{attempt.stem}.failure.json'), {
                'user_story_id': pair[0], 'pattern_id': pair[1],
                'state': 'failed', 'error': message, 'automatic_retry': False,
                'api_calls': 'At most one; request may have failed before dispatch',
            })
            raise ValueError(f'Execution stopped for {pair}: {message}; no retry') from None
    print(f'API calls made: {calls}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true', help='Local validation only; zero API calls')
    mode.add_argument('--execute', action='store_true', help='Explicitly run pending pairs sequentially')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Authorize recorded failed attempts; requires --execute to call API')
    args = parser.parse_args()
    try:
        prompts, pending, source_hash = preflight(args.retry_failed)
        if args.execute:
            execute(prompts, pending, source_hash, args.retry_failed)
        return 0
    except Exception as error:
        print(f'Experiment stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
