"""Compile reviewed evaluation mappings locally; standard library only, zero API calls."""

import csv
import io
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
FIELDS = ('pattern_name', 'pattern_motivation', 'pattern_solution',
          'pattern_consequences', 'adr_title', 'adr_status', 'adr_context',
          'adr_decision', 'adr_consequences')
REQUIREMENTS = ('system_purpose', 'user_story', 'acceptance_criteria')
MAPPING_COLUMNS = ('system_id', 'user_story_id', 'pattern_id', 'field',
                   'original_text', 'evaluation_text_pt', 'translation_action')
AUDIT_COLUMNS = (*MAPPING_COLUMNS, 'translation_candidate_pt',
                 'manual_correction_authorized', 'manual_correction_from',
                 'manual_correction_to')
CORRECTION_COLUMNS = ('system_id', 'user_story_id', 'pattern_id', 'field',
                      'translation_candidate_pt', 'evaluation_text_pt',
                      'replace_from', 'replace_to', 'authorization_ref')
APPROVED_CORRECTIONS = {
    **{('SYS03-US02', '014', field): ('Commercial', 'Comercial')
       for field in ('adr_title', 'adr_context', 'adr_decision', 'adr_consequences')},
    ('SYS04-US03', '014', 'pattern_motivation'): ('Machine Learning', 'aprendizado de máquina'),
}
CASE_COLUMNS = ('system_id', 'user_story_id', *REQUIREMENTS, 'pattern_id',
                *(f + '_pt' for f in FIELDS))
