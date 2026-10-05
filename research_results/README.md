# Research results

This directory contains derived artifacts for research analysis and scientific
article writing. It contains no new experimental executions. Run from any
working directory with Python 3.10 or later:

```bash
python research_results/compile_results.py
```

The command above reconstructs the original Study 1 CSVs and replaces the
ADR-enriched main CSV with its original columns. To reproduce the final
ADR-integrated datasets, run the compilation command below afterward. The
original Study 1 backup is preserved independently.

The script uses only the standard library and reconstructs both UTF-8 CSV files
deterministically from the existing sources, validating all expected counts,
identifiers, evidence ownership, catalog fields, and overlap before writing.
It does not call APIs, retrieval, embedding, or reranking models.

## Provenance

The source of truth remains:

- `data/user_histories_orig.csv`: original system purpose, user story, and acceptance criteria.
- `catalogs/patterns/P001.json` through `P070.json`: original pattern fields.
- `experiments/pattern_selection/outputs/assessments.jsonl`: official exhaustive classifications, references, and rationales.
- `experiments/rag/outputs/rag_baseline.csv`: frozen official baseline identified by `experiments/rag/README.md`; only `top5_ids` is used.

The exhaustive experiment evaluated all 70 architectural patterns independently
against all 12 user stories, producing 840 Pattern × User Story assessments:
36 applicable, 31 not_applicable, and 773 insufficient_information.
`pattern_selection_results.csv` contains only the 36 pairs classified as applicable.
`pattern_selection_summary.csv` contains all 12 stories, including SYS04-US01 with
zero applicable patterns. Eleven stories have applicable patterns.

These exhaustive LLM-based classifications are not ground truth. Expert evaluation
will be conducted in a subsequent stage. The RAG comparison is only a preliminary
baseline comparison: final Top-5 membership represents semantic retrieval/ranking,
not architectural applicability. Five applicable pairs occur in the final Top-5,
across five stories; 31 applicable pairs do not. Top-15 candidates and all ranks
are excluded from the compiled results.

## Fields and preservation

- `system_id` is derived from the stable `user_story_id`; `system_purpose` and `user_story` preserve exact original dataset text.
- `acceptance_criteria` contains every criterion for the story in dataset order, formatted as `[identifier] original text`, separated by ` | `.
- `pattern_id` retains three digits; pattern name, motivation, solution, and consequences are copied exactly from the catalog. Explicitly present empty catalog strings are preserved; missing fields or non-string values cause failure. CSV readers should import identifiers as text to retain leading zeros.
- `classification` is always `applicable` in the main CSV.
- `evidence_refs` copies the assessment's `requirement_refs` in original order, separated by semicolons.
- `evidence_text` resolves only those references to exact original User Story or Acceptance Criterion text, formatted as `[identifier] original text`, separated by ` | `. Every reference must belong to the same story.
- `rationale` preserves the model's original text exactly, including its language and wording.
- `rag_top5` is `yes` when the same pattern appears in that story's frozen final RAG Top-5, otherwise `no`.

evidence_text contains the original requirement text referenced by the model as evidence for its classification, while acceptance_criteria contains the complete set of acceptance criteria provided for the corresponding user story.

System Purpose was used only as contextual information during applicability
assessment, whereas positive evidence for an applicable classification had to
come from the User Story and/or Acceptance Criteria.

The summary records the applicable count, numerically sorted semicolon-separated
three-digit applicable pattern IDs (empty for zero patterns), and the count also
present in final RAG Top-5. Both CSV files sort stories by stable ID; the main CSV
then sorts patterns numerically. CSV quoting preserves embedded newlines and
punctuation without translating, correcting, or rewriting source content.

## ADR generation and integration

Study 1 exhaustively assessed 840 User Story × Pattern combinations. Its 36
applicable pairs became the input to ADR generation, with one independent
generation call per pair and one ADR per applicable pair. The final count is
36 ADRs, including the approved SYS01-US01 × Pattern 001 pilot. ADR status was
added deterministically as `Proposed`. A technical connection failure for
SYS04-US03 × Pattern 003 required an explicitly authorized second attempt;
the original failure remains execution metadata and is not an additional ADR.

`adr_generation_results.csv` joins the original Study 1 fields with the stored
ADR components and model, reasoning effort, and response ID metadata by
`(user_story_id, pattern_id)`. `pattern_selection_results.csv` now includes each
corresponding complete ADR in its sole new final column, `adr`, formatted in
Title, Status, Context, Decision, Consequences order. All original columns and
cell values are preserved. `pattern_selection_results_before_adr.csv` is a
byte-for-byte backup of the Study 1 result before ADR integration.

ADR text is copied exactly as generated, including language variation; it is
not translated, normalized, corrected, or rewritten during compilation. Empty
catalog fields remain empty. Attempt and failure records are excluded from
the research dataset.

Reproduce both final CSVs locally with:

```bash
python -B research_results/compile_adr_results.py
```

This standard-library script reads the preserved Study 1 backup and the 36
immutable top-level ADR JSON outputs in `experiments/adr_generation/outputs/`.
It validates all expected pairs, ADR fields, configuration, Structured Outputs
metadata, and source and prompt hashes before writing either dataset. It makes
zero API calls and does not regenerate ADRs or modify experimental artifacts.
Reruns produce byte-for-byte identical CSVs.
