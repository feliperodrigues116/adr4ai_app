# RAG-Based Retrieval Baseline

This directory contains the reproducibility package for the RAG-based retrieval baseline used in the ADR4AI study. It retrieves architectural pattern candidates from requirements using:

Requirements → BAAI/bge-small-en-v1.5 → Vector Retrieval Top-15 → BAAI/bge-reranker-base → Top-5

The dataset contains 4 systems, 12 user stories (3 per system), and 35 acceptance criteria. The catalog contains 70 architectural patterns. CSV rows are consolidated by `user_story_id`, preserving source text, IDs, and encounter order. Both story and criterion identifiers are explicitly included in each query:

```text
System Purpose:
<system_purpose>

User Story:
[<user_story_id>] <user_story>

Acceptance Criteria:
[<acceptance_criterion_id>] <acceptance_criterion>
...
```

The Top-5 results represent retrieved candidate patterns and should not be interpreted as validated architectural applicability.

No external LLM is used. No OpenAI API key is required. There is no applicability selection or ADR generation.

## Files

```text
rag/
├── README.md
├── requirements.txt
├── data/user_histories_EN.csv
├── catalogs/all-patterns.json
├── src/
│   ├── __init__.py
│   ├── pattern_catalog.py
│   ├── retrieval.py
│   └── run_baseline.py
└── outputs/
    ├── rag_baseline.csv
    └── rag_baseline.md
```

The included data, catalog, and output artifacts are unchanged copies of the official retrieval baseline. This directory can be copied into a separate repository; no parent project files are required.

## Reproduction

Use Python 3.12 (the recorded environment used 3.12.14). From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.run_baseline
```

The embedding and reranking models may need to be downloaded on first execution. Internet access may therefore be required on the first run if the models are not already cached. Model caches are stored in `data/model_cache/`; the rebuildable Chroma index is stored in `data/chroma/`. Neither generated directory is included or required beforehand. All paths are resolved within this package.

Execution replaces the two files under `outputs/`. The CSV contains one row per story with these columns, in order:

```text
user_story_id,system,top15_ids,top15_names,top5_ids,top5_names
```

Multiple pattern IDs and names are separated by semicolons with matching order. Top-15 preserves vector ranking; Top-5 preserves reranking order.

## Implementation and reproducibility

The extracted catalog loader preserves the original fields, including concatenated JSON records. Document construction, catalog fingerprinting, index compatibility checks, and Chroma `similarity_search_with_score` follow the original ingestion/retrieval code. Chroma uses its existing default similarity configuration; no distance metric is overridden. The FastEmbed LangChain wrapper uses the same underlying `TextEmbedding` model and two threads as the recorded experiment. The cross-encoder also uses two threads. Reranking sorts descending finite scores, breaking ties by vector rank, and retains five results.

Direct dependencies and the numerical runtimes are pinned to installed versions from the execution environment. Transitive dependencies are not fully locked. Model identifiers are fixed, but upstream model download revisions are not pinned. A rebuilt approximate vector index or different numerical hardware may affect ranking; exact agreement with the included CSV must be checked in the later isolated reproduction test. The pinned SQLite compatibility wheel should be checked for availability on the target platform.

Only structural validation was performed when assembling this package. No models, experiment runs, dependency installations, or API calls were executed. An isolated end-to-end reproduction test remains pending.
