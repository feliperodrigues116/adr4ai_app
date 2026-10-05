"""Compile frozen research artifacts using only the Python standard library."""

import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(__file__).resolve().parent
RESULT_FIELDS = [
    'system_id', 'system_purpose', 'user_story_id', 'user_story',
    'acceptance_criteria', 'pattern_id', 'pattern_name', 'pattern_motivation',
    'pattern_solution', 'pattern_consequences', 'classification',
    'evidence_refs', 'evidence_text', 'rationale', 'rag_top5',
]
SUMMARY_FIELDS = [
    'system_id', 'user_story_id', 'applicable_count',
    'applicable_pattern_ids', 'rag_top5_overlap_count',
]
EXPECTED_TOTALS = Counter(applicable=36, not_applicable=31,
                          insufficient_information=773)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as source:
        return list(csv.DictReader(source))


def source_text(record, key, context, allow_empty=False):
    require(key in record and isinstance(record[key], str),
            f'{context}: missing or invalid text field {key}')
    require(allow_empty or bool(record[key]), f'{context}: empty text field {key}')
    return record[key]


def compile_results():
    stories = {}
    references = {}
    for row in read_csv(ROOT / 'data/user_histories_orig.csv'):
        uid = source_text(row, 'user_story_id', 'Requirements')
        require(re.fullmatch(r'SYS\d{2}-US\d{2}', uid),
                f'Invalid user story identifier: {uid}')
        purpose = source_text(row, 'system_purpose', uid)
        story = source_text(row, 'user_story', uid)
        if uid not in stories:
            stories[uid] = dict(system_purpose=purpose, user_story=story, criteria=[])
            require(uid not in references, f'Duplicate requirement identifier: {uid}')
            references[uid] = (uid, story)
        require(stories[uid]['system_purpose'] == purpose and
                stories[uid]['user_story'] == story,
                f'Inconsistent repeated story context: {uid}')
        aid = source_text(row, 'acceptance_criterion_id', uid)
        criterion = source_text(row, 'acceptance_criterion', aid)
        require(re.fullmatch(re.escape(uid) + r'-AC\d{2}', aid),
                f'Acceptance criterion does not belong to story: {aid}')
        require(aid not in references, f'Duplicate requirement identifier: {aid}')
        references[aid] = (uid, criterion)
        stories[uid]['criteria'].append(f'[{aid}] {criterion}')
    require(len(stories) == 12, 'Expected exactly 12 user stories')

    patterns = {}
    for number in range(1, 71):
        pid = f'{number:03d}'
        path = ROOT / f'catalogs/patterns/P{pid}.json'
        pattern = json.loads(path.read_text(encoding='utf-8'))
        require(pattern.get('id') == pid, f'Catalog identifier mismatch: {path}')
        for field in ('name', 'motivation', 'solution', 'consequences'):
            # Empty strings explicitly present in the catalog are preserved.
            source_text(pattern, field, str(path), allow_empty=True)
        patterns[pid] = pattern

    rag = {}
    for row in read_csv(ROOT / 'experiments/rag/outputs/rag_baseline.csv'):
        uid = source_text(row, 'user_story_id', 'RAG')
        require(uid in stories and uid not in rag, f'Unknown or duplicate RAG story: {uid}')
        ids = source_text(row, 'top5_ids', uid).split(';')
        require(len(ids) == 5 and len(set(ids)) == 5 and
                all(pid in patterns for pid in ids), f'Invalid final RAG Top-5: {uid}')
        rag[uid] = set(ids)
    require(set(rag) == set(stories), 'RAG must cover all 12 user stories')

    assessment_path = ROOT / 'experiments/pattern_selection/outputs/assessments.jsonl'
    assessments = [json.loads(line) for line in
                   assessment_path.read_text(encoding='utf-8').splitlines()]
    require(len(assessments) == 840, 'Expected exactly 840 assessments')
    pairs = set()
    totals = Counter()
    results = []
    for assessment in assessments:
        uid = assessment.get('user_story_id')
        pid = assessment.get('pattern_id')
        require(isinstance(uid, str) and uid in stories, f'Unknown assessment story: {uid}')
        require(isinstance(pid, str) and pid in patterns, f'Unknown assessment pattern: {pid}')
        require((uid, pid) not in pairs, f'Duplicate assessment pair: {uid}, {pid}')
        pairs.add((uid, pid))
        classification = assessment.get('classification')
        require(isinstance(classification, str) and classification in EXPECTED_TOTALS,
                f'Invalid classification: {classification}')
        totals[classification] += 1
        refs = assessment.get('requirement_refs')
        require(isinstance(refs, list), f'Invalid requirement_refs: {uid}, {pid}')
        evidence = []
        for ref in refs:
            require(isinstance(ref, str) and ref in references,
                    f'Unresolved evidence reference: {uid}, {pid}, {ref}')
            owner, text = references[ref]
            require(owner == uid, f'Evidence reference belongs to another case: {ref}')
            evidence.append(f'[{ref}] {text}')
        rationale = source_text(assessment, 'rationale', f'{uid}, {pid}')
        if classification != 'applicable':
            continue
        require(bool(refs), f'Applicable pair has no positive evidence: {uid}, {pid}')
        context = stories[uid]
        pattern = patterns[pid]
        results.append(dict(
            system_id=uid.split('-')[0], system_purpose=context['system_purpose'],
            user_story_id=uid, user_story=context['user_story'],
            acceptance_criteria=' | '.join(context['criteria']), pattern_id=pid,
            pattern_name=pattern['name'], pattern_motivation=pattern['motivation'],
            pattern_solution=pattern['solution'], pattern_consequences=pattern['consequences'],
            classification=classification, evidence_refs=';'.join(refs),
            evidence_text=' | '.join(evidence), rationale=rationale,
            rag_top5='yes' if pid in rag[uid] else 'no',
        ))
    require(len(pairs) == 840 and pairs == {(uid, pid) for uid in stories for pid in patterns},
            'Expected the complete set of 840 unique Pattern x User Story pairs')
    require(totals == EXPECTED_TOTALS, f'Unexpected classification totals: {dict(totals)}')
    results.sort(key=lambda row: (row['user_story_id'], int(row['pattern_id'])))
    require(len(results) == 36, 'Expected exactly 36 result rows')
    require(all(row['classification'] == 'applicable' for row in results),
            'Every result must be classified as applicable')
    require(len({(row['user_story_id'], row['pattern_id']) for row in results}) == 36,
            'Expected 36 unique applicable pairs')
    summary = []
    for uid in sorted(stories):
        selected = [row for row in results if row['user_story_id'] == uid]
        summary.append(dict(
            system_id=uid.split('-')[0], user_story_id=uid,
            applicable_count=len(selected),
            applicable_pattern_ids=';'.join(row['pattern_id'] for row in selected),
            rag_top5_overlap_count=sum(row['rag_top5'] == 'yes' for row in selected),
        ))
    require(len(summary) == 12, 'Expected exactly 12 summary rows')
    require(sum(row['applicable_count'] for row in summary) == 36,
            'Summary applicable counts must sum to 36')
    require(any(row['user_story_id'] == 'SYS04-US01' and row['applicable_count'] == 0
                for row in summary), 'SYS04-US01 must have zero applicable patterns')
    require(sum(row['rag_top5_overlap_count'] for row in summary) == 5,
            'Expected exactly 5 applicable pairs in final RAG Top-5')
    require(sum(row['applicable_count'] > 0 for row in summary) == 11,
            'Expected 11 stories with applicable patterns')
    require(sum(row['rag_top5_overlap_count'] > 0 for row in summary) == 5,
            'Expected 5 stories with an applicable pattern in final RAG Top-5')
    return results, summary, totals


def render_csv(rows, fields):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main():
    try:
        results, summary, totals = compile_results()
        # Construct both complete outputs only after every validation succeeds.
        outputs = [
            ('pattern_selection_results.csv', render_csv(results, RESULT_FIELDS)),
            ('pattern_selection_summary.csv', render_csv(summary, SUMMARY_FIELDS)),
        ]
        for filename, content in outputs:
            (OUTPUT / filename).write_text(content, encoding='utf-8', newline='')
        print('All validations passed: 840 assessments; 840 unique pairs.')
        for label in EXPECTED_TOTALS:
            print(f'{label}: {totals[label]}')
        print('Final RAG Top-5 overlap: 5 present; 31 absent.')
        print('Stories with applicable patterns: 11; stories with overlap: 5.')
        for (filename, _), count in zip(outputs, (len(results), len(summary))):
            print(f'{OUTPUT / filename}: {count} data rows')
        fields = ['user_story_id', 'pattern_id', 'pattern_name', 'evidence_refs', 'rag_top5']
        print('First 5 result rows:')
        print(render_csv([{key: row[key] for key in fields} for row in results[:5]], fields),
              end='')
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'Compilation failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
