"""Offline descriptive analysis; reads frozen sources and writes only this analysis directory."""
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(PARENT))
import consolidate as c
p = c.p
CLASSES = ('applicable', 'not_applicable', 'insufficient_information')
VERDICTS = ('supported', 'partially_supported', 'unsupported')


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def csv_text(rows, fields):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], (list, dict)) else row[k] for k in fields})
    return out.getvalue()


def percentage(n, total):
    return round(100 * n / total, 6) if total else None


def validate_sources():
    provenance = p.strict_json((PARENT / 'analysis_provenance.json').read_text())
    for name, sha in provenance['input_source_sha256'].items():
        p.require(p.file_hash(ROOT / name) == sha, f'Frozen input changed: {name}')
    for name, sha in provenance['output_sha256'].items():
        p.require(p.file_hash(PARENT / name) == sha, f'Consolidated output changed: {name}')
    p.require(provenance['scientific_protocol_id'] == p.PROTOCOL_ID, 'Protocol ID mismatch')
    p.require(provenance['operational_policy_id'] == c.op.POLICY['policy_id'], 'Operational amendment mismatch')
    p.require(provenance['instructions_sha256'] == p.digest(p.INSTRUCTIONS), 'Instructions changed')
    p.require(provenance['schema_sha256'] == p.digest(p.SCHEMA), 'Schema changed')
    expected, items, done, corrected, _ = c.prepare_records()
    rows = p.read_rows(PARENT / 'analytical_judgments.jsonl')
    origins = c.validate_analytical(rows, items, done, corrected)
    p.require(rows == expected, 'Consolidated records differ from exact source reconstruction')
    counts = Counter(r['gpt_classification'] for r in rows)
    p.require(counts == {'applicable': 36, 'not_applicable': 31, 'insufficient_information': 773}, 'GPT marginal counts changed')
    stories = {r['user_story_id'] for r in rows}
    patterns = {r['pattern_id'] for r in rows}
    p.require(len(stories) == 12 and len(patterns) == 70 and len({r['system'] for r in rows}) == 4, 'Coverage dimensions changed')
    p.require({c.record_key(r) for r in rows} == {(s, pat) for s in stories for pat in patterns}, 'Incomplete Cartesian coverage')
    return rows, origins, provenance


def validate_coding(rows, annotations, book):
    target = {c.record_key(r): r for r in rows if r['gpt_classification'] == 'applicable' and r['judgment']['verdict'] == 'partially_supported'}
    p.require(len(annotations) == len(target) == 15, 'All 15 applicable partial decisions must be coded')
    seen = set()
    for a in annotations:
        key = c.record_key(a)
        p.require(key in target and key not in seen, 'Duplicate or foreign qualitative annotation')
        seen.add(key)
        p.require(a['recorded_verdict'] == target[key]['judgment']['verdict'], 'Annotation changes recorded verdict')
        p.require(a['codes'] and len(a['codes']) == len(set(a['codes'])) and set(a['codes']) <= set(book['qualitative_codes']), 'Unknown or duplicate code')
        gaps = target[key]['judgment']['identified_gaps']
        p.require(a['evidence'] == [{'field': f'identified_gaps[{i}]', 'quote': gap} for i, gap in enumerate(gaps)], 'Qualitative evidence must preserve all original gaps verbatim')
    return True


def breakdown(rows, field=None):
    groups = sorted({r[field] for r in rows}) if field else ['all']
    result = []
    for group in groups:
        subset = [r for r in rows if field is None or r[field] == group]
        for classification in ('all',) + CLASSES:
            selected = [r for r in subset if classification == 'all' or r['gpt_classification'] == classification]
            counts = Counter(r['judgment']['verdict'] for r in selected)
            for verdict in VERDICTS:
                result.append({'group': group, 'gpt_classification': classification, 'verdict': verdict,
                               'count': counts[verdict], 'denominator': len(selected),
                               'within_category_percent': percentage(counts[verdict], len(selected))})
    return result


