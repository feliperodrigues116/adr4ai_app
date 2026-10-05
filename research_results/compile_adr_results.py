"""Compile immutable ADR artifacts locally using only the Python standard library."""

import ast
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / 'pattern_selection_results.csv'
BACKUP = HERE / 'pattern_selection_results_before_adr.csv'
RESULT = HERE / 'adr_generation_results.csv'
OUTPUTS = ROOT / 'experiments/adr_generation/outputs'
ORIGINAL = (
    'system_id system_purpose user_story_id user_story acceptance_criteria '
    'pattern_id pattern_name pattern_motivation pattern_solution pattern_consequences '
    'classification evidence_refs evidence_text rationale rag_top5'
).split()
EXTRA = ('adr_title adr_status adr_context adr_decision adr_consequences '
         'adr_model adr_reasoning_effort adr_response_id').split()
ADR_FIELDS = ['title', 'status', 'context', 'decision', 'consequences']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pair(row):
    return row['user_story_id'], row['pattern_id']


def csv_rows(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8'), newline=''))
    rows = list(reader)
    require(all(None not in r and all(v is not None for v in r.values()) for r in rows),
            'Malformed CSV row')
    return reader.fieldnames, rows


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def adr_text(adr):
    return '\n'.join(f'{field.title()}: {adr[field]}' for field in ADR_FIELDS)


def encode_csv(columns, rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def compile_data(original_bytes):
    columns, rows = csv_rows(original_bytes)
    require(columns == ORIGINAL, 'Original Study 1 columns differ from the expected schema')
    require(len(rows) == 36, 'Study 1 must contain exactly 36 rows')
    require(all(r['classification'] == 'applicable' for r in rows), 'Non-applicable source row')
    expected = {pair(r): r for r in rows}
    require(len(expected) == 36, 'Duplicate Study 1 pair')
    require(('SYS01-US01', '001') in expected, 'Pilot pair missing')
    # Read the frozen template without executing generation code or importing an SDK.
    tree = ast.parse((ROOT / 'experiments/adr_generation/generate_adr.py').read_text(encoding='utf-8'))
    template = next(ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id == 'PROMPT_TEMPLATE')
    paths = sorted(OUTPUTS.glob('*.json'))  # Attempt records in subdirectories are excluded.
    require(len(paths) == 36, 'Expected exactly 36 ADR JSON outputs')
    artifacts = {}
    pilot_found = False
    for path in paths:
        artifact = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
        require(isinstance(artifact, dict), f'{path.name}: output must be an object')
        key = pair(artifact)
        require(key in expected, f'Unexpected ADR pair: {key}')
        require(key not in artifacts, f'Duplicate ADR pair: {key}')
        adr = artifact['adr']
        require(isinstance(adr, dict) and set(adr) == set(ADR_FIELDS), f'{key}: incorrect ADR fields')
        require(all(isinstance(adr[f], str) and adr[f].strip() for f in ADR_FIELDS),
                f'{key}: empty or non-string ADR field')
        require(adr['status'] == 'Proposed', f'{key}: incorrect status')
        require(artifact['model'] == 'gpt-6-sol', f'{key}: incorrect model')
        require(artifact['reasoning_effort'] == 'high', f'{key}: incorrect reasoning effort')
        structured = artifact['structured_outputs']
        require(isinstance(structured, dict) and structured.get('strict') is True
                and structured.get('validation_succeeded') is True, f'{key}: Structured Outputs not validated')
        require(isinstance(artifact['response_id'], str) and artifact['response_id'].strip(),
                f'{key}: missing response ID')
        require(type(artifact['api_calls']) is int and artifact['api_calls'] == 1,
                f'{key}: incorrect per-ADR call metadata')
        require(artifact['source_file'] == 'research_results/pattern_selection_results.csv'
                and artifact['source_sha256'] == sha(original_bytes), f'{key}: source provenance mismatch')
        prompt = template.format(**expected[key])
        require(artifact['prompt_sha256'] == sha(prompt.encode('utf-8')), f'{key}: prompt provenance mismatch')
        if path.name == 'pilot_SYS01-US01_P001.json':
            require(key == ('SYS01-US01', '001'), 'Pilot pair mismatch')
            pilot_found = True
        artifacts[key] = artifact
    require(pilot_found and set(artifacts) == set(expected), 'Pilot or expected ADR missing')
    dataset = []
    enriched = []
    for row in rows:  # Preserve original Study 1 row order; join exclusively by IDs.
        artifact = artifacts[pair(row)]
        adr = artifact['adr']
        dataset.append({**row, 'adr_title': adr['title'], 'adr_status': adr['status'],
                        'adr_context': adr['context'], 'adr_decision': adr['decision'],
                        'adr_consequences': adr['consequences'], 'adr_model': artifact['model'],
                        'adr_reasoning_effort': artifact['reasoning_effort'],
                        'adr_response_id': artifact['response_id']})
        enriched.append({**row, 'adr': adr_text(adr)})
    result_bytes = encode_csv(ORIGINAL + EXTRA, dataset)
    enriched_bytes = encode_csv(ORIGINAL + ['adr'], enriched)
    # Validate the serialized CSVs before publishing either dataset.
    new_columns, new_rows = csv_rows(enriched_bytes)
    require(new_columns == ORIGINAL + ['adr'] and len(new_rows) == 36, 'Incorrect enriched CSV schema')
    require([{f: r[f] for f in ORIGINAL} for r in new_rows] == rows, 'Original Study 1 values changed')
    require(all(r['adr'] == adr_text(artifacts[pair(r)]['adr']) for r in new_rows), 'ADR text mismatch')
    result_columns, result_rows = csv_rows(result_bytes)
    require(result_columns == ORIGINAL + EXTRA and result_rows == dataset, 'ADR dataset serialization mismatch')
    require({pair(r) for r in result_rows} == set(expected), 'Cross-dataset pair mismatch')
    return result_bytes, enriched_bytes


def publish(datasets):
    """Stage both validated files; roll back both if publication raises an error."""
    staged = {}
    previous = {path: path.read_bytes() if path.exists() else None for path in datasets}
    replaced = []
    try:
        for path, data in datasets.items():
            with tempfile.NamedTemporaryFile(dir=HERE, delete=False) as temporary:
                staged[path] = Path(temporary.name)
                temporary.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
        require(all(path.read_bytes() == data for path, data in datasets.items()), 'Published byte mismatch')
    except BaseException:
        for path in replaced:
            if previous[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous[path])
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def main():
    original_bytes = BACKUP.read_bytes() if BACKUP.exists() else SOURCE.read_bytes()
    result_bytes, enriched_bytes = compile_data(original_bytes)  # All validation before writes.
    current = SOURCE.read_bytes()
    require(current in (original_bytes, enriched_bytes), 'Current Study 1 file differs from original or compiled data')
    if not BACKUP.exists():
        with BACKUP.open('xb') as backup:
            backup.write(original_bytes)
            backup.flush()
            os.fsync(backup.fileno())
    require(BACKUP.read_bytes() == original_bytes, 'Backup bytes differ')
    publish({RESULT: result_bytes, SOURCE: enriched_bytes})
    print('ADR JSON outputs recognized: 36\nStudy 1 rows: 36\nADR dataset rows: 36')
    print('Unique pairs: 36\nDuplicate pairs: 0\nMissing ADRs: 0\nUnexpected ADRs: 0')
    print('Non-empty titles: 36\nNon-empty contexts: 36\nNon-empty decisions: 36\nNon-empty consequences: 36')
    print('Status Proposed: 36\nModel gpt-6-sol: 36\nReasoning effort high: 36')
    print('Structured Outputs validated source ADRs: 36\nNon-empty Study 1 adr values: 36')
    print('Original columns and values preserved: YES\nOnly new Study 1 column: adr (final)')
    print('Exact pair-set equality: YES\nStudy 1 ADR text matches JSON: YES\nAPI calls made: 0')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Compilation stopped: {error}')
