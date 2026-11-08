# ADR4AI RQ1: independent GPT–Claude classification comparison

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
involve 17 distinct pattern IDs; Claude's 30 selected pairs involve 16.
Repeated pattern IDs across different stories are not collapsed in overlap metrics.

## Three-category agreement matrix

Rows are GPT; columns are Claude. Categories retain their original meanings.

| GPT / Claude | applicable | not_applicable | insufficient_information |
| --- | --- | --- | --- |
| applicable | 21 | 4 | 11 |
| not_applicable | 0 | 26 | 5 |
| insufficient_information | 9 | 498 | 266 |

GPT marginals: 36 applicable, 31 not_applicable,
773 insufficient_information. Claude marginals:
30 applicable, 528 not_applicable,
282 insufficient_information.

Overall exact agreement is **313/840 = 37.26%**;
there are 527 disagreements. Cohen's unweighted nominal kappa
is **0.058460**, with expected agreement from empirical marginals
33.37%.

| GPT classification | GPT count | Same classification | Conditional agreement |
| --- | --- | --- | --- |
| applicable | 36 | 21 | 58.33% |
| not_applicable | 31 | 26 | 83.87% |
| insufficient_information | 773 | 266 | 34.41% |

The dominant difference is GPT insufficient_information → Claude not_applicable:
498 pairs, 94.50% of all disagreements.
The reverse direction occurs in 5 pairs.
This describes different decisions about evidence sufficiency/non-applicability;
it does not establish which decisions are justified. Rationales are exported
verbatim for subsequent independent review; no automated thematic coding or
adjudication is claimed here.

## Positive-selection overlap

Claude also classified **21 of GPT's 36 selected pairs** as applicable
(58.33%). Conversely,
21/30 Claude-selected pairs were also GPT-selected
(70.00%).

- Intersection: 21 pairs; union: 45 pairs.
- Jaccard overlap = intersection/union = **46.67%**.
- Symmetric positive Dice agreement = 2 × intersection/(GPT applicable + Claude applicable)
  = **63.64%**.
- GPT applicable but Claude not applicable-selected: 15 pairs.
- Claude applicable but GPT not applicable-selected: 9 pairs.

Here “not applicable-selected” includes both original non-selected categories;
they remain distinct in the matrix, exports, and pair lists below.

### GPT-selected pairs Claude did not classify as applicable

| Story | Pattern | Name | GPT classification | Claude classification |
| --- | --- | --- | --- | --- |
| SYS01-US02 | 003 | Client-Server | applicable | insufficient_information |
| SYS01-US03 | 013 | Fluid Architecture | applicable | not_applicable |
| SYS01-US03 | 060 | Parameter-based serving pattern | applicable | not_applicable |
| SYS02-US01 | 002 | Pipes and Filters | applicable | insufficient_information |
| SYS02-US01 | 004 | Model-View-Controller (MVC) | applicable | insufficient_information |
| SYS02-US02 | 002 | Pipes and Filters | applicable | insufficient_information |
| SYS02-US02 | 060 | Parameter-based serving pattern | applicable | insufficient_information |
| SYS02-US02 | 064 | Daisy Architecture | applicable | insufficient_information |
| SYS02-US02 | 070 | Condition-based-serving pattern | applicable | insufficient_information |
| SYS03-US02 | 050 | Synchronous pattern | applicable | insufficient_information |
| SYS03-US03 | 050 | Synchronous pattern | applicable | insufficient_information |
| SYS04-US02 | 028 | End-To-End Tests | applicable | not_applicable |
| SYS04-US03 | 001 | Encapsulating ML Models within Rule-based Safeguards | applicable | not_applicable |
| SYS04-US03 | 003 | Client-Server | applicable | insufficient_information |
| SYS04-US03 | 014 | Distinguish Business Logic from<br>ML Model | applicable | insufficient_information |

### Claude-applicable pairs GPT did not select