def text_matches(row, book):
    matches = []
    for code, rule in book['text_signals'].items():
        for field in rule['fields']:
            values = [(field, row['judgment'][field])] if field == 'rationale' else [(f'identified_gaps[{i}]', gap) for i, gap in enumerate(row['judgment'][field])]
            for locator, value in values:
                if re.search(rule['regex'], value, re.IGNORECASE):
                    matches.append({'user_story_id': row['user_story_id'], 'pattern_id': row['pattern_id'],
                                    'verdict': row['judgment']['verdict'], 'signal': code,
                                    'field': locator, 'verbatim_text': value})
    return matches


def flattened(row):
    fields = ('user_story_id', 'pattern_id', 'system', 'gpt_classification', 'record_origin', 'source_response_id', 'source_attempt_id', 'source_file', 'source_line', 'source_record_sha256')
    return {**{f: row[f] for f in fields}, **row['judgment']}


CASE_FIELDS = ['user_story_id', 'pattern_id', 'system', 'gpt_classification', 'verdict', 'rationale', 'evidence_refs', 'identified_gaps', 'record_origin', 'source_response_id', 'source_attempt_id', 'source_file', 'source_line', 'source_record_sha256']
SUMMARY_FIELDS = ['group', 'gpt_classification', 'verdict', 'count', 'denominator', 'within_category_percent']


def md_table(headers, rows):
    def escape(x):
        return str(x).replace('|', '\\|').replace('\n', '<br>')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] + ['| ' + ' | '.join(escape(x) for x in row) + ' |' for row in rows])


def summarize(rows, annotations, book):
    validate_coding(rows, annotations, book)
    insuff = [r for r in rows if r['gpt_classification'] == 'insufficient_information' and r['judgment']['verdict'] != 'supported']
    matches = [match for row in insuff for match in text_matches(row, book)]
    signals = defaultdict(set)
    for m in matches:
        signals[m['signal']].add(c.record_key(m))
    code_counts = Counter(code for a in annotations for code in a['codes'])
    stats = {'expected_pairs': 840, 'analytical_pairs': len(rows), 'origins': dict(Counter(r['record_origin'] for r in rows)),
             'gpt_classifications': dict(Counter(r['gpt_classification'] for r in rows)),
             'support_verdicts': dict(Counter(r['judgment']['verdict'] for r in rows)),
             'applicable_verdicts': dict(Counter(r['judgment']['verdict'] for r in rows if r['gpt_classification'] == 'applicable')),
             'qualitative_code_counts': dict(sorted(code_counts.items())),
             'insufficient_nonsupported_denominator': len(insuff),
             'text_signal_unique_case_counts': {code: len(signals[code]) for code in book['text_signals']},
             'boundary_gap_and_no_incompatibility_signal_intersection': len(signals['I2'] & signals['I3']),
             'scientific_protocol_id': p.PROTOCOL_ID, 'operational_policy_id': c.op.POLICY['policy_id'],
             'metrics_are_descriptive_support_not_ground_truth_performance': True}
    return stats, insuff, matches, signals


