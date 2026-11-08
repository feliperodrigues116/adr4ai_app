"""Read-only source validation followed by descriptive Claude support × human Q5 analysis."""
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE.parent / 'analysis'
sys.path.insert(0, str(ANALYSIS))
import analyze as a
p = a.p
QUESTIONS = ('Q1', 'Q2', 'Q3', 'Q4', 'Q5')


def load_spec():
    return p.strict_json((HERE / 'mapping_spec.json').read_text())


def parse_csv(text, selected, spec):
    """Fail closed before calculating results if any assigned rating/case is ambiguous."""
    table = list(csv.reader(io.StringIO(text, newline=''), delimiter=spec['delimiter'], strict=True))
    p.require(len(table) == spec['expected_response_rows'] + 1, 'Unexpected response row count')
    headers, *responses = table
    p.require(len(headers) == spec['expected_column_count'] and len(headers) == len(set(headers)), 'Wrong or duplicate columns')
    p.require(all(len(row) == len(headers) for row in responses), 'Ragged CSV')
    system_column = headers.index(spec['system_column'])
    columns = {}
    mapping = []
    for index, header in enumerate(headers):
        match = re.fullmatch(spec['case_column_regex'], header)
        if not match:
            p.require(not header.startswith('['), 'Malformed case column')
            mapping.append({'source_column': index + 1, 'source_header': header, 'column_kind': 'metadata',
                            'user_story_id': '', 'pattern_id': '', 'field': '', 'question_text': ''})
            continue
        story, pattern, field, question = match.groups()
        pair = story, pattern
        p.require(pair in selected, f'Unknown case in header: {pair}')
        key = pair + (field,)
        p.require(key not in columns, f'Duplicate case field: {key}')
        columns[key] = index
        mapping.append({'source_column': index + 1, 'source_header': header, 'column_kind': 'case',
                        'user_story_id': story, 'pattern_id': pattern, 'field': field, 'question_text': question})
    expected = {pair + (field,) for pair in selected for field in spec['case_fields']}
    p.require(len(selected) == spec['expected_case_count'] and set(columns) == expected, 'Incomplete case/question header mapping')
    system_rows = {}
    for number, response in enumerate(responses, 2):
        match = re.fullmatch(spec['system_value_regex'], response[system_column])
        p.require(match is not None, f'Unknown system in response row {number}')
        system = match[1]
        p.require(system in {pair[0][:5] for pair in selected} and system not in system_rows, 'Duplicate or foreign system response')
        system_rows[system] = number, response
        for key, index in columns.items():
            if key[0][:5] != system:
                p.require(response[index] == '', f'Unexpected cross-system response: row {number}, {key}')
    p.require(set(system_rows) == {pair[0][:5] for pair in selected}, 'Missing system response')
    cases, ratings = [], []
    for pair in sorted(selected):
        system = pair[0][:5]
        number, response = system_rows[system]
        case = {'user_story_id': pair[0], 'pattern_id': pair[1], 'system_id': system,
                'source_csv_record': number, 'source_system_value': response[system_column]}
        for question in QUESTIONS:
            index = columns[pair + (question,)]
            raw = response[index]
            p.require(raw in spec['rating_values'], f'Missing or invalid {question} at row {number}, case {pair}: {raw!r}')
            case[question] = int(raw)
            case[question + '_raw'] = raw
            case[question + '_source_column'] = index + 1
            ratings.append({'user_story_id': pair[0], 'pattern_id': pair[1], 'system_id': system,
                            'source_csv_record': number, 'source_column': index + 1, 'source_header': headers[index],
                            'question': question, 'raw_rating': raw, 'rating': int(raw)})
        index = columns[pair + ('COMMENT',)]
        case['comment_raw'] = response[index]
        case['comment_source_column'] = index + 1
        case['comment_has_nonwhitespace_text'] = bool(response[index].strip())
        cases.append(case)
    return cases, ratings, mapping


