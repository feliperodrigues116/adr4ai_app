"""Audit and consolidate 839 original judgments plus one explicit analytical correction."""

from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SUPPORT = ROOT / 'experiments/llm_judge_support_rq1'
sys.path.insert(0, str(SUPPORT))
import continue_experiment as op

p = op.p
OFFICIAL = SUPPORT / 'outputs/claude-sonnet-5-5/v1.1/full'
CORRECTIONS = SUPPORT / 'operational_outputs/p051-reference-correction-v1.1'
PLAN = HERE / 'p051_reference_correction_plan.json'
REVIEW = HERE / 'p051_correction_review.json'
PAIR = ('SYS02-US01', '051')


def record_key(row):
    return row['user_story_id'], row['pattern_id']


def validate_analytical(rows, items, done, corrected_record):
    expected = {p.key(item): item for item in items}
    p.require(len(rows) == len(expected) == 840, 'Expected exactly 840 analytical records')
    by_pair = {}
    counts = Counter()
    for row in rows:
        key = record_key(row)
        p.require(key in expected and key not in by_pair, 'Duplicate or unknown analytical pair')
        item = expected[key]
        p.require(row['gpt_classification'] == item['gpt_assessment']['classification'], 'GPT classification association mismatch')
        p.validate_judgment(row['judgment'], item['case'])
        p.require(row['source_record_sha256'] == p.digest(row['source_record']), 'Analytical source-record hash mismatch')
        p.require(row['scientific_protocol_id'] == p.PROTOCOL_ID, 'Scientific protocol mismatch')
        if row['record_origin'] == 'official_api_validated':
            p.require(key in done and row['official_api_validated'] is True, 'Wrong official origin label')
            source = done[key]
            p.require(row['source_record'] == source, 'Original official record changed')
            p.require(row['judgment'] == {field: source[field] for field in p.SCHEMA['required']},
                      'Original scientific judgment changed')
            p.require(row['source_response_id'] == source['response_id'] and row['source_attempt_id'] == source['attempt_id'],
                      'Original response/attempt association mismatch')
        elif row['record_origin'] == 'technically_corrected_analytical':
            p.require(key == PAIR and key not in done and row['official_api_validated'] is False,
                      'Corrected record must not be labeled originally validated')
            p.require(row['source_record'] == corrected_record
                      and row['judgment'] == corrected_record['corrected_analytical_judgment'],
                      'Corrected analytical record changed')
            p.require(row['source_attempt_id'] == corrected_record['source_attempt_id']
                      and row['source_response_id'] == corrected_record['original_response_metadata']['response_id'],
                      'Correction response/attempt association mismatch')
        else:
            raise ValueError('Unknown analytical record origin')
        counts[row['record_origin']] += 1
        by_pair[key] = row
    p.require(set(by_pair) == set(expected), 'Incomplete analytical coverage')
    p.require(counts == {'official_api_validated': 839, 'technically_corrected_analytical': 1},
              'Official versus corrected counts must remain 839 + 1')
    return dict(counts)