ACTIONS = {'portuguese': 'preserved_portuguese',
           'non_portuguese': 'translated_non_portuguese',
           'mixed_portuguese_non_portuguese': 'partially_translated_mixed',
           'empty': 'preserved_empty'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pair(row):
    return row['user_story_id'], row['pattern_id']


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        require(columns and len(set(columns)) == len(columns), f'{path}: invalid header')
        rows = list(reader)
    require(all(None not in r and all(v is not None for v in r.values()) for r in rows),
            f'{path}: malformed CSV')
    return columns, rows


def validate_source(path=HERE / 'adr_generation_results.csv'):
    columns, rows = read_csv(path)
    require(set(('system_id', 'user_story_id', 'pattern_id', *REQUIREMENTS, *FIELDS))
            <= set(columns), 'Missing scientific source columns')
    require(len(rows) == 36, 'Expected exactly 36 scientific source rows')
    require(len({pair(r) for r in rows}) == 36, 'Duplicate scientific source pairs')
    require(all(r['user_story_id'].strip() and r['pattern_id'].strip() for r in rows),
            'Missing source identifiers')
    require(all(r['adr_status'] == 'Proposed' for r in rows), 'Invalid scientific ADR status')
    require(all(r[f].strip() for r in rows for f in FIELDS if f.startswith('adr_')),
            'Missing scientific ADR content')
    return rows


def load_inventory(rows):
    """Use Phase 1 only for language labels, never as a scientific text source."""
    _, inventory = read_csv(HERE / 'expert_evaluation_language_classification.csv')
    expected = {( *pair(r), f): r for r in rows for f in FIELDS}
    require(len(inventory) == 324, 'Expected 324 language labels')
    labels = {}
    for item in inventory:
        key = (*pair(item), item['field'])
        require(key in expected and key not in labels, f'Unexpected/duplicate language label: {key}')
        source = expected[key]
        require(item['system_id'] == source['system_id']
                and item['original_text'] == source[item['field']], f'Stale language label: {key}')
        label = item['language_classification']
        require(label in ACTIONS, f'Invalid language label: {key}')
        require((label == 'empty') == (source[item['field']] == ''), f'Empty label mismatch: {key}')
        labels[key] = label
    require(set(labels) == set(expected), 'Missing language labels')
    require({label: list(labels.values()).count(label) for label in ACTIONS}
            == {'portuguese': 12, 'non_portuguese': 289,
                'mixed_portuguese_non_portuguese': 14, 'empty': 9}, 'Phase 1 counts changed')
    return labels


def portuguese_spans(row, field):
    """Explicitly reviewed Portuguese boundaries for the fourteen mixed fields."""
    text = row[field]
    key = (*pair(row), field)
    if key == ('SYS03-US02', '001', 'adr_decision'):
        require(text.startswith('We will submeter '), 'Mixed decision prefix changed')
        return [(len('We will '), len(text))]
    if key == ('SYS04-US02', '003', 'adr_decision'):
        start = text.index('O simulador disponibilizará')
        return [(start, len(text))]
    token = 'PENDENTE DE EXECUÇÃO' if 'PENDENTE DE EXECUÇÃO' in text else 'improcedente'
    require(token in text, f'Unrecognized mixed-language field: {key}')
    spans = []
    start = 0
    while (index := text.find(token, start)) != -1:
        spans.append((index, index + len(token)))
        start = index + len(token)
    return spans


def validate_mapping(rows, mappings, labels):
    expected = {(*pair(r), f): r for r in rows for f in FIELDS}
    require(len(mappings) == 324, 'Expected 324 translation mappings')
    indexed = {}
    for item in mappings:
        require(set(item) == set(MAPPING_COLUMNS), 'Invalid mapping columns')
        key = (*pair(item), item['field'])
        require(key in expected and key not in indexed, f'Unexpected/duplicate mapping: {key}')
        source = expected[key]
        field = item['field']
        original, translated = source[field], item['evaluation_text_pt']
        require(item['system_id'] == source['system_id'] and item['original_text'] == original,
                f'Mapping identifiers/source text changed: {key}')
        action = ACTIONS[labels[key]]
        require(item['translation_action'] == action, f'Incorrect action: {key}')
        if action in ('preserved_portuguese', 'preserved_empty'):
            require(translated == original, f'Preserved source content changed: {key}')
        else:
            require(translated.strip(), f'Empty translation: {key}')
        if field == 'adr_status':
            require(translated == 'Proposto', f'Incorrect evaluation status: {key}')
        if action == 'partially_translated_mixed':
            cursor = 0
            for start, end in portuguese_spans(source, field):
                portion = original[start:end]
                index = translated.find(portion, cursor)
                require(index != -1, f'Portuguese portion changed: {key}')
                cursor = index + len(portion)
        require('[[PT_KEEP_' not in translated, f'Unresolved translation placeholder: {key}')
        indexed[key] = item
    require(set(indexed) == set(expected), 'Missing translation mappings')
    return indexed


def encode_csv(columns, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def atomic_write(path, content):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_review_provenance(rows, mappings, labels):
    """Validate that final values differ from immutable candidates only as approved."""
    _, candidate_rows = read_csv(HERE / 'expert_evaluation_translation_run/translations_candidate.csv')
    candidates = validate_mapping(rows, candidate_rows, labels)
    final = validate_mapping(rows, mappings, labels)
    columns, corrections = read_csv(HERE / 'expert_evaluation_manual_corrections.csv')
    require(tuple(columns) == CORRECTION_COLUMNS, 'Invalid manual correction columns')
    require(len(corrections) == 5, 'Expected five authorized field corrections')
    reviewed = {}
    for correction in corrections:
        key = (*pair(correction), correction['field'])
        require(key in APPROVED_CORRECTIONS and key not in reviewed,
                f'Unexpected/duplicate manual correction: {key}')
        old, new = APPROVED_CORRECTIONS[key]
        candidate = candidates[key]['evaluation_text_pt']
        require(old in candidate, f'Approved residual text missing: {key}')
        require(correction['system_id'] == final[key]['system_id']
                and correction['translation_candidate_pt'] == candidate
                and correction['evaluation_text_pt'] == candidate.replace(old, new)
                and correction['replace_from'] == old and correction['replace_to'] == new,
                f'Manual correction differs from authorization: {key}')
        require(correction['authorization_ref'] ==
                'expert_evaluation_translation_run/manual_authorization.txt'
                and (HERE / correction['authorization_ref']).is_file(),
                f'Missing manual authorization record: {key}')
        reviewed[key] = correction
    require(set(reviewed) == set(APPROVED_CORRECTIONS), 'Missing authorized corrections')
    provenance = {}
    for key, item in final.items():
        candidate = candidates[key]
        require(all(item[f] == candidate[f] for f in MAPPING_COLUMNS if f != 'evaluation_text_pt'),
                f'Candidate identifiers/source/action changed: {key}')
        expected = (reviewed[key]['evaluation_text_pt'] if key in reviewed
                    else candidate['evaluation_text_pt'])
        require(item['evaluation_text_pt'] == expected, f'Unapproved presentation change: {key}')
        provenance[key] = {
            'translation_candidate_pt': candidate['evaluation_text_pt'],
            'manual_correction_authorized': 'yes' if key in reviewed else 'no',
            'manual_correction_from': reviewed[key]['replace_from'] if key in reviewed else '',
            'manual_correction_to': reviewed[key]['replace_to'] if key in reviewed else '',
        }
    return provenance


def compile_data(rows, mappings, labels, provenance):
    indexed = validate_mapping(rows, mappings, labels)
    cases, audit = [], []
    for source in rows:
        case = {f: source[f] for f in ('system_id', 'user_story_id', *REQUIREMENTS, 'pattern_id')}
        for field in FIELDS:
            item = indexed[(*pair(source), field)]
            case[field + '_pt'] = item['evaluation_text_pt']
            audit.append({**item, **provenance[(*pair(source), field)]})
        cases.append(case)
    require(len(cases) == len({pair(r) for r in cases}) == 36, 'Invalid evaluation pair count')
    require({pair(r) for r in cases} == {pair(r) for r in rows}, 'Evaluation pair-set mismatch')
    sources = {pair(r): r for r in rows}
    require(all(r[f] == sources[pair(r)][f] for r in cases for f in REQUIREMENTS),
            'Requirement field changed')
    return encode_csv(CASE_COLUMNS, cases), encode_csv(AUDIT_COLUMNS, audit)


def main():
    rows = validate_source()
    labels = load_inventory(rows)
    columns, mappings = read_csv(HERE / 'expert_evaluation_translations_pt.csv')
    require(tuple(columns) == MAPPING_COLUMNS, 'Incorrect mapping column order')
    provenance = load_review_provenance(rows, mappings, labels)
    cases, audit = compile_data(rows, mappings, labels, provenance)
    # All input/data validations complete before either final output is written.
    atomic_write(HERE / 'expert_evaluation_cases_pt.csv', cases)
    atomic_write(HERE / 'expert_evaluation_translation_audit.csv', audit)
    print('Validated: 36 cases, 324 mappings, exact pair equality; compiler API calls: 0.')


if __name__ == '__main__':
    main()