def validate_and_join():
    spec = load_spec()
    source = ROOT / spec['authoritative_source']
    p.require(p.file_hash(source) == spec['authoritative_source_sha256'], 'Authoritative CSV hash changed; explicit review required')
    support, origins, _ = a.validate_sources()
    # Validate the previous analysis, but never regenerate or modify it.
    previous = p.strict_json((ANALYSIS / 'analysis_provenance.json').read_text())
    for name, sha in previous['output_sha256'].items():
        p.require(p.file_hash(ANALYSIS / name) == sha, f'Previous analysis output changed: {name}')
    for name, sha in previous['source_sha256'].items():
        p.require(p.file_hash(ROOT / name) == sha, f'Previous analysis source changed: {name}')
    selected = {a.c.record_key(row): row for row in support if row['gpt_classification'] == 'applicable'}
    cases, ratings, mapping = parse_csv(source.read_bytes().decode(spec['encoding']), selected, spec)
    coding = {a.c.record_key(row): row for row in p.strict_json((ANALYSIS / 'applicable_partial_coding.json').read_text())}
    joined = []
    for case in cases:
        original = selected[a.c.record_key(case)]
        joined.append({**case, 'gpt_classification': original['gpt_classification'],
                       'claude_support_verdict': original['judgment']['verdict'],
                       'claude_rationale': original['judgment']['rationale'],
                       'claude_evidence_refs': original['judgment']['evidence_refs'],
                       'claude_identified_gaps': original['judgment']['identified_gaps'],
                       'support_record_origin': original['record_origin'],
                       'support_response_id': original['source_response_id'],
                       'support_source_record_sha256': original['source_record_sha256'],
                       'posthoc_qualitative_codes': coding.get(a.c.record_key(case), {}).get('codes', [])})
    p.require(len(joined) == len({a.c.record_key(row) for row in joined}) == 36, 'Join is incomplete or duplicated')
    p.require(all(row['support_record_origin'] == 'official_api_validated' for row in joined), 'Unexpected corrected selected case')
    return joined, ratings, mapping, spec


def matrix(cases, field=None):
    result = []
    groups = sorted({r[field] for r in cases}) if field else ['all']
    for group in groups:
        subset = [r for r in cases if field is None or r[field] == group]
        for verdict in a.VERDICTS:
            selected = [r for r in subset if r['claude_support_verdict'] == verdict]
            for score in range(1, 6):
                count = sum(r['Q5'] == score for r in selected)
                result.append({'group': group, 'claude_support_verdict': verdict, 'Q5': score, 'count': count,
                               'verdict_denominator': len(selected), 'within_verdict_percent': a.percentage(count, len(selected))})
    return result


def describe(cases, ratings):
    verdicts = {v: [r for r in cases if r['claude_support_verdict'] == v] for v in a.VERDICTS}
    return {'case_count': len(cases), 'rating_count_Q1_to_Q5': len(ratings),
            'Q5_distribution': {str(score): sum(r['Q5'] == score for r in cases) for score in range(1, 6)},
            'Q5_by_support': {v: {str(score): sum(r['Q5'] == score for r in rows) for score in range(1, 6)} for v, rows in verdicts.items()},
            'support_counts': {v: len(rows) for v, rows in verdicts.items()},
            'cases_per_system': dict(Counter(r['system_id'] for r in cases)),
            'comments_with_nonwhitespace_text': sum(r['comment_has_nonwhitespace_text'] for r in cases),
            'comments_nonempty_including_whitespace': sum(r['comment_raw'] != '' for r in cases),
            'supplementary_bands': {v: {'Q5_4_or_5': sum(r['Q5'] >= 4 for r in rows), 'Q5_3': sum(r['Q5'] == 3 for r in rows), 'Q5_1_or_2': sum(r['Q5'] <= 2 for r in rows)} for v, rows in verdicts.items()},
            'Q1_to_Q5_distributions': {q: {str(score): sum(r[q] == score for r in cases) for score in range(1, 6)} for q in QUESTIONS}}


