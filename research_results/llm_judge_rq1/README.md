# RQ1 GPT–Claude comparison

This directory contains a reproducible, offline comparison of the frozen
840-pair GPT experiment and the official 840-pair Claude Sonnet 5.5 experiment.
It reads neither the RAG baseline nor the architects' Q5 evaluations.

Run from the repository root, with Python 3.10+ and no third-party packages:

```bash
python -B research_results/llm_judge_rq1/analyze.py
python -B -m unittest discover -s research_results/llm_judge_rq1 -p 'test_*.py' -v
```

The official Claude run is discovered from its full-mode, Sonnet-model manifest;
pilots are excluded. Multiple candidates fail rather than silently choosing a run.
If needed, select the official source explicitly:

```bash
python -B research_results/llm_judge_rq1/analyze.py --claude-results experiments/llm_judge_rq1/outputs/claude-sonnet-5-5/full/results.jsonl
```

Analysis completes all mandatory coverage, schema, reference, manifest, source,
configuration, prompt/input hash, response, attempt, and event checks before
writing reports. It never calls the runner's execution/resume mutation helpers,
imports an LLM SDK, or makes API calls. Both experimental source trees and all
original inputs remain unchanged. Hashes of those files are recorded for audit.

| Artifact | Contents |
| --- | --- |
| `report.md` | Findings, matrix, metrics/formulas, all positive-selection differences, story/system tables, and methodological limits |
| `validation.md` | Mandatory validation checks and official Claude execution audit |
| `pair_comparison.csv` | All 840 pairs with both classifications, original reference arrays, and verbatim rationales |
| `agreement_matrix.csv` | 3×3 matrix; GPT rows and Claude columns |
| `overall_metrics.csv` | Overall agreement, marginal-based expected agreement, nominal kappa, positive overlap, and counts |
| `agreement_by_gpt_classification.csv` | Diagonal/GPT row count for each original category |
| `gpt_selected_not_claude_applicable.csv` | All GPT-applicable pairs Claude did not classify as applicable |
| `claude_applicable_not_gpt_selected.csv` | All Claude-applicable pairs GPT did not classify as applicable |
| `by_user_story.csv`, `by_system.csv`, `by_pattern.csv` | Counts, category marginals, agreement, kappa, positive overlap, and key disagreement transitions by group |
| `analysis_provenance.json` | Raw input/code hashes, report hashes, and validation/execution metadata |

Fractions in CSVs are 0–1, not percentages. Blank ratios are undefined because
the denominator is zero. The Markdown report renders percentages and explicit
“undefined” labels. Pattern IDs must be imported as strings to preserve leading
zeros. Reference arrays and acceptance criteria are JSON within CSV cells;
parsing them preserves their original values/order. UTF-8 CSV quoting preserves
Unicode, embedded newlines, commas, quotes, and rationale whitespace.

The unit is a **User Story × Pattern pair**, not a distinct catalog pattern:
GPT's 36 selections span 17 distinct pattern IDs. Positive overlap uses these
pairs and leaves all three original categories intact in the primary analysis.
No ground-truth, error, accuracy, precision/recall, or superiority claim follows
from either agreement or disagreement. The fixed corpus, repeated stories and
patterns, class imbalance, asymmetric historical provenance, and one outcome
per model/pair limit inference. See `report.md` for the full discussion.

Outputs are deterministic for unchanged inputs/code. Tests include known-matrix
metrics, degenerate denominators, frozen-corpus reconciliation, invalid and
incomplete input rejection, Claude provenance tampering rejection, ambiguous
run discovery, exact text round trips, group totals, repeated byte-identical
reproduction, and unchanged input hashes. Generated report hashes exclude the
provenance file itself to avoid circular hashing. Tests may write only temporary
fixtures/derived reports; no model calls occur.
