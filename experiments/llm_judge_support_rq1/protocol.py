"""Fixed response-conditioned RQ1 protocol. No clients or previous judge outcomes."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = ROOT / 'experiments/pattern_selection'
sys.path.insert(0, str(ORIGINAL))
from prepare_data import load_patterns, load_requirement_cases
from assess_pattern import build_prompt as original_prompt, validate_assessment

MODEL = 'claude-sonnet-5-5'
PROTOCOL_VERSION = 'v1.1'
PROTOCOL_ID = f'adr4ai-rq1-response-conditioned-support-{PROTOCOL_VERSION}'
EFFORT = 'high'
SDK_VERSION = '1.17.0'
DEFAULT_MAX_TOKENS = 32768
DEFAULT_TIMEOUT = 600
MAX_ATTEMPTS_PER_PAIR = 3
CLASSIFICATIONS = ('applicable', 'not_applicable', 'insufficient_information')
EXPECTED_COUNTS = {'applicable': 36, 'not_applicable': 31, 'insufficient_information': 773}
PATTERN_FIELDS = ('id', 'name', 'motivation', 'solution', 'consequences')
GPT_PATH = ORIGINAL / 'outputs/assessments.jsonl'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, f'Duplicate JSON field: {key}')
        result[key] = value
    return result


def strict_json(text):
    def reject_constant(value):
        raise ValueError(f'Invalid JSON constant: {value}')
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def read_rows(path, optional=False):
    if optional and not path.exists():
        return []
    raw = path.read_bytes()
    require(not raw or raw.endswith(b'\n'), f'Truncated journal: {path}; inspect manually before resumption')
    result = []
    for number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
        try:
            row = strict_json(line)
            require(isinstance(row, dict), 'Expected JSON object')
            result.append(row)
        except ValueError as error:
            raise ValueError(f'{path}:{number}: {error}') from error
    return result


INSTRUCTIONS = (HERE / 'instructions.txt').read_text(encoding='utf-8')
SCHEMA = strict_json((HERE / 'response_schema.json').read_text(encoding='utf-8'))
VERDICTS = ('supported', 'partially_supported', 'unsupported')


def validate_schema():
    require(SCHEMA == {
        'type': 'object',
        'properties': {
            'verdict': {'type': 'string', 'enum': list(VERDICTS)},
            'evidence_refs': {'type': 'array', 'items': {'type': 'string'}},
            'rationale': {'type': 'string'},
            'identified_gaps': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['verdict', 'evidence_refs', 'rationale', 'identified_gaps'],
        'additionalProperties': False,
    }, 'Support response schema is not the specified strict four-field schema')
    require(bool(INSTRUCTIONS.strip()), 'Empty support instructions')


def validate_judgment(judgment, case):
    require(isinstance(judgment, dict) and set(judgment) == set(SCHEMA['required']),
            'Judgment must contain exactly verdict, evidence_refs, rationale, identified_gaps')
    require(isinstance(judgment['verdict'], str) and judgment['verdict'] in VERDICTS,
            'Invalid support verdict')
    for field in ('evidence_refs', 'identified_gaps'):
        require(isinstance(judgment[field], list) and all(isinstance(x, str) for x in judgment[field]),
                f'{field} must be an array of strings')
    valid_refs = {case['user_story_id']} | {c['acceptance_criterion_id'] for c in case['acceptance_criteria']}
    require(all(ref in valid_refs for ref in judgment['evidence_refs']), 'Unknown or foreign evidence reference')
    require(isinstance(judgment['rationale'], str) and bool(judgment['rationale'].strip()),
            'Rationale must be a nonempty explanation')
    # No verdict-dependent references or gaps are invented or structurally forced.


def source_paths():
    return [ROOT / 'data/user_histories_orig.csv', *sorted((ROOT / 'catalogs/patterns').glob('P*.json')),
            GPT_PATH, ORIGINAL / 'prepare_data.py', ORIGINAL / 'assess_pattern.py']


def verify_sources():
    baseline = strict_json((HERE / 'source_baseline.json').read_text(encoding='utf-8'))
    actual = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in source_paths()}
    require(actual == baseline['file_sha256'], 'Original source inventory/hash mismatch; no source files may be repaired or rewritten')
    return actual


def load_items():
    validate_schema()
    verify_sources()
    cases = load_requirement_cases(ROOT / 'data/user_histories_orig.csv')
    patterns = load_patterns(ROOT / 'catalogs/patterns')
    require({p['id'] for p in patterns} == {f'{i:03d}' for i in range(1, 71)}, 'Expected pattern IDs 001–070')
    patterns = sorted(patterns, key=lambda p: p['id'])
    cases = sorted(cases, key=lambda c: c['user_story_id'])
    expected = {(c['user_story_id'], p['id']) for c in cases for p in patterns}
    assessments = read_rows(GPT_PATH)
    require(len(assessments) == 840, 'Expected 840 original GPT assessments')
    by_pair = {}
    cases_by_id = {c['user_story_id']: c for c in cases}
    for assessment in assessments:
        key = assessment.get('user_story_id'), assessment.get('pattern_id')
        require(all(isinstance(x, str) for x in key), 'GPT identifiers must be strings')
        require(key in expected and key not in by_pair, f'Unknown or duplicate GPT pair: {key}')
        require(set(assessment) == {'user_story_id', 'pattern_id', 'model', 'reasoning_effort',
                                    'classification', 'requirement_refs', 'rationale'}, 'Unexpected GPT record fields')
        validate_assessment({k: assessment[k] for k in ('classification', 'requirement_refs', 'rationale')}, cases_by_id[key[0]])
        require(assessment['model'] == 'gpt-6-sol' and assessment['reasoning_effort'] == 'high',
                'Original GPT model/effort mismatch')
        by_pair[key] = assessment
    require(set(by_pair) == expected and len(expected) == 840, 'Incomplete 12 × 70 pair coverage')
    require(dict(Counter(a['classification'] for a in assessments)) == EXPECTED_COUNTS,
            'Original GPT category counts differ from 36 / 31 / 773')
    items = []
    for case in cases:
        for pattern in patterns:
            original_prompt(case, pattern)  # Original validation of all five fields.
            item = {'case': case, 'pattern': {k: pattern[k] for k in PATTERN_FIELDS},
                    'gpt_assessment': by_pair[case['user_story_id'], pattern['id']]}
            build_prompt(item)
            items.append(item)
    return items


def key(item):
    return item['case']['user_story_id'], item['pattern']['id']


def build_prompt(item):
    assessment = item['gpt_assessment']
    require((assessment['user_story_id'], assessment['pattern_id']) == key(item), 'GPT assessment association mismatch')
    return (original_prompt(item['case'], item['pattern']) + '\n\nORIGINAL GPT ASSESSMENT\n\n'
            + 'Classification:\n' + assessment['classification']
            + '\n\nRequirement references:\n' + json.dumps(assessment['requirement_refs'], ensure_ascii=False)
            + '\n\nRationale:\n' + assessment['rationale'])


def pilot_items(items):
    # Input order is lexicographic story ID, then three-digit pattern ID.
    return [next(item for item in items if item['gpt_assessment']['classification'] == category)
            for category in CLASSIFICATIONS]


def request_config(max_tokens=DEFAULT_MAX_TOKENS):
    return {'model': MODEL, 'max_tokens': max_tokens, 'system': INSTRUCTIONS,
            'thinking': {'type': 'adaptive'},
            'output_config': {'effort': EFFORT, 'format': {'type': 'json_schema', 'schema': SCHEMA}}}