def report(cases, stats, spec):
    table = a.md_table(['Claude support', 'N', 'Q5=1', 'Q5=2', 'Q5=3', 'Q5=4', 'Q5=5'], [[v, stats['support_counts'][v]] + [f'{stats["Q5_by_support"][v][str(s)]} ({100*stats["Q5_by_support"][v][str(s)]/stats["support_counts"][v]:.2f}%)' if stats['support_counts'][v] else '0 (not defined)' for s in range(1, 6)] for v in a.VERDICTS])
    partial = [r for r in cases if r['claude_support_verdict'] == 'partially_supported']
    partial_table = a.md_table(['Case', 'Human Q5', 'Existing post-hoc codes', 'Original general ADR comment'], [[r['user_story_id']+' × P'+r['pattern_id'], r['Q5'], ', '.join(r['posthoc_qualitative_codes']), r['comment_raw'] if r['comment_has_nonwhitespace_text'] else '(no substantive comment)'] for r in partial])
    systems = a.md_table(['System / one response row each', 'N', 'Q5=1', 'Q5=2', 'Q5=3', 'Q5=4', 'Q5=5'], [[system, len(subset)] + [sum(r['Q5'] == score for r in subset) for score in range(1, 6)] for system in sorted(stats['cases_per_system']) for subset in [[r for r in cases if r['system_id'] == system]]])
    return f'''# Claude support × human expert Q5 triangulation

## Source structure, mapping and validation gate

The sole authoritative source for human Q1–Q5 ratings and comments is `{spec['authoritative_source']}` (SHA-256 `{spec['authoritative_source_sha256']}`). It is read unchanged. The CSV is comma-delimited UTF-8, with **225 columns and four response rows**. Of these columns, **216** are 36 explicitly identified cases × five rating questions plus one optional comment; **nine** are metadata. The metadata include similar AI-experience headers differing by trailing whitespace, blank role fields, and `Column 223`. Their headers are preserved exactly and never used as rating substitutes.

`column_mapping.csv` records every source column (one-based), original full header, case identifiers, field and question text. Headers follow `[SYS01-US01|001|Q5] ...`; the story and zero-padded pattern ID are parsed directly, not inferred from position or text similarity. The system-selection column is `Qual sistema você avaliará?`. Its explicit SYS prefix links each response to the corresponding cases. Four rows cover SYS01/SYS02/SYS03/SYS04, respectively 7/12/8/9 cases. There is **one response per system, one Q5 rating per case**, with no multiple-rater aggregation or inferred participant identity. Source CSV record numbers (header = 1) identify rows reproducibly; these are not necessarily physical file lines if a comment contains newlines.

All **36 GPT-selected pairs match unambiguously**. All **180 required Q1–Q5 cells** are present with exact digit values 1–5; all 36 Q5 ratings are complete and unique. For each response, the other systems' question/comment cells are exactly empty, verified before analysis; those routing blanks are not missing assigned ratings. The 36 comments are retained exactly, including empty and whitespace-only values: {stats['comments_with_nonwhitespace_text']} contain non-whitespace text and {stats['comments_nonempty_including_whitespace']} are nonempty before whitespace inspection. Optional comment blanks are not imputed. No ratings are trimmed, fabricated, replaced or inferred.

The transformation is wide-to-long using explicit identifiers: `expert_ratings_long.csv` preserves all 180 raw ratings and question headers; `case_triangulation.csv` joins all 36 cases to their original Claude judgment, preserving rationale, references, gaps, record origin and response ID. `partial_support_cases.csv` isolates the 15 partial cases. `mapping_spec.json` specifies parsing, allowed values, routing rules, source hash and analysis conventions. Validation must finish successfully before any triangulation statistics are calculated or outputs written.

The existing consolidated 840-record validation is rerun read-only: scientific protocol v1.1/op1, 839 originals + one documented correction, source provenance, original GPT counts and exact scientific-text preservation. All 36 selected cases are originally API-validated judgments; the reference correction belongs to a not_applicable case and has no role in this 36-case join. Previous analysis source/output hashes are checked without regenerating prior files.

## Meaning of the measures

Q5 asks: “O padrão arquitetural utilizado como base para gerar este ADR é aplicável às necessidades expressas na história de usuário e em seus critérios de aceitação?” The form-generation code documents a 1–5 scale with endpoints **1 = Discordo totalmente**, **5 = Concordo totalmente**. Intermediate verbal anchors are not supplied in that code; numeric 2/3/4 are retained without inventing labels such as a formally defined neutral category.

Claude assessed the evidential support of the original GPT classification and rationale. Humans assessed applicability of the pattern used to generate an ADR, with requirements, pattern and ADR displayed by the form. These are related but different constructs and presentations. Their cross-tabulation is triangulation of perspectives, not a ground-truth agreement matrix. No accuracy, precision, recall, kappa, model-superiority claims, inferential tests or rescoring are made. Q1–Q4 are preserved in the case export and descriptively counted separately, but never substituted for Q5 or combined into a synthetic applicability score.

## Primary results: exact ordinal Q5 scores

Cell percentages use the Claude verdict row as denominator. The unsupported row has no observed cases and therefore undefined percentages, not 0% estimated support.

{table}

Overall Q5 distribution (1→5) is **{', '.join(str(stats['Q5_distribution'][str(s)]) for s in range(1,6))}**. The Claude selected-case distribution remains **21 supported, 15 partially_supported, zero unsupported**.

For an explicitly supplementary descriptive grouping, Q5 scores 4–5 occur in **{sum(r['Q5'] >= 4 for r in cases)}/36 cases ({100*sum(r['Q5'] >= 4 for r in cases)/36:.2f}%)**, score 3 in **{sum(r['Q5'] == 3 for r in cases)}/36**, and scores 1–2 in **{sum(r['Q5'] <= 2 for r in cases)}/36**. These bands are analyst choices, not a conversion to Claude verdicts or an assertion that all 4–5 scores are equivalent. Among supported cases, {stats['supplementary_bands']['supported']['Q5_4_or_5']}/21 have Q5 4–5; among partial cases, {stats['supplementary_bands']['partially_supported']['Q5_4_or_5']}/15 have Q5 4–5. Row-wise raw ratings remain the primary result.

### System and story context

{systems}

`by_system.csv` and `by_story.csv` give full support × exact-Q5 cross-tabulations, including empty verdict rows. Each system has only one response, so evaluator effects cannot be separated from system effects. The same catalog patterns recur across stories and decisions are clustered within respondents and systems; 36 case ratings are not 36 independent experts.

## Individual review of the 15 partially_supported cases

The codes below reproduce the previous analysis's explicitly post-hoc qualitative coding; they are interpretations of Claude's text, not human judgments or newly adjudicated defects. Existing code definitions and annotations remain unchanged and are hashed in provenance. Full unedited Claude texts, human Q1–Q5 and comments are in the case exports. Comments were invited about the ADR generally, not specifically Q5; no causal attribution of a rating is inferred from them.

{partial_table}

The {stats['supplementary_bands']['partially_supported']['Q5_4_or_5']} partial-support cases with Q5 4–5 show that a judge's qualification of evidential support can coexist with a higher human applicability rating. They do not demonstrate that the judge was wrong or that the expert endorsed every rationale or mechanism. The remaining partial cases' ratings similarly do not independently confirm each recorded gap.

Representative juxtaposition, with all original texts retained:

- **SYS02-US01 × P002:** Claude partially_supported, human Q5=5. The existing analysis identifies inference from task operations to composable pipeline stages; a high applicability rating does not resolve that justification-specific concern.
- **SYS01-US03 × P013:** partially_supported, Q5=5, no substantive comment. There is no human explanation for the difference in emphasis; none is invented.
- **SYS04-US03 × P001:** partially_supported, Q5=2. This is a lower applicability rating alongside qualified support, but the absence of a comment prevents assigning a shared reason.
- **SYS01-US02 × P003:** supported, Q5=3. The comment requests more technical depth; it concerns the ADR generally and cannot be assumed to explain Q5 specifically.
- **SYS04-US03 × P015:** supported, Q5=2. This is another indication that support and human applicability ratings should not be collapsed into the same construct; no substantive human comment supplies a reason.
- **SYS03-US02 × P050 and SYS03-US03 × P050:** Claude supported/partially_supported, human Q5=4/5 respectively. The previous analysis's question about a variable threshold for synchronous blocking remains a text-level observation; the human scores do not adjudicate it.

These are descriptive case selections spanning support verdicts and rating values, not additional architectural assessments. No missing explanations are supplied.

## Methodological qualifications

- This is a selected set of 36 GPT-applicable decisions used for ADR generation. It does not represent the other 804 classifications or allow an all-840 human validation claim.
- Four response rows, one per system, provide no within-case inter-rater reliability estimate; the file does not establish independent rater consensus or permit separation of system and respondent effects. Participant roles are blank in the supplied export; none are filled from assumptions.
- The original GPT classification/rationale is visible to Claude. Human form context includes the generated ADR and translated case materials. This is neither a blind replication nor an assessment with identical inputs or scales.
- Q5 is ordinal. Exact score distributions are reported; no interval-scale average, binary accuracy, or mapping from human scores to support verdicts is imposed. Supplementary bands are transparent descriptive summaries only.
- Existing qualitative codes are single-assistant post-hoc interpretations, not expert adjudication; comments are sparse and generally ADR-directed. Neither absent comments nor lower/higher numeric scores establish a reason or architectural correctness.
- Results characterize these recorded evaluations only. They neither revise GPT selections nor Claude judgments, nor establish model superiority or human ground truth. The prior blind experiment and RAG baseline are excluded.

## Reproduction and audit

```bash
python -B research_results/llm_judge_support_rq1/triangulation/triangulate.py
python -B -m unittest discover -s research_results/llm_judge_support_rq1/triangulation -p 'test_triangulation.py' -v
```

The tool is offline, requires no model credentials and only writes new derived files in this `triangulation/` directory. It pins the authoritative CSV hash, verifies complete mapping before calculating statistics, and verifies source hashes again before writing. Reruns require byte-identical outputs and refuse divergent overwrites. `provenance.json` records source, mapping, code/test and output hashes; `validation.json` documents coverage and exclusions. No original experimental records, CSV, previous support analyses or corrections are modified.
'''