def prepare_records():
    directory, manifest, items, _ = op.legacy.prepare('full', 32768, 600.0, OFFICIAL)
    done, _, pending = op.inspect(directory, manifest, items)
    p.require(len(done) == 839 and pending == {PAIR}, 'Official frozen state is not 839 validated plus P051 pending')
    correction_audit = p.strict_json((CORRECTIONS / 'correction_manifest.json').read_text())
    for name, sha in correction_audit['output_sha256'].items():
        p.require(p.file_hash(CORRECTIONS / name) == sha, f'Correction output hash mismatch: {name}')
    p.require(correction_audit['tool_source_sha256'] == op.operation_sources(), 'Correction tool source provenance mismatch')
    p.require(correction_audit['approved_plan_sha256'] == p.file_hash(PLAN), 'Approved source plan changed')
    p.require((CORRECTIONS / 'approved_plan.json').read_bytes() == PLAN.read_bytes(), 'Archived plan differs from source plan')
    p.require(correction_audit['official_validated_count'] == 839
              and correction_audit['corrections_are_excluded_from_official_coverage_and_verdict_counts'] is True,
              'Correction audit must preserve official counts')
    for name, sha in correction_audit['source_snapshot_sha256'].items():
        p.require(p.file_hash(OFFICIAL / name) == sha, f'Official source changed after correction: {name}')
    corrected = p.read_rows(CORRECTIONS / 'corrected_analytical_records.jsonl')
    log = p.read_rows(CORRECTIONS / 'correction_log.jsonl')
    plan = p.strict_json(PLAN.read_text())
    p.require(len(corrected) == len(log) == len(plan['corrections']) == 1, 'Expected exactly one explicit correction')
    c, entry, approval = corrected[0], log[0], plan['corrections'][0]
    review = p.strict_json(REVIEW.read_text())
    failures = review['failed_responses']
    p.require(len(failures) == 2, 'Both failed responses must be reviewed')
    events = p.read_rows(OFFICIAL / 'events.jsonl')
    attempts = {a['attempt_id']: a for a in p.read_rows(OFFICIAL / 'attempts.jsonl')}
    for reviewed in failures:
        source = reviewed['source_failure']
        event = events[source['event_line'] - 1]
        p.require(event['attempt_id'] == source['attempt_id'] and event['response_metadata'] == reviewed['response_metadata'],
                  'Reviewed failed response does not match preserved original event')
        p.require(reviewed['judgment'] == p.strict_json(event['response_metadata']['response_text']),
                  'Reviewed failed judgment changed')
        p.require(attempts[source['attempt_id']]['attempt_number'] == source['attempt_number'], 'Wrong failed attempt order')
    selected = min(failures, key=lambda f: f['source_failure']['attempt_number'])
    p.require(c['source_attempt_id'] == selected['source_failure']['attempt_id'] == approval['attempt_id'],
              'Source correction must use earliest failed attempt, not select by outcome')
    p.require(c['original_response_text'] == selected['response_metadata']['response_text']
              and c['original_response_metadata'] == selected['response_metadata']
              and c['original_judgment'] == selected['judgment'], 'Original correction source changed')
    p.require(record_key(c) == PAIR and c['not_an_original_validated_judgment'] is True
              and c['original_validation_status'] == 'invalid', 'Correction origin mislabeled')
    p.require(entry['corrected_record_sha256'] == p.digest(c), 'Correction record hash mismatch')
    p.require(all(entry[key] == value for key, value in approval.items()), 'Correction log differs from explicit plan')
    p.require(approval['approved'] is True and approval['field'] == 'evidence_refs', 'Only explicit approved reference edits allowed')
    p.require(plan['scientific_manifest_sha256'] == p.file_hash(OFFICIAL / 'manifest.json'), 'Plan manifest mismatch')
    p.require(c['corrected_analytical_judgment']['evidence_refs'] == approval['replacement'] == entry['corrected_value'],
              'Corrected reference array inconsistent')
    p.require(entry['original_value'] == c['original_judgment']['evidence_refs'], 'Original references changed')
    p.require(entry['raw_response_sha256'] == p.digest(c['original_response_text']), 'Original response hash mismatch')
    old = c['original_judgment']['evidence_refs']
    new = c['corrected_analytical_judgment']['evidence_refs']
    p.require(old == ['SYS02-US01-AC02', 'SYS02-US01-AC05', 'SYS02-US01-US01']
              and new == ['SYS02-US01-AC02', 'SYS02-US01-AC05', 'SYS02-US01'], 'Correction exceeds the single reviewed identifier replacement')
    for field in ('verdict', 'rationale', 'identified_gaps'):
        p.require(c['original_judgment'][field] == c['corrected_analytical_judgment'][field],
                  f'Correction changed scientific field: {field}')
    item = next(item for item in items if p.key(item) == PAIR)
    p.validate_judgment(c['corrected_analytical_judgment'], item['case'])
    p.require(review['original_requirement_case'] == item['case'], 'Reviewed requirement case changed')
    p.require(failures[0]['judgment']['verdict'] == failures[1]['judgment']['verdict'] == 'supported'
              and failures[0]['judgment']['identified_gaps'] == failures[1]['judgment']['identified_gaps'] == [],
              'Failed response verdict/gap agreement changed')
    p.require(failures[0]['judgment']['rationale'] != failures[1]['judgment']['rationale'], 'Do not conflate distinct original rationales')
    rows = []
    official_lines = {record_key(row): number for number, row in enumerate(p.read_rows(OFFICIAL / 'results.jsonl'), 1)}
    for item in items:
        key = p.key(item)
        original = done.get(key)
        is_original = original is not None
        source = original if is_original else c
        judgment = {field: original[field] for field in p.SCHEMA['required']} if is_original else c['corrected_analytical_judgment']
        rows.append({
            'user_story_id': key[0], 'pattern_id': key[1], 'system': item['case']['system'],
            'gpt_classification': item['gpt_assessment']['classification'], 'scientific_protocol_id': p.PROTOCOL_ID,
            'record_origin': 'official_api_validated' if is_original else 'technically_corrected_analytical',
            'official_api_validated': is_original, 'judgment': judgment,
            'source_response_id': original['response_id'] if is_original else c['original_response_metadata']['response_id'],
            'source_attempt_id': original['attempt_id'] if is_original else c['source_attempt_id'],
            'source_file': str((OFFICIAL / 'results.jsonl' if is_original else CORRECTIONS / 'corrected_analytical_records.jsonl').relative_to(ROOT)),
            'source_line': official_lines[key] if is_original else 1, 'source_record_sha256': p.digest(source),
            'correction_timestamp': None if is_original else approval['approved_at'],
            'source_record': source,
        })
    validate_analytical(rows, items, done, c)
    return rows, items, done, c, review


