"""Explicit approved reference-only analytical corrections; never edit official data."""

import argparse
import hashlib
from datetime import datetime
import json
from pathlib import Path
import continue_experiment as op

p = op.p


def apply_plan(directory, manifest, items, plan_path, output_directory):
    plan_path = Path(plan_path)
    plan_bytes = plan_path.read_bytes()
    plan = p.strict_json(plan_bytes.decode('utf-8'))
    p.require(set(plan) == {'scientific_manifest_sha256', 'corrections'}, 'Unexpected correction plan fields')
    p.require(plan['scientific_manifest_sha256'] == p.file_hash(Path(directory) / 'manifest.json'),
              'Correction plan targets a different scientific manifest')
    p.require(isinstance(plan['corrections'], list) and bool(plan['corrections']), 'An explicit nonempty correction list is required')
    summary = op.validation_summary(directory, manifest, items)
    failures = {f['attempt_id']: f for pair in summary['pending_pairs'] for f in pair['validation_failures']}
    events = p.read_rows(Path(directory) / 'events.jsonl')
    by_pair = {p.key(item): item for item in items}
    records, logs, seen = [], [], set()
    expected_fields = {'attempt_id', 'raw_response_sha256', 'field', 'replacement', 'reason',
                       'reviewed_by', 'approved_at', 'approved'}
    for correction in plan['corrections']:
        p.require(isinstance(correction, dict) and set(correction) == expected_fields,
                  'Only explicit approved reference corrections are supported; verdict/rationale/gap edits are forbidden')
        attempt_id = correction['attempt_id']
        p.require(attempt_id in failures and attempt_id not in seen, 'Unknown, duplicate, or no-longer-pending invalid attempt')
        seen.add(attempt_id)
        p.require(correction['approved'] is True and correction['field'] == 'evidence_refs',
                  'Human-approved evidence_refs replacement required; no automatic mapping or verdict edits')
        for field in ('reason', 'reviewed_by', 'approved_at'):
            p.require(isinstance(correction[field], str) and correction[field].strip(), f'Explicit {field} is required')
        p.require(datetime.fromisoformat(correction['approved_at']).tzinfo is not None,
                  'Approval timestamp must include a timezone')
        failure = failures[attempt_id]
        event = events[failure['event_line'] - 1]
        metadata = event['response_metadata']
        raw = metadata['response_text']
        p.require(correction['raw_response_sha256'] == p.digest(raw), 'Raw response hash mismatch')
        original = p.strict_json(raw)
        p.require(isinstance(original, dict) and set(original) == set(p.SCHEMA['required']),
                  'Only an existing four-field judgment can receive reference-only correction')
        attempt = next(a for a in p.read_rows(Path(directory) / 'attempts.jsonl') if a['attempt_id'] == attempt_id)
        item = by_pair[attempt['user_story_id'], attempt['pattern_id']]
        corrected = {**original, 'evidence_refs': correction['replacement']}
        p.require(corrected != original, 'No-op correction is not accepted')
        p.validate_judgment(corrected, item['case'])
        p.require(all(corrected[field] == original[field] for field in ('verdict', 'rationale', 'identified_gaps')),
                  'Scientific judgment must remain unchanged')
        record = {
            'record_kind': 'human_approved_reference_correction_for_analysis_only',
            'not_an_original_validated_judgment': True,
            'user_story_id': item['case']['user_story_id'], 'pattern_id': item['pattern']['id'],
            'gpt_classification': item['gpt_assessment']['classification'],
            'source_attempt_id': attempt_id, 'source_failure': failure,
            'original_validation_status': 'invalid', 'original_response_text': raw,
            'original_response_metadata': metadata, 'original_judgment': original,
            'corrected_analytical_judgment': corrected,
            'analytical_validation_status': 'schema_and_reference_checks_passed_after_explicit_correction',
        }
        records.append(record)
        logs.append({**correction, 'original_value': original['evidence_refs'],
                     'corrected_value': corrected['evidence_refs'],
                     'corrected_record_sha256': p.digest(record)})
    output_directory = op.safe_operation_path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=False)
    # Exact plan bytes are retained; outputs are deterministic for the same approved plan/source snapshot.
    with (output_directory / 'approved_plan.json').open('xb') as stream:
        stream.write(plan_bytes)
    for name, values in (('corrected_analytical_records.jsonl', records), ('correction_log.jsonl', logs)):
        op.write_new(output_directory / name, ''.join(json.dumps(v, ensure_ascii=False, sort_keys=True) + '\n' for v in values))
    audit = {
        'scientific_protocol_id': manifest['protocol_id'], 'official_results_unchanged': True,
        'official_directory': str(directory), 'source_snapshot_sha256': summary['source_snapshot_sha256'],
        'approved_plan_sha256': hashlib.sha256(plan_bytes).hexdigest(), 'correction_count': len(records),
        'tool_source_sha256': op.operation_sources(),
        'output_sha256': {name: p.file_hash(output_directory / name) for name in
                          ('approved_plan.json', 'corrected_analytical_records.jsonl', 'correction_log.jsonl')},
        'official_validated_count': summary['validated_judgments'],
        'corrections_are_excluded_from_official_coverage_and_verdict_counts': True,
    }
    op.write_new(output_directory / 'correction_manifest.json', op.json_text(audit))
    return records, logs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--max-tokens', type=int, default=p.DEFAULT_MAX_TOKENS)
    parser.add_argument('--timeout', type=float, default=float(p.DEFAULT_TIMEOUT))
    args = parser.parse_args(argv)
    directory, manifest, items, _ = op.legacy.prepare('full', args.max_tokens, args.timeout, args.run_dir)
    # Locking prevents the referenced event line/source snapshot changing during derived output creation.
    with op.legacy.locked(directory):
        apply_plan(directory, manifest, items, args.plan, args.output_dir)
    print('Wrote separately labeled analytical corrections and audit log; official records were not modified.')


if __name__ == '__main__':
    main()
