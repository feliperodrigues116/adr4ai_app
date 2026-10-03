"""Reproduce the fixed retrieval/reranking experiment without external LLMs."""

import csv
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ['user_story_id', 'system', 'top15_ids', 'top15_names',
           'top5_ids', 'top5_names']
DATASET_COLUMNS = {'system', 'system_purpose', 'user_story_id', 'user_story',
                   'acceptance_criterion_id', 'acceptance_criterion'}


def load_cases(path=ROOT / 'data' / 'user_histories_EN.csv'):
    """Validate IDs and metadata, retaining source text and CSV encounter order."""
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not DATASET_COLUMNS.issubset(reader.fieldnames or []):
            raise ValueError('Dataset is missing required columns')
        rows = list(reader)
    grouped = OrderedDict()
    criterion_ids = set()
    for row in rows:
        if any(not row[field] or not row[field].strip() for field in DATASET_COLUMNS):
            raise ValueError('Dataset contains an empty required field')
        if row['acceptance_criterion_id'] in criterion_ids:
            raise ValueError('Acceptance criterion IDs must be unique')
        criterion_ids.add(row['acceptance_criterion_id'])
        grouped.setdefault(row['user_story_id'], []).append(row)
    systems = {row['system'] for row in rows}
    if (len(systems), len(grouped), len(criterion_ids), len(rows)) != (4, 12, 35, 35):
        raise ValueError('Dataset must contain four systems, twelve stories, and thirty-five criteria')
    counts = Counter(case[0]['system'] for case in grouped.values())
    if any(count != 3 for count in counts.values()):
        raise ValueError('Each system must contain exactly three user stories')
    for case in grouped.values():
        if len({(r['system'], r['system_purpose'], r['user_story']) for r in case}) != 1:
            raise ValueError('Story metadata is inconsistent within a user story ID')
    for system in systems:
        if len({r['system_purpose'] for r in rows if r['system'] == system}) != 1:
            raise ValueError('System purpose is inconsistent within a system')
    return grouped


def build_query(case):
    """Include exact source IDs and text in the recorded query format."""
    first = case[0]
    criteria = '\n'.join(f"[{r['acceptance_criterion_id']}] {r['acceptance_criterion']}"
                         for r in case)
    return (f"System Purpose:\n{first['system_purpose']}\n\n"
            f"User Story:\n[{first['user_story_id']}] {first['user_story']}\n\n"
            f"Acceptance Criteria:\n{criteria}")


def write_outputs(results):
    """Replace the package outputs with the reproduced rankings."""
    output = ROOT / 'outputs'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'rag_baseline_reproduced.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    text = ('# ADR4AI RAG Baseline\n\n'
            'Requirements → BAAI/bge-small-en-v1.5 → Vector Retrieval Top-15 '
            '→ BAAI/bge-reranker-base → Top-5\n\n'
            'Dataset: data/user_histories_EN.csv  \nSystems: 4  \n'
            'User stories: 12  \nAcceptance criteria: 35\n\n'
            'Embedding: BAAI/bge-small-en-v1.5  \nVector retrieval: Top-15  \n'
            'Reranker: BAAI/bge-reranker-base  \nFinal ranking: Top-5\n\n'
            'The user_story_id and acceptance_criterion_id values were explicitly '
            'included in the retrieval input for traceability.\n\n'
            'The Top-5 results represent retrieved candidate patterns and should not '
            'be interpreted as validated architectural applicability.\n\n'
            '| user_story_id | top5_ids |\n|---|---|\n')
    text += ''.join(f"| {r['user_story_id']} | {r['top5_ids']} |\n" for r in results)
    (output / 'rag_baseline_reproduced.md').write_text(text, encoding='utf-8')


def main():
    cases = load_cases()
    from .pattern_catalog import load_pattern_catalog

    patterns = load_pattern_catalog()
    if len(patterns) != 70:
        raise ValueError('Catalog must contain exactly seventy unique patterns')
    from .retrieval import create_retrieval_components, retrieve_rankings

    store, reranker = create_retrieval_components()
    results = []
    for story_id, case in cases.items():
        top15, top5 = retrieve_rankings(store, reranker, build_query(case))
        row = {'user_story_id': story_id, 'system': case[0]['system']}
        for prefix, ranking in [('top15', top15), ('top5', top5)]:
            row[prefix + '_ids'] = ';'.join(pattern['id'] for pattern in ranking)
            row[prefix + '_names'] = ';'.join(pattern['name'] for pattern in ranking)
        results.append(row)
    write_outputs(results)
    print('Wrote twelve retrieval/reranking cases to outputs/rag_baseline_reproduced.csv and outputs/rag_baseline_reproduced.md')


if __name__ == '__main__':
    main()