| Story | Pattern | Name | GPT classification | Claude classification |
| --- | --- | --- | --- | --- |
| SYS02-US01 | 001 | Encapsulating ML Models within Rule-based Safeguards | insufficient_information | applicable |
| SYS02-US02 | 028 | End-To-End Tests | insufficient_information | applicable |
| SYS02-US03 | 005 | Multi-Layer Pattern | insufficient_information | applicable |
| SYS02-US03 | 050 | Synchronous pattern | insufficient_information | applicable |
| SYS03-US01 | 003 | Client-Server | insufficient_information | applicable |
| SYS03-US03 | 014 | Distinguish Business Logic from<br>ML Model | insufficient_information | applicable |
| SYS04-US02 | 046 | Adapter Pattern | insufficient_information | applicable |
| SYS04-US03 | 046 | Adapter Pattern | insufficient_information | applicable |
| SYS04-US03 | 053 | Microservice horizontal pattern | insufficient_information | applicable |

Full original references and rationales are in the corresponding difference CSVs
and [pair_comparison.csv](pair_comparison.csv).

## Agreement by user story

| user_story_id | Pairs | Agree | Disagree | Agreement | GPT applicable | Claude applicable | Both applicable | Positive Jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SYS01-US01 | 70 | 34 | 36 | 48.57% | 3 | 3 | 3 | 100.00% |
| SYS01-US02 | 70 | 35 | 35 | 50.00% | 1 | 0 | 0 | 0.00% |
| SYS01-US03 | 70 | 10 | 60 | 14.29% | 3 | 1 | 1 | 33.33% |
| SYS02-US01 | 70 | 33 | 37 | 47.14% | 5 | 4 | 3 | 50.00% |
| SYS02-US02 | 70 | 32 | 38 | 45.71% | 5 | 2 | 1 | 16.67% |
| SYS02-US03 | 70 | 23 | 47 | 32.86% | 2 | 4 | 2 | 50.00% |
| SYS03-US01 | 70 | 45 | 25 | 64.29% | 1 | 2 | 1 | 50.00% |
| SYS03-US02 | 70 | 14 | 56 | 20.00% | 5 | 4 | 4 | 80.00% |
| SYS03-US03 | 70 | 21 | 49 | 30.00% | 2 | 2 | 1 | 33.33% |
| SYS04-US01 | 70 | 21 | 49 | 30.00% | 0 | 0 | 0 | undefined |
| SYS04-US02 | 70 | 12 | 58 | 17.14% | 2 | 2 | 1 | 33.33% |
| SYS04-US03 | 70 | 33 | 37 | 47.14% | 7 | 6 | 4 | 44.44% |

Exact agreement varies from 14.29%
(SYS01-US03, 10/70) to
64.29%
(SYS03-US01, 45/70).
Selection overlap and exact three-category agreement answer different questions:
SYS01-US01 shares all three applicable selections, but still has 36 disagreements
among its other 67 pairs. SYS04-US01 has no applicable selections from either
model, so positive Jaccard is undefined even though 49 category disagreements
remain. These are descriptive within-corpus observations, not evidence of
different system-level accuracy.

## Agreement by system

| system | Pairs | Agree | Disagree | Agreement | GPT applicable | Claude applicable | Both applicable | Positive Jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| System_01 | 210 | 79 | 131 | 37.62% | 7 | 4 | 4 | 57.14% |
| System_02 | 210 | 88 | 122 | 41.90% | 12 | 10 | 6 | 37.50% |
| System_03 | 210 | 80 | 130 | 38.10% | 8 | 8 | 6 | 60.00% |
| System_04 | 210 | 66 | 144 | 31.43% | 9 | 8 | 5 | 41.67% |

Group CSVs additionally include kappa, category marginals, positive overlaps,
and the dominant non-selected-category transition counts. Per-pattern metrics
across 12 stories are in [by_pattern.csv](by_pattern.csv). A blank/undefined
positive overlap means its denominator is zero, not perfect agreement.

## Definitions and methodological limits

1. **Overall agreement** = diagonal count/N. It weights all pairs equally and
   can hide class-specific behavior under class imbalance. Here GPT assigned
   insufficient_information to 92.02% of pairs;
   Claude assigned not_applicable to 62.86%.
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