def report(rows, annotations, book, stats):
    def matrix(subset):
        return md_table(['GPT classification', 'N', 'Supported', 'Partially supported', 'Unsupported'], [
            [label, len(selected)] + [f'{sum(r["judgment"]["verdict"] == v for r in selected)} ({100*sum(r["judgment"]["verdict"] == v for r in selected)/len(selected):.2f}%)' for v in VERDICTS]
            for label in CLASSES for selected in [[r for r in subset if r['gpt_classification'] == label]] if selected])
    app = [r for r in rows if r['gpt_classification'] == 'applicable']
    def group_table(field, subset):
        return md_table([field, 'N', *VERDICTS], [[g, len(s)] + [f'{sum(r["judgment"]["verdict"] == v for r in s)} ({100*sum(r["judgment"]["verdict"] == v for r in s)/len(s):.2f}%)' for v in VERDICTS] for g in sorted({r[field] for r in subset}) for s in [[r for r in subset if r[field] == g]]])
    code_table = md_table(['Code', 'Interpretation', 'Cases / 15', 'Representative case'], [[code, detail['label'], stats['qualitative_code_counts'].get(code, 0), next((a['user_story_id'] + ' × P' + a['pattern_id'] for a in annotations if code in a['codes']), '')] for code, detail in book['qualitative_codes'].items()])
    individual = md_table(['Case', 'Codes', 'Post-hoc interpretation (not a new verdict)'], [[a['user_story_id'] + ' × P' + a['pattern_id'], ', '.join(a['codes']), a['analyst_note']] for a in annotations])
    signal_table = md_table(['Signal', 'Rule-based observation', 'Cases / 428', '% of 428'], [[code, rule['label'], stats['text_signal_unique_case_counts'][code], f'{100*stats["text_signal_unique_case_counts"][code]/428:.2f}%'] for code, rule in book['text_signals'].items()])
    origin_table = md_table(['Subset', 'N', *VERDICTS], [[label, len(s)] + [sum(r['judgment']['verdict'] == v for r in s) for v in VERDICTS] for label in ('official_api_validated', 'technically_corrected_analytical') for s in [[r for r in rows if r['record_origin'] == label]]])
    return f'''# ADR4AI RQ1: response-conditioned support evaluation

## Scope and source validation

This is a descriptive analysis of Claude's recorded support for original GPT classifications, conditioned on the GPT decision and rationale. Support for a decision is distinct from architectural correctness and from human expert evaluation. No blind Claude results or architects' Q5 scores enter this analysis. No new model calls or expert adjudications were made.

The frozen consolidated records pass exact source reconstruction, the unchanged original support JSON/schema and case-reference validator, and source/manifest/correction hash checks: **840 unique pairs**, the full Cartesian product of 12 stories and 70 patterns across four systems. GPT marginal counts are **36 applicable, 31 not_applicable, 773 insufficient_information**. Scientific protocol is `{p.PROTOCOL_ID}` (v1.1); operational amendment is `{c.op.POLICY['policy_id']}` (op1). Source identifiers and hashes are recorded in `analysis_provenance.json` and `validation.json`.

There are **839 originally API-validated judgments and one technically corrected analytical record**, SYS02-US01 × P051. The official records still contain 839 validated judgments. The existing approved correction replaces only `SYS02-US01-US01` with `SYS02-US01` in the earliest failed response's evidence references. Original verdict (`supported`), rationale, and identified gaps are unchanged; the second failed response and its different rationale remain preserved. All 839 original judgments match their preserved source records exactly. This analysis does not modify the correction or relabel it as originally validated.

{origin_table}

Excluding the correction yields 395 supported, 443 partially_supported, and one unsupported judgment (839). The correction affects only the not_applicable row (29/1/0 becomes 30/1/0), and none of the 36 applicable decisions.

## Descriptive support matrix

Percentages use the original GPT category as denominator; totals are counts of pair-level decisions, not distinct catalog patterns.

{matrix(rows)}

Overall: **396 supported (47.14%), 443 partially_supported (52.74%), one unsupported (0.12%)**. These are support-verdict frequencies, not agreement, accuracy, precision, recall, or evidence of model superiority. The highly unequal GPT category sizes mean the overall distribution mostly reflects insufficient_information decisions.

### By system (all classifications)

{group_table('system', rows)}

### By user story (all classifications)

{group_table('user_story_id', rows)}

`by_system.csv` and `by_story.csv` additionally cross each group with all three GPT categories, including zero-denominator categories (blank percentage). Counts and six-decimal percentages are recalculated directly; display percentages are rounded to two decimals.

## The 36 GPT-applicable decisions used for ADR generation

Of the 36 decisions, **21 (58.33%) are supported, 15 (41.67%) partially_supported, and none unsupported**. All 36 are original validated records. These are 36 story–pattern selections; the same catalog pattern can recur across stories. This evaluates the evidential support of the selections, not the quality or correctness of the generated ADRs.

{group_table('system', app)}

The complete case table `applicable_decisions.csv` retains every original rationale, evidence-reference array and identified-gap array verbatim, with origin and source identifiers. CSV array cells contain JSON; pattern identifiers are zero-padded strings.

### Transparent qualitative procedure

All 15 applicable partially_supported judgments were read individually. `applicable_partial_coding.json` contains assistant-authored, post-hoc, multi-label annotations, full verbatim gap quotes, and case-specific notes. `codebook.json` defines the codes. The analysis is descriptive coding of the judge's explanations, not an independent architecture assessment; there is one coder, no preregistration and no inter-coder reliability estimate. Code frequencies overlap and must not be summed as distinct decisions. Exact quote and case coverage checks run offline. No recorded verdict is changed.

{code_table}

{individual}

The recurring substantive claim is that a functional goal, quality constraint, or adjacent concern does not sufficiently establish the particular pattern mechanism. Pipes and Filters cases distinguish task variety from composable stages; safeguard/control cases distinguish output correctness, provenance or isolation from rule-based gating. Other cases question translation from ML-specific language, workflow transformation, interaction contracts, or omitted evidence mappings. These are **claimed evidential concerns recorded by the judge**, not verified architectural defects. Requiring an explicit implementation of every pattern mechanism, rather than positive evidence of its architectural need, would exceed an applicability assessment; the recorded language sometimes approaches that stricter standard.

Seven of the 15 rationales also invoke alternative designs or whether a mechanism is necessary (A7). A single routine, a single model, or asynchronous interaction may be viable alternatives without undermining another defensible selection. These seven also contain specific claimed mapping limitations; they are not coded as general uncertainty alone. Likewise, domain transfer, missing literal terminology, or failure to cite every criterion does not by itself invalidate applicability. None of these interpretations reassigns the judge's verdict.

### Representative cases

- **Supported, SYS01-US01 × P001:** the recorded rationale ties document-grounded answering and refusal outside the source context to safeguard intent. This is an example of the judge accepting a positive requirement-to-intent link.
- **Supported, SYS03-US02 × P050:** downstream status change and scheduling depend on the AI ownership confirmation. The judge accepts this as a defensible blocker motivation despite no explicit waiting requirement and acknowledges alternatives.
- **Partially supported, SYS03-US03 × P050:** conditional closure after a negative ownership result is accepted as a meaningful basis, but missing explicit synchronous waiting and the availability of asynchronous designs limit support. Juxtaposition with the preceding case illustrates a potentially variable evidential threshold, not proof that either judgment is incorrect.
- **Partially supported, SYS02-US02 × P070:** the judge accepts task/input variation as a basis but questions the inference to multiple selectable models. The reference to a single-model alternative must be distinguished from the more specific claimed requirement-to-mechanism gap.
- **Partially supported, SYS04-US02 × P028:** the judge accepts integration-testing intent but questions the transfer from ML release testing to simulator testability. This is a recorded scope/domain distinction, not a finding that patterns cannot transfer across domains.
- **Supported, SYS04-US03 × P043:** the recorded rationale accepts comparing interchangeable models against the same simulation scenario as support for Strategy intent.

Full unedited texts for these examples and the remaining-classification examples are exported in `representative_cases.csv`.

## The 31 not_applicable decisions

**30 (96.77%) are supported; one (3.23%) is partially_supported; none unsupported.** The only partial case, SYS04-US03 × P034 (Dogfooding), contrasts simulation-based evaluation with internal-user feedback, but acknowledges plausible internal users and overlap in low-risk testing. Its rationale explicitly asks whether absent feedback/toggling is evidence of mismatch or merely missing positive evidence. This is a recorded qualification of non-applicability, not a proposed reversal. All 31 texts and origins are in `not_applicable_decisions.csv`; P051 is separately labeled corrected.

## The 773 insufficient_information decisions

**345 (44.63%) are supported; 427 (55.24%) partially_supported; one (0.13%) unsupported.** The 428 non-supported judgments are exported with full original texts and auditable text flags in `insufficient_information_review.csv`. Unlike the 15-case close reading, this larger subset receives a complete deterministic text-rule pass plus selected close readings. This does not claim exhaustive semantic adjudication of all 428 cases.

### Recurring recorded explanations and rubric-sensitive language

Rules in `codebook.json` search case-insensitively within each rationale or individual gap, without normalization. Each case counts at most once per signal; labels overlap. `text_signal_evidence.csv` preserves the complete originating field for every match. `text_signal_summary.csv` also separates partially_supported and unsupported counts. These are lexical observations, not validated rates of protocol violation, and rule non-matches do not establish absence of a concern.

{signal_table}

The intersection of a boundary criticism in gaps (I2) and acknowledged absence of incompatibility in the rationale (I3) contains **{stats['boundary_gap_and_no_incompatibility_signal_intersection']} cases**. This identifies candidates for scrutiny, not a count of demonstrated conflations. The dominant recorded explanation questions why an absent pattern concern justifies uncertainty rather than contextual mismatch, often coupled with requests to engage more explicitly with particular criteria. Material evidence overlooked by a rationale can be a legitimate support limitation; requiring missing architectural details or rejecting uncertainty simply because the story is functionally specific can conflict with the v1.1 clarification. Recorded verdicts alone cannot settle that distinction.

Selected close readings illustrate both possibilities:

- **SYS01-US01 × P002, partially_supported:** the rationale accepts that a pipeline could implement retrieval/answering but that possibility does not establish a pipeline requirement; it also acknowledges no incompatibility, yet questions the uncertainty-versus-mismatch explanation. This raises a rubric-sensitive boundary issue rather than establishing non-applicability.
- **SYS01-US01 × P003, partially_supported:** the judge identifies a potential requester/provider interpretation and criticizes incomplete consideration of that evidence, while acknowledging missing explicit multiple-client/network details. This is a more specific claimed evidence-engagement limitation; it should not be grouped automatically with criticism of missing detail alone.
- **SYS01-US01 × P044; SYS04-US03 × P063 and P069, partially_supported:** recorded gaps criticize absent requirement references while expressly acknowledging that omission is permitted. These examples warrant caution about whether a concrete material reasoning limitation, rather than the allowed empty array itself, underlies the verdict. They are not silently excluded or rescored. The I4 count is a reproducible lexical flag, not an estimate of confirmed invalid judgments.
- **SYS04-US01 × P026 (CI/CD), the sole unsupported case:** the judge treats the functionally specified simulation context and lack of build/test/release requirements as a relevant contextual mismatch and proposes not_applicable. Its rationale simultaneously states: “Absence of positive evidence alone does not establish non-applicability, so the more defensible result is not_applicable rather than insufficient_information.” This contains an apparent tension between the stated principle and proposed replacement. The protocol asks for support assessment, not replacement classification. The judgment remains recorded as unsupported; this analysis does not establish GPT error or substitute a verdict.

An absence of architectural information may be precisely what supports insufficient_information; absence of contradiction is also not positive applicability evidence. Neither direction can be resolved by absence alone. These cautions are particularly material because 773 of 840 original classifications occupy this category.

## Methodological limitations

1. **Response conditioning:** the judge sees the original GPT classification and rationale. Support frequencies are not independent classification replication and may reflect anchoring or the presentation of justification.
2. **No complete human ground truth:** support for a rationale does not establish architectural correctness, ADR quality or human endorsement. No error, false-positive, accuracy or superiority claims are warranted. Human Q5 integration is deferred.
3. **Unequal categories and dependent observations:** stories share systems and patterns recur. The 840 pairs are a finite study corpus, not 840 independent random observations; no inferential significance tests or confidence intervals are claimed. Applicable decisions form a selected 36-case subset.
4. **Judge/rubric behavior:** machine-valid references and JSON do not establish semantic adherence. Some rationales invoke uniqueness, domain literalism, permitted reference omission, or uncertainty-versus-mismatch tensions. Text flags identify language, not independently confirmed reasoning failures.
5. **Qualitative subjectivity:** codes are post-hoc single-assistant interpretations of recorded text, not new expert assessments. Multi-label frequencies depend on explicit code definitions and regex vocabulary; they do not quantify causal reasons or objective defects.
6. **One analytical correction:** the 840th record is a documented reference-only correction of an originally invalid response, not an original API-validated judgment. Its inclusion adds one supported not_applicable decision and changes no applicable-case result. Both failed attempts remain preserved; source selection was earliest attempt rather than outcome selection.
7. **Single execution:** these data describe one configured judge run, not variability across runs, prompts or model families. No blind-run results or RAG baseline are included.

## Reproduction and files

From the repository root, without credentials or network access:

```bash
python -B research_results/llm_judge_support_rq1/analysis/analyze.py
python -B -m unittest discover -s research_results/llm_judge_support_rq1/analysis -p 'test_analysis.py' -v
```

The runner reads and validates frozen source records, emits deterministic reports only into this `analysis/` directory, and checks source hashes again after computation. Existing generated files must be byte-identical on rerun; it refuses differing overwrites. No scientific or experimental artifacts are edited. `analysis_provenance.json` records source, code, codebook, annotation and output hashes; `validation.json` records coverage and validation status.

Outputs: `support_matrix.csv`, `by_system.csv`, `by_story.csv`, `applicable_decisions.csv`, `not_applicable_decisions.csv`, `insufficient_information_review.csv`, `evidence_limitations.csv`, `text_signal_summary.csv`, `text_signal_evidence.csv`, `representative_cases.csv`, `statistics.json`, this `report.md`, validation and provenance JSON. Input coding artifacts are `codebook.json` and `applicable_partial_coding.json`; reproducible code/tests are `analyze.py` and `test_analysis.py`.
'''