def outputs(cases, ratings, mapping, spec):
    stats = describe(cases, ratings)
    case_fields = list(cases[0])
    result = {'statistics.json': a.json_text(stats), 'report.md': report(cases, stats, spec),
              'column_mapping.csv': a.csv_text(mapping, list(mapping[0])),
              'expert_ratings_long.csv': a.csv_text(ratings, list(ratings[0])),
              'case_triangulation.csv': a.csv_text(cases, case_fields),
              'partial_support_cases.csv': a.csv_text([r for r in cases if r['claude_support_verdict'] == 'partially_supported'], case_fields)}
    for filename, field in [('support_by_Q5.csv', None), ('by_system.csv', 'system_id'), ('by_story.csv', 'user_story_id')]:
        table = matrix(cases, field)
        result[filename] = a.csv_text(table, list(table[0]))
    qs = [{'question': q, 'rating': score, 'count': stats['Q1_to_Q5_distributions'][q][str(score)], 'denominator': 36} for q in QUESTIONS for score in range(1, 6)]
    result['Q1_to_Q5_distributions.csv'] = a.csv_text(qs, list(qs[0]))
    result['validation.json'] = a.json_text({'status': 'passed', 'authoritative_source_sha256': spec['authoritative_source_sha256'],
        'source_response_rows': 4, 'source_columns': 225, 'case_columns': 216, 'metadata_columns': 9,
        'matched_unique_selected_cases': len(cases), 'required_Q1_to_Q5_ratings': len(ratings), 'complete_Q5_cases': 36,
        'ratings_imputed_or_substituted': 0, 'ambiguous_matches': 0, 'outside_system_case_blocks_verified_blank': 108,
        'optional_comments_preserved_including_whitespace': True, 'all_selected_support_records_are_original_validated': True,
        'scientific_protocol_id': p.PROTOCOL_ID, 'operational_policy_id': a.c.op.POLICY['policy_id'],
        'previous_840_record_consolidation_and_analysis_provenance': 'verified read-only',
        'mapping_validated_before_statistics': True})
    return result