def serialize_csv(rows):
    stream = io.StringIO(newline='')
    fields = ['user_story_id', 'pattern_id', 'system', 'gpt_classification', 'record_origin', 'official_api_validated',
              'verdict', 'evidence_refs', 'rationale', 'identified_gaps', 'source_response_id', 'source_attempt_id',
              'source_file', 'source_line', 'source_record_sha256', 'correction_timestamp']
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        values = {key: row[key] for key in fields if key not in p.SCHEMA['required']}
        values.update(row['judgment'])
        for field in ('evidence_refs', 'identified_gaps'):
            values[field] = json.dumps(values[field], ensure_ascii=False)
        writer.writerow(values)
    return stream.getvalue()


def input_hashes():
    paths = [OFFICIAL / name for name in ('manifest.json', 'results.jsonl', 'attempts.jsonl', 'events.jsonl')]
    paths += [CORRECTIONS / name for name in ('approved_plan.json', 'corrected_analytical_records.jsonl',
                                            'correction_log.jsonl', 'correction_manifest.json')]
    paths += [PLAN, REVIEW, SUPPORT / 'protocol.py', SUPPORT / 'run_experiment.py',
              SUPPORT / 'instructions.txt', SUPPORT / 'response_schema.json', SUPPORT / 'protocol_revision.json',
              SUPPORT / 'source_baseline.json', HERE / 'consolidate.py', HERE / 'test_consolidation.py']
    paths += [ROOT / name for name in p.verify_sources()]
    for event in p.read_rows(OFFICIAL / 'events.jsonl'):
        if event.get('event') == 'execution_started' and 'operation_id' in event:
            opdir = op.OPERATION_ROOT / event['operation_id']
            paths += [path for path in opdir.iterdir() if path.is_file()]
    return {path.relative_to(ROOT).as_posix(): p.file_hash(path) for path in sorted(set(paths))}


def write_identical_or_new(path, text):
    if path.exists():
        p.require(path.read_bytes() == text.encode('utf-8'), f'Derived file differs; refusing overwrite: {path}')
    else:
        op.write_new(path, text)


def main():
    before = input_hashes()
    rows, items, done, corrected, review = prepare_records()
    counts = validate_analytical(rows, items, done, corrected)
    validation = {
        'status': 'passed', 'expected_pairs': 840, 'unique_analytical_pairs': len({record_key(row) for row in rows}),
        'official_api_validated_judgments': counts['official_api_validated'],
        'technically_corrected_analytical_records': counts['technically_corrected_analytical'],
        'total_analytical_coverage': len(rows), 'official_unresolved_pairs': [list(PAIR)],
        'official_experiment_complete': False, 'analytical_coverage_complete': True,
        'user_stories': len({row['user_story_id'] for row in rows}),
        'patterns': len({row['pattern_id'] for row in rows}), 'systems': len({row['system'] for row in rows}),
        'schema_and_reference_validation': 'passed for all 840 analytical judgments using unchanged protocol validator',
        'both_original_rationales_preserved': True, 'selected_rationale_preserved_verbatim': True,
        'source_response_id': corrected['original_response_metadata']['response_id'],
        'correction_timestamp': rows[next(i for i, row in enumerate(rows) if record_key(row) == PAIR)]['correction_timestamp'],
        'correction_is_not_original_api_validation': True,
        'review_authority': review['approval_basis'],
    }
    outputs = {
        'analytical_judgments.jsonl': ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows),
        'analytical_judgments.csv': serialize_csv(rows), 'validation_report.json': op.json_text(validation),
    }
    p.require(before == input_hashes(), 'Sources changed during consolidation')
    provenance = {'input_source_sha256': before,
                  'output_sha256': {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in outputs.items()},
                  'scientific_protocol_id': p.PROTOCOL_ID, 'operational_policy_id': op.POLICY['policy_id'],
                  'schema_sha256': p.digest(p.SCHEMA), 'instructions_sha256': p.digest(p.INSTRUCTIONS),
                  'official_and_corrected_origins_must_not_be_conflated': True}
    outputs['analysis_provenance.json'] = op.json_text(provenance)
    for name, text in outputs.items():
        write_identical_or_new(HERE / name, text)
    print(op.json_text(validation))


if __name__ == '__main__':
    main()