def build_outputs(rows, annotations, book, origins):
    stats, insuff, matches, signals = summarize(rows, annotations, book)
    out = {'statistics.json': json_text(stats)}
    for filename, field in [('support_matrix.csv', None), ('by_system.csv', 'system'), ('by_story.csv', 'user_story_id')]:
        summary = breakdown(rows, field)
        if field is None:
            summary = [r for r in summary if r['gpt_classification'] != 'all']
        out[filename] = csv_text(summary, SUMMARY_FIELDS)
    for name, classification in [('applicable_decisions.csv', 'applicable'), ('not_applicable_decisions.csv', 'not_applicable')]:
        out[name] = csv_text([flattened(r) for r in rows if r['gpt_classification'] == classification], CASE_FIELDS)
    out['insufficient_information_review.csv'] = csv_text([{**flattened(r), 'text_signals': [code for code in book['text_signals'] if c.record_key(r) in signals[code]]} for r in insuff], CASE_FIELDS + ['text_signals'])
    out['text_signal_evidence.csv'] = csv_text(matches, ['user_story_id', 'pattern_id', 'verdict', 'signal', 'field', 'verbatim_text'])
    signal_summary = []
    for code, rule in book['text_signals'].items():
        for verdict in ('all_nonsupported', 'partially_supported', 'unsupported'):
            subset = [r for r in insuff if verdict == 'all_nonsupported' or r['judgment']['verdict'] == verdict]
            n = sum(c.record_key(r) in signals[code] for r in subset)
            signal_summary.append({'signal': code, 'label': rule['label'], 'verdict_subset': verdict, 'count': n, 'denominator': len(subset), 'percent': percentage(n, len(subset))})
    out['text_signal_summary.csv'] = csv_text(signal_summary, ['signal', 'label', 'verdict_subset', 'count', 'denominator', 'percent'])
    limitation_rows = []
    for code, detail in book['qualitative_codes'].items():
        cases = [a for a in annotations if code in a['codes']]
        limitation_rows.append({'code': code, 'label': detail['label'], 'definition': detail['definition'], 'cases': len(cases), 'denominator': 15,
                                'representative_cases': [a['user_story_id'] + ' × P' + a['pattern_id'] for a in cases[:3]],
                                'all_cases': [a['user_story_id'] + ' × P' + a['pattern_id'] for a in cases],
                                'interpretation_status': 'Post-hoc analyst interpretation of judge text, not independent adjudication'})
    out['evidence_limitations.csv'] = csv_text(limitation_rows, ['code', 'label', 'definition', 'cases', 'denominator', 'representative_cases', 'all_cases', 'interpretation_status'])
    examples = {('SYS01-US01','001'), ('SYS03-US02','050'), ('SYS03-US03','050'), ('SYS02-US02','070'), ('SYS04-US02','028'), ('SYS04-US03','043'), ('SYS04-US03','034'), ('SYS01-US01','002'), ('SYS01-US01','003'), ('SYS01-US01','044'), ('SYS04-US03','063'), ('SYS04-US03','069'), ('SYS04-US01','026')}
    out['representative_cases.csv'] = csv_text([flattened(r) for r in rows if c.record_key(r) in examples], CASE_FIELDS)
    out['report.md'] = report(rows, annotations, book, stats)
    out['validation.json'] = json_text({'status': 'passed', 'unique_pairs': 840, 'user_stories': 12, 'patterns': 70, 'systems': 4,
        'origins': origins, 'gpt_classifications': stats['gpt_classifications'], 'all_case_reference_and_json_validations': 'passed using unchanged protocol validator',
        'exact_consolidated_source_reconstruction': True, 'all_839_original_judgments_unchanged': True,
        'corrected_verdict_rationale_and_gaps_unchanged': True, 'all_15_partial_applicable_annotations_quote_original_gaps': True,
        'frozen_source_manifest_protocol_and_correction_hashes_verified': True,
        'scientific_protocol_id': p.PROTOCOL_ID, 'operational_policy_id': c.op.POLICY['policy_id']})
    return out