def snapshot():
    spec = load_spec()
    names = set(a.source_snapshot())
    names.add(spec['authoritative_source'])
    names.add(spec['scale']['source'])
    names.update(str(path.relative_to(ROOT)) for path in ANALYSIS.iterdir() if path.is_file())
    names.update(str((HERE / name).relative_to(ROOT)) for name in ('mapping_spec.json', 'triangulate.py', 'test_triangulation.py'))
    return {name: p.file_hash(ROOT / name) for name in sorted(names)}


def main():
    before = snapshot()
    cases, ratings, mapping, spec = validate_and_join()
    result = outputs(cases, ratings, mapping, spec)
    p.require(before == snapshot(), 'Sources changed during triangulation')
    provenance = {'input_source_sha256': before,
                  'output_sha256': {name: __import__('hashlib').sha256(value.encode()).hexdigest() for name, value in sorted(result.items())},
                  'authority': spec['authoritative_source'], 'scientific_protocol_id': p.PROTOCOL_ID,
                  'operational_policy_id': a.c.op.POLICY['policy_id'],
                  'method': 'Descriptive ordinal Q5 triangulation after complete exact-ID join; offline; deterministic'}
    result['provenance.json'] = a.json_text(provenance)
    for name, value in result.items():
        path = HERE / name
        p.require(not path.exists() or path.read_bytes() == value.encode(), f'Refusing divergent overwrite: {path}')
    for name, value in result.items():
        a.c.write_identical_or_new(HERE / name, value)
    print(f'Validated {len(cases)} exact case matches, {len(ratings)} Q1–Q5 ratings; wrote {len(result)} reproducible outputs.')
    print(a.json_text(describe(cases, ratings)))


if __name__ == '__main__':
    main()
