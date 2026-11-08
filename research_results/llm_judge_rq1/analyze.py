"""Offline, deterministic comparison of frozen GPT and official Claude RQ1 results."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GPT_PATH = ROOT / 'experiments/pattern_selection/outputs/assessments.jsonl'
CLAUDE_OUTPUTS = ROOT / 'experiments/llm_judge_rq1/outputs'
MODEL = 'claude-sonnet-5-5'
spec = importlib.util.spec_from_file_location('rq1_claude_runner', ROOT / 'experiments/llm_judge_rq1/run_experiment.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from assess_pattern import CLASSIFICATIONS, MODEL as GPT_MODEL, REASONING_EFFORT, validate_assessment

CATEGORIES = tuple(CLASSIFICATIONS)
FIELDS = ('classification', 'requirement_refs', 'rationale')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, f'Duplicate JSON field: {key}')
        result[key] = value
    return result


def strict_json(text):
    def invalid_constant(value):
        raise ValueError(f'Non-finite JSON constant: {value}')
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def read_jsonl(path):
    raw = path.read_bytes()
    require(bool(raw) and raw.endswith(b'\n'), f'{path}: empty or truncated JSONL')
    result = []
    for number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
        try:
            row = strict_json(line)
            require(isinstance(row, dict), 'Expected a JSON object')
            result.append(row)
        except (ValueError, TypeError) as error:
            raise ValueError(f'{path}:{number}: {error}') from error
    return result


def pair_key(row):
    require(all(isinstance(row.get(k), str) and row[k] for k in ('user_story_id', 'pattern_id')),
            'Missing or non-string pair identifier')
    return row['user_story_id'], row['pattern_id']


def validate_records(records, pairs, label):
    expected = {(c['user_story_id'], p['id']): c for c, p in pairs}
    require(len(expected) == 840, 'Expected input universe of 840 unique pairs')
    require(len(records) == 840, f'{label}: expected exactly 840 records, found {len(records)}')
    indexed = {}
    for row in records:
        key = pair_key(row)
        require(key in expected, f'{label}: unknown pair {key}')
        require(key not in indexed, f'{label}: duplicate pair {key}')
        require(all(k in row for k in FIELDS), f'{label}: missing assessment fields for {key}')
        try:
            validate_assessment({k: row[k] for k in FIELDS}, expected[key])
        except (ValueError, TypeError) as error:
            raise ValueError(f'{label} {key}: {error}') from error
        if label == 'GPT':
            require(set(row) == set(FIELDS) | {'user_story_id', 'pattern_id', 'model', 'reasoning_effort'},
                    f'GPT: unexpected record fields for {key}')
            require(row.get('model') == GPT_MODEL and row.get('reasoning_effort') == REASONING_EFFORT,
                    f'GPT: model/configuration mismatch for {key}')
        indexed[key] = row
    require(set(indexed) == set(expected), f'{label}: incomplete pair coverage')
    return indexed


def locate_official(base=CLAUDE_OUTPUTS):
    candidates = []
    for path in sorted(base.rglob('results.jsonl')):
        manifest_path = path.parent / 'manifest.json'
        if not manifest_path.exists():
            continue
        manifest = strict_json(manifest_path.read_text(encoding='utf-8')).get('experiment', {})
        if manifest.get('mode') == 'full' and manifest.get('configuration', {}).get('model') == MODEL:
            candidates.append(path)
    require(len(candidates) == 1,
            f'Expected exactly one official {MODEL} full run, found {len(candidates)}; use --claude-results to disambiguate')
    return candidates[0]


def timestamp(value):
    require(isinstance(value, str), 'Timestamp must be a string')
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None, 'Timestamp must include a timezone')
    return parsed


def validate_claude(path, indexed, pairs):
    directory = path.parent
    wrapper = strict_json((directory / 'manifest.json').read_text(encoding='utf-8'))
    manifest = wrapper['experiment']
    timestamp(wrapper['created_at'])
    config = manifest['configuration']
    require(config.get('model') == MODEL, 'Not the official Sonnet model')
    require(type(config.get('max_tokens')) is int and config['max_tokens'] > 0, 'Invalid token limit')
    timeout = manifest['timeout_seconds']
    require(type(timeout) in (float, int) and math.isfinite(timeout) and timeout > 0, 'Invalid timeout')
    require(config == runner.request_config(MODEL, config['max_tokens']),
            'Claude configuration differs from original instructions/schema and adaptive/high protocol')
    expected = runner.provenance(pairs, config, 'full', runner.SDK_VERSION, timeout)
    require(manifest == expected, 'Claude official manifest/provenance mismatch (inputs/prompts/source/configuration)')
    fingerprint = runner.digest(manifest)
    events = read_jsonl(directory / 'events.jsonl')
    starts, ends = {}, {}
    failed = []
    for event in events:
        kind = event.get('event')
        execution = event.get('execution_id')
        require(isinstance(execution, str) and execution, 'Missing execution ID')
        timestamp(event['at'])
        if kind == 'execution_started':
            require(execution not in starts, 'Duplicate execution start')
            require(event.get('experiment_sha256') == fingerprint, 'Event provenance mismatch')
            require(type(event.get('already_completed')) is int and 0 <= event['already_completed'] <= 840,
                    'Invalid completed-count at start')
            require(type(event.get('retry_unfinished')) is bool, 'Missing explicit retry policy')
            require('--full-run' in event.get('argv', []), 'Execution did not explicitly request full run')
            starts[execution] = event
        elif kind in ('execution_completed', 'execution_failed'):
            require(execution in starts and execution not in ends, 'Unmatched or duplicate execution termination')
            require(timestamp(event['at']) >= timestamp(starts[execution]['at']), 'Invalid execution chronology')
            ends[execution] = event
            if kind == 'execution_failed':
                failed.append(event)
        else:
            raise ValueError(f'Unknown execution event {kind!r}')
    require(events[-1].get('event') == 'execution_completed' and events[-1].get('validated_results') == 840,
            'Official run has no final completion of 840 assessments')
    attempts = read_jsonl(directory / 'attempts.jsonl')
    attempts_by_id = {}
    attempts_per_pair = Counter()
    for attempt in attempts:
        key = pair_key(attempt)
        require(key in indexed, f'Unknown attempt pair {key}')
        attempt_id = attempt.get('attempt_id')
        require(isinstance(attempt_id, str) and attempt_id and attempt_id not in attempts_by_id,
                'Missing or duplicate attempt ID')
        require(attempt.get('execution_id') in starts, 'Attempt references unknown execution')
        # Expected per-pair hashes are checked below against original prompts and inputs.
        require(attempt.get('experiment_sha256') == fingerprint, 'Attempt provenance mismatch')
        timestamp(attempt['started_at'])
        execution_start = starts[attempt['execution_id']]
        require(timestamp(attempt['started_at']) >= timestamp(execution_start['at']),
                'Attempt precedes execution start')
        attempts_by_id[attempt_id] = attempt
        attempts_per_pair[key] += 1
    pair_inputs = {(c['user_story_id'], p['id']): (c, p) for c, p in pairs}
    for attempt in attempts:
        c, p = pair_inputs[pair_key(attempt)]
        require(attempt.get('input_sha256') == runner.digest([c, p])
                and attempt.get('prompt_sha256') == runner.digest(runner.build_prompt(c, p)),
                'Attempt input/prompt hash mismatch')
    response_ids, matched = set(), set()
    for key, row in indexed.items():
        require(row.get('attempt_id') in attempts_by_id, f'Result without matching attempt: {key}')
        attempt = attempts_by_id[row['attempt_id']]
        require(row['attempt_id'] not in matched, 'Attempt reused by multiple results')
        matched.add(row['attempt_id'])
        require(all(row.get(k) == v for k, v in attempt.items()), f'Result/attempt mismatch: {key}')
        require(row.get('model') == row.get('response_model') == MODEL
                and row.get('effort') == 'high' and row.get('thinking') == {'type': 'adaptive'}
                and row.get('stop_reason') == 'end_turn', f'Response configuration/completion mismatch: {key}')
        require(timestamp(row['completed_at']) >= timestamp(row['started_at']), 'Invalid response chronology')
        end = ends.get(row['execution_id'])
        if end:
            require(timestamp(row['completed_at']) <= timestamp(end['at']), 'Result follows execution termination')
        require(isinstance(row.get('response_id'), str) and row['response_id']
                and row['response_id'] not in response_ids, 'Missing or duplicate response ID')
        response_ids.add(row['response_id'])
        require(isinstance(row.get('request_id'), str) and row['request_id'], 'Missing request ID')
        blocks = row.get('content_block_types', [])
        require(isinstance(blocks, list) and blocks.count('text') == 1
                and all(b in ('text', 'thinking', 'redacted_thinking') for b in blocks), 'Invalid response block types')
        usage = row.get('usage', {})
        require(isinstance(usage, dict), 'Usage must be an object')
        for field in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'):
            require(type(usage.get(field)) is int and usage[field] >= 0, f'Invalid usage {field}')
        details = usage.get('output_tokens_details', {})
        require(isinstance(details, dict), 'Output-token details must be an object')
        thinking_tokens = details.get('thinking_tokens')
        require(type(thinking_tokens) is int and 0 <= thinking_tokens <= usage['output_tokens'], 'Invalid thinking token count')
        elapsed = row.get('elapsed_seconds')
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
                'Invalid response duration')
    return manifest, {
        'executions': len(starts), 'attempts': len(attempts),
        'pairs_with_multiple_attempts': sum(n > 1 for n in attempts_per_pair.values()),
        'attempts_without_validated_result': len(attempts) - len(matched),
        'failure_events': len(failed), 'executions_without_terminal_event': len(set(starts) - set(ends)),
        'explicit_retry_executions': sum(e['retry_unfinished'] for e in starts.values()),
        'incomplete_response_failure_events': sum(e.get('response_metadata', {}).get('stop_reason') not in (None, 'end_turn')
                                                  for e in failed if e.get('response_metadata')),
    }


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def agreement_metrics(rows):
    require(bool(rows), 'Cannot compute metrics for empty dataset')
    matrix = Counter((r['gpt_classification'], r['claude_classification']) for r in rows)
    n = len(rows)
    g = Counter(r['gpt_classification'] for r in rows)
    c = Counter(r['claude_classification'] for r in rows)
    agreements = sum(matrix[k, k] for k in CATEGORIES)
    observed = Fraction(agreements, n)
    expected = sum((Fraction(g[k] * c[k], n * n) for k in CATEGORIES), Fraction(0))
    kappa = (observed - expected) / (1 - expected) if expected != 1 else None
    both = matrix['applicable', 'applicable']
    union = g['applicable'] + c['applicable'] - both
    return {
        'pairs': n, 'agreements': agreements, 'disagreements': n - agreements,
        'overall_agreement': float(observed), 'expected_agreement_from_marginals': float(expected),
        'cohens_kappa': float(kappa) if kappa is not None else None,
        'gpt_applicable': g['applicable'], 'claude_applicable': c['applicable'],
        'both_applicable': both, 'gpt_applicable_not_claude_applicable': g['applicable'] - both,
        'claude_applicable_not_gpt_applicable': c['applicable'] - both,
        'applicable_union': union, 'positive_jaccard': ratio(both, union),
        'gpt_selected_overlap_fraction': ratio(both, g['applicable']),
        'claude_selected_overlap_fraction': ratio(both, c['applicable']),
        'positive_dice_agreement': ratio(2 * both, g['applicable'] + c['applicable']),
        'gpt_not_applicable': g['not_applicable'], 'claude_not_applicable': c['not_applicable'],
        'gpt_insufficient_information': g['insufficient_information'],
        'claude_insufficient_information': c['insufficient_information'],
        'gpt_insufficient_claude_not_applicable': matrix['insufficient_information', 'not_applicable'],
        'gpt_not_applicable_claude_insufficient': matrix['not_applicable', 'insufficient_information'],
    }


def comparison_rows(pairs, gpt, claude):
    rows = []
    for case, pattern in pairs:
        key = case['user_story_id'], pattern['id']
        g, c = gpt[key], claude[key]
        rows.append({
            'system': case['system'], 'user_story_id': key[0], 'pattern_id': key[1],
            'pattern_name': pattern['name'], 'system_purpose': case['system_purpose'],
            'user_story': case['user_story'],
            'acceptance_criteria': json.dumps(case['acceptance_criteria'], ensure_ascii=False),
            'gpt_model': g['model'], 'claude_model': c['response_model'],
            'gpt_classification': g['classification'], 'claude_classification': c['classification'],
            'agreement': g['classification'] == c['classification'],
            'gpt_requirement_refs': json.dumps(g['requirement_refs'], ensure_ascii=False),
            'claude_requirement_refs': json.dumps(c['requirement_refs'], ensure_ascii=False),
            'gpt_rationale': g['rationale'], 'claude_rationale': c['rationale'],
        })
    return rows


def group_metrics(rows, field):
    groups = defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    return [{field: key, **agreement_metrics(group)} for key, group in sorted(groups.items())]


def csv_text(rows, fields=None):
    import io
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def md_table(headers, rows):
    def escape(value):
        return str(value).replace('|', '\\|').replace('\n', '<br>')
    return '\n'.join(['| ' + ' | '.join(map(escape, headers)) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(map(escape, row)) + ' |' for row in rows])


def percent(value):
    return f'{value:.2%}' if value is not None else 'undefined'


def render_outputs(pairs, gpt, claude, manifest, audit, source_paths):
    rows = comparison_rows(pairs, gpt, claude)
    metrics = agreement_metrics(rows)
    matrix = Counter((r['gpt_classification'], r['claude_classification']) for r in rows)
    matrix_rows = [{'gpt_classification': g, **{c: matrix[g, c] for c in CATEGORIES}} for g in CATEGORIES]
    per_class = []
    for g in CATEGORIES:
        total = sum(matrix[g, c] for c in CATEGORIES)
        per_class.append({'gpt_classification': g, 'gpt_count': total, 'same_classification': matrix[g, g],
                          'agreement_given_gpt_classification': ratio(matrix[g, g], total)})
    story = group_metrics(rows, 'user_story_id')
    systems = group_metrics(rows, 'system')
    patterns = group_metrics(rows, 'pattern_id')
    only_g = [r for r in rows if r['gpt_classification'] == 'applicable' and r['claude_classification'] != 'applicable']
    only_c = [r for r in rows if r['claude_classification'] == 'applicable' and r['gpt_classification'] != 'applicable']
    files = {
        'pair_comparison.csv': csv_text(rows),
        'agreement_matrix.csv': csv_text(matrix_rows),
        'agreement_by_gpt_classification.csv': csv_text(per_class),
        'overall_metrics.csv': csv_text([{'metric': k, 'value': v if v is not None else '',
                                         'denominator_note': 'fractions are 0–1; blank means undefined'} for k, v in metrics.items()]),
        'by_user_story.csv': csv_text(story), 'by_system.csv': csv_text(systems),
        'by_pattern.csv': csv_text(patterns),
        'gpt_selected_not_claude_applicable.csv': csv_text(only_g, list(rows[0])),
        'claude_applicable_not_gpt_selected.csv': csv_text(only_c, list(rows[0])),
    }
    def group_table(groups, field):
        return md_table([field, 'Pairs', 'Agree', 'Disagree', 'Agreement', 'GPT applicable', 'Claude applicable', 'Both applicable', 'Positive Jaccard'],
                        [[r[field], r['pairs'], r['agreements'], r['disagreements'], percent(r['overall_agreement']),
                          r['gpt_applicable'], r['claude_applicable'], r['both_applicable'], percent(r['positive_jaccard'])] for r in groups])
    def difference_table(group):
        return md_table(['Story', 'Pattern', 'Name', 'GPT classification', 'Claude classification'],
                        [[r['user_story_id'], r['pattern_id'], r['pattern_name'], r['gpt_classification'], r['claude_classification']] for r in group])
    distinct_g = len({r['pattern_id'] for r in rows if r['gpt_classification'] == 'applicable'})
    distinct_c = len({r['pattern_id'] for r in rows if r['claude_classification'] == 'applicable'})
    shifted = metrics['gpt_insufficient_claude_not_applicable']
    lowest_story = min(story, key=lambda r: r['overall_agreement'])
    highest_story = max(story, key=lambda r: r['overall_agreement'])
    files['report.md'] = f'''# ADR4AI RQ1: independent GPT–Claude classification comparison

## Scope and validation

Both frozen datasets contain exactly 840 unique User Story × Pattern pairs:
12 user stories, 70 patterns (001–070), four systems, 70 assessments per story,
and 12 assessments per pattern. Both cover the complete, identical Cartesian
product. All classifications, required fields, and requirement references pass
the original validator. No missing, duplicate, or unknown pairs are accepted.
Claude's official full-run manifest, source/configuration/input/prompt hashes,
all result/attempt links, response identifiers, and final completion were verified.
See [validation.md](validation.md) and [analysis_provenance.json](analysis_provenance.json).

The unit of selection is a **User Story × Pattern pair**. GPT's 36 selected pairs
involve {distinct_g} distinct pattern IDs; Claude's {metrics['claude_applicable']} selected pairs involve {distinct_c}.
Repeated pattern IDs across different stories are not collapsed in overlap metrics.

## Three-category agreement matrix

Rows are GPT; columns are Claude. Categories retain their original meanings.

{md_table(['GPT / Claude', *CATEGORIES], [[r['gpt_classification'], *[r[c] for c in CATEGORIES]] for r in matrix_rows])}

GPT marginals: {metrics['gpt_applicable']} applicable, {metrics['gpt_not_applicable']} not_applicable,
{metrics['gpt_insufficient_information']} insufficient_information. Claude marginals:
{metrics['claude_applicable']} applicable, {metrics['claude_not_applicable']} not_applicable,
{metrics['claude_insufficient_information']} insufficient_information.

Overall exact agreement is **{metrics['agreements']}/840 = {percent(metrics['overall_agreement'])}**;
there are {metrics['disagreements']} disagreements. Cohen's unweighted nominal kappa
is **{metrics['cohens_kappa']:.6f}**, with expected agreement from empirical marginals
{percent(metrics['expected_agreement_from_marginals'])}.

{md_table(['GPT classification', 'GPT count', 'Same classification', 'Conditional agreement'], [[r['gpt_classification'], r['gpt_count'], r['same_classification'], percent(r['agreement_given_gpt_classification'])] for r in per_class])}

The dominant difference is GPT insufficient_information → Claude not_applicable:
{shifted} pairs, {percent(shifted / metrics['disagreements'])} of all disagreements.
The reverse direction occurs in {metrics['gpt_not_applicable_claude_insufficient']} pairs.
This describes different decisions about evidence sufficiency/non-applicability;
it does not establish which decisions are justified. Rationales are exported
verbatim for subsequent independent review; no automated thematic coding or
adjudication is claimed here.

## Positive-selection overlap

Claude also classified **{metrics['both_applicable']} of GPT's 36 selected pairs** as applicable
({percent(metrics['gpt_selected_overlap_fraction'])}). Conversely,
{metrics['both_applicable']}/{metrics['claude_applicable']} Claude-selected pairs were also GPT-selected
({percent(metrics['claude_selected_overlap_fraction'])}).

- Intersection: {metrics['both_applicable']} pairs; union: {metrics['applicable_union']} pairs.
- Jaccard overlap = intersection/union = **{percent(metrics['positive_jaccard'])}**.
- Symmetric positive Dice agreement = 2 × intersection/(GPT applicable + Claude applicable)
  = **{percent(metrics['positive_dice_agreement'])}**.
- GPT applicable but Claude not applicable-selected: {len(only_g)} pairs.
- Claude applicable but GPT not applicable-selected: {len(only_c)} pairs.

Here “not applicable-selected” includes both original non-selected categories;
they remain distinct in the matrix, exports, and pair lists below.

### GPT-selected pairs Claude did not classify as applicable

{difference_table(only_g)}

### Claude-applicable pairs GPT did not select

{difference_table(only_c)}

Full original references and rationales are in the corresponding difference CSVs
and [pair_comparison.csv](pair_comparison.csv).

## Agreement by user story

{group_table(story, 'user_story_id')}

Exact agreement varies from {percent(lowest_story['overall_agreement'])}
({lowest_story['user_story_id']}, {lowest_story['agreements']}/70) to
{percent(highest_story['overall_agreement'])}
({highest_story['user_story_id']}, {highest_story['agreements']}/70).
Selection overlap and exact three-category agreement answer different questions:
SYS01-US01 shares all three applicable selections, but still has 36 disagreements
among its other 67 pairs. SYS04-US01 has no applicable selections from either
model, so positive Jaccard is undefined even though 49 category disagreements
remain. These are descriptive within-corpus observations, not evidence of
different system-level accuracy.

## Agreement by system

{group_table(systems, 'system')}

Group CSVs additionally include kappa, category marginals, positive overlaps,
and the dominant non-selected-category transition counts. Per-pattern metrics
across 12 stories are in [by_pattern.csv](by_pattern.csv). A blank/undefined
positive overlap means its denominator is zero, not perfect agreement.

## Definitions and methodological limits

1. **Overall agreement** = diagonal count/N. It weights all pairs equally and
   can hide class-specific behavior under class imbalance. Here GPT assigned
   insufficient_information to {percent(metrics['gpt_insufficient_information'] / 840)} of pairs;
   Claude assigned not_applicable to {percent(metrics['claude_not_applicable'] / 840)}.
2. **Agreement by GPT classification** = diagonal cell/GPT row total. This is
   directional conditional agreement, sensitive to the chosen reference model
   and small category sizes; GPT is a reference for tabulation, not ground truth.
3. **Cohen's kappa** = (p_o − p_e)/(1 − p_e), with p_e = sum over categories of
   GPT marginal × Claude marginal/N². Categories are nominal, so no ordinal
   weighting is used. Kappa depends on prevalence and marginal imbalance;
   its chance model is an algebraic baseline, not a validated account of LLM
   decision processes. It cannot establish correctness or superiority. Kappa
   is undefined if p_e=1; no qualitative strength labels are imposed.
4. **Positive selection** uses sets of applicable pairs. Jaccard and Dice
   avoid agreement inflation from jointly non-selected pairs, but ignore the
   distinction between not_applicable and insufficient_information and are
   unstable when few positives occur. The directional overlap fractions are
   not accuracy, precision, or recall measures. Overlap is undefined when its
   denominator is zero. Binary selection overlap supplements rather than
   replaces the three-category analysis.
5. Neither model supplies independent human ground truth for all 840 pairs.
   Disagreements are not confirmed errors or false positives/negatives.
   Agreement is not proof of validity, and model superiority is not assessed.
   Schema/reference validation establishes structural validity and evidence-ID
   ownership, not semantic support for a classification or rationale.
6. The 840 pairs reuse 12 stories and 70 patterns from four systems. They are
   not 840 independently sampled requirements. All metrics are descriptive
   of this fixed corpus; no naive independent-pair confidence intervals,
   significance tests, or population generalization are reported. Group
   results are exploratory and share the same dependence and imbalance limits.
7. Each model contributed one validated outcome per pair. This analysis does
   not quantify stochastic run-to-run variability, causal provider effects,
   or matched computational budgets. The label high is provider-specific.
   Prior technical pilots existed and are excluded; this is a replication
   using shared prompts/inputs, not an independently designed human judgment.
8. Claude provenance is checked against the recorded manifest and current
   source/input files. This is an integrity/consistency check, not a signed
   external attestation. GPT records contain model/effort and outcomes but no
   equivalent per-response prompt/input hashes or full execution manifest;
   historical GPT prompt delivery cannot be retrospectively proven by this
   analysis. No outputs are repaired, translated, normalized, or overwritten.
9. No prompt/configuration is changed in response to these findings. No RAG
   baseline, architects' Q5 evaluations, external service, or API is used.

## Reproduction and exports

From the repository root, Python 3.10+ and the standard library suffice:

```bash
python -B research_results/llm_judge_rq1/analyze.py
python -B -m unittest discover -s research_results/llm_judge_rq1 -p 'test_*.py' -v
```

Reports are deterministic for unchanged inputs/code; no current timestamp or
absolute machine path is embedded. CSV uses UTF-8, quoted multiline cells,
string pattern IDs (import as text to preserve leading zeros), and JSON arrays
for references and acceptance criteria. Parsing those arrays restores their
original order/values. Rationales and requirement/catalog text are copied without
translation, trimming, or correction. [analysis_provenance.json](analysis_provenance.json)
records SHA256 hashes of raw experimental files, original inputs, analysis code,
and every generated report. All validation finishes before report files are written.
'''
    files['validation.md'] = f'''# Validation audit

Status: **PASS**. All checks are mandatory; a mismatch aborts analysis.

- GPT: 840 unique pairs; model {GPT_MODEL}, effort {REASONING_EFFORT}.
- Claude: 840 unique pairs; mode full; actual/requested model {MODEL};
  effort high; adaptive thinking; max_tokens {manifest['configuration']['max_tokens']};
  SDK {manifest['sdk_version']}; timeout {manifest['timeout_seconds']} seconds;
  SDK retries {manifest['sdk_max_retries']}.
- Same 12 stories × 70 patterns; four systems; three stories per system;
  35 acceptance criteria. Complete cross product verified in both datasets.
- Original classification schema constraints and reference ownership validated.
- Full original instruction/schema/input/prompt/runner/loader hashes verified.
- Each Claude result matches its reserved attempt and experiment fingerprint;
  response IDs are unique; model/configuration/stop reason/block types and usage
  are checked. All 840 accepted results have stop_reason=end_turn.
- Final full-run execution event records 840 validated results.
- Official input: `{source_paths['claude_results']}`.
- GPT input: `{source_paths['gpt_results']}`.
- Claude execution audit:
{chr(10).join(f'  - {k}: {v}' for k, v in audit.items())}
- Pilots are excluded by mode/model selection. Analysis never calls the runner's
  mutation or execution helpers, creates clients, or imports an LLM SDK.
- GPT lacks equivalent historical response/hash metadata; retrospective execution
  provenance is correspondingly limited (see report.md).
'''
    return files, metrics


def run_analysis(claude_path=None, output_dir=HERE, gpt_path=GPT_PATH):
    pairs = runner.dataset()
    require({p['id'] for _, p in pairs} == {f'{i:03d}' for i in range(1, 71)}, 'Unexpected pattern IDs')
    claude_path = Path(claude_path) if claude_path else locate_official()
    gpt_path = Path(gpt_path)
    original_paths = [gpt_path, claude_path, *[claude_path.parent / name for name in
                      ('manifest.json', 'attempts.jsonl', 'events.jsonl')],
                      ROOT / 'data/user_histories_orig.csv', *sorted((ROOT / 'catalogs/patterns').glob('P*.json')),
                      ROOT / 'experiments/pattern_selection/assess_pattern.py',
                      ROOT / 'experiments/pattern_selection/prepare_data.py',
                      ROOT / 'experiments/llm_judge_rq1/run_experiment.py']
    def label(path):
        return path.resolve().relative_to(ROOT).as_posix()
    before = {label(path): file_hash(path) for path in original_paths}
    gpt = validate_records(read_jsonl(gpt_path), pairs, 'GPT')
    claude = validate_records(read_jsonl(claude_path), pairs, 'Claude')
    manifest, audit = validate_claude(claude_path, claude, pairs)
    sources = {'gpt_results': label(gpt_path), 'claude_results': label(claude_path)}
    files, metrics = render_outputs(pairs, gpt, claude, manifest, audit, sources)
    require(before == {label(path): file_hash(path) for path in original_paths},
            'Input files changed during analysis')
    provenance = {
        'analysis_version': 1, 'sources': sources, 'input_file_sha256': before,
        'analysis_source_sha256': {p.name: file_hash(p) for p in (HERE / 'analyze.py', HERE / 'test_analysis.py')},
        'claude_experiment_sha256': runner.digest(manifest), 'validation': 'passed',
        'claude_execution_audit': audit,
        'output_sha256': {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in sorted(files.items())},
    }
    files['analysis_provenance.json'] = json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    output_dir = Path(output_dir).resolve()
    require(output_dir.is_relative_to(ROOT / 'research_results') or output_dir.is_relative_to(Path('/tmp')),
            'Reports must be under research_results/ or /tmp (tests)')
    require(all(output_dir / name != path.resolve() for name in files for path in original_paths),
            'Output would overwrite a scientific input')
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(files.items()):
        (output_dir / name).write_text(text, encoding='utf-8', newline='')
    return metrics, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude-results', type=Path, help='Explicit official full-run results.jsonl if discovery is ambiguous')
    parser.add_argument('--output-dir', type=Path, default=HERE)
    args = parser.parse_args()
    metrics, files = run_analysis(args.claude_results, args.output_dir)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f'Wrote {len(files)} derived reports to {args.output_dir}')


if __name__ == '__main__':
    main()