def source_snapshot():
    paths = set(c.input_hashes())
    paths.update(str(path.relative_to(ROOT)) for path in PARENT.iterdir() if path.is_file())
    paths.update(str(path.relative_to(ROOT)) for path in HERE.iterdir() if path.name in ('analyze.py', 'test_analysis.py', 'codebook.json', 'applicable_partial_coding.json'))
    return {name: p.file_hash(ROOT / name) for name in sorted(paths)}


def main():
    before = source_snapshot()
    rows, origins, _ = validate_sources()
    annotations = p.strict_json((HERE / 'applicable_partial_coding.json').read_text())
    book = p.strict_json((HERE / 'codebook.json').read_text())
    outputs = build_outputs(rows, annotations, book, origins)
    p.require(source_snapshot() == before, 'Sources changed during analysis')
    provenance = {'scientific_protocol_id': p.PROTOCOL_ID, 'operational_policy_id': c.op.POLICY['policy_id'],
                  'source_sha256': before, 'output_sha256': {name: hashlib.sha256(value.encode()).hexdigest() for name, value in sorted(outputs.items())},
                  'execution': 'Offline deterministic Python standard-library analysis; no model calls; no timestamps in deterministic outputs',
                  'qualitative_authority': 'Single-assistant post-hoc descriptive coding, not independent human ground truth'}
    outputs['analysis_provenance.json'] = json_text(provenance)
    # Preflight every existing output before writing any, so a divergent rerun fails closed.
    for name, value in outputs.items():
        path = HERE / name
        p.require(not path.exists() or path.read_bytes() == value.encode(), f'Refusing different overwrite: {path}')
    for name, value in outputs.items():
        c.write_identical_or_new(HERE / name, value)
    print(f'Validated {len(rows)} pairs (839 original + 1 corrected); generated {len(outputs)} deterministic analysis outputs.')


if __name__ == '__main__':
    main()
