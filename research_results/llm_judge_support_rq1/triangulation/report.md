# Claude support × human expert Q5 triangulation

## Source structure, mapping and validation gate

The sole authoritative source for human Q1–Q5 ratings and comments is `research_results/expert_evaluation/expert_responses_original.csv` (SHA-256 `9cee7fc155ef767800349b07ecb72947502d75556cbf6e8a3738fb6b1a8eed5e`). It is read unchanged. The CSV is comma-delimited UTF-8, with **225 columns and four response rows**. Of these columns, **216** are 36 explicitly identified cases × five rating questions plus one optional comment; **nine** are metadata. The metadata include similar AI-experience headers differing by trailing whitespace, blank role fields, and `Column 223`. Their headers are preserved exactly and never used as rating substitutes.

`column_mapping.csv` records every source column (one-based), original full header, case identifiers, field and question text. Headers follow `[SYS01-US01|001|Q5] ...`; the story and zero-padded pattern ID are parsed directly, not inferred from position or text similarity. The system-selection column is `Qual sistema você avaliará?`. Its explicit SYS prefix links each response to the corresponding cases. Four rows cover SYS01/SYS02/SYS03/SYS04, respectively 7/12/8/9 cases. There is **one response per system, one Q5 rating per case**, with no multiple-rater aggregation or inferred participant identity. Source CSV record numbers (header = 1) identify rows reproducibly; these are not necessarily physical file lines if a comment contains newlines.

All **36 GPT-selected pairs match unambiguously**. All **180 required Q1–Q5 cells** are present with exact digit values 1–5; all 36 Q5 ratings are complete and unique. For each response, the other systems' question/comment cells are exactly empty, verified before analysis; those routing blanks are not missing assigned ratings. The 36 comments are retained exactly, including empty and whitespace-only values: 7 contain non-whitespace text and 8 are nonempty before whitespace inspection. Optional comment blanks are not imputed. No ratings are trimmed, fabricated, replaced or inferred.

The transformation is wide-to-long using explicit identifiers: `expert_ratings_long.csv` preserves all 180 raw ratings and question headers; `case_triangulation.csv` joins all 36 cases to their original Claude judgment, preserving rationale, references, gaps, record origin and response ID. `partial_support_cases.csv` isolates the 15 partial cases. `mapping_spec.json` specifies parsing, allowed values, routing rules, source hash and analysis conventions. Validation must finish successfully before any triangulation statistics are calculated or outputs written.

The existing consolidated 840-record validation is rerun read-only: scientific protocol v1.1/op1, 839 originals + one documented correction, source provenance, original GPT counts and exact scientific-text preservation. All 36 selected cases are originally API-validated judgments; the reference correction belongs to a not_applicable case and has no role in this 36-case join. Previous analysis source/output hashes are checked without regenerating prior files.

## Meaning of the measures

Q5 asks: “O padrão arquitetural utilizado como base para gerar este ADR é aplicável às necessidades expressas na história de usuário e em seus critérios de aceitação?” The form-generation code documents a 1–5 scale with endpoints **1 = Discordo totalmente**, **5 = Concordo totalmente**. Intermediate verbal anchors are not supplied in that code; numeric 2/3/4 are retained without inventing labels such as a formally defined neutral category.

Claude assessed the evidential support of the original GPT classification and rationale. Humans assessed applicability of the pattern used to generate an ADR, with requirements, pattern and ADR displayed by the form. These are related but different constructs and presentations. Their cross-tabulation is triangulation of perspectives, not a ground-truth agreement matrix. No accuracy, precision, recall, kappa, model-superiority claims, inferential tests or rescoring are made. Q1–Q4 are preserved in the case export and descriptively counted separately, but never substituted for Q5 or combined into a synthetic applicability score.

## Primary results: exact ordinal Q5 scores

Cell percentages use the Claude verdict row as denominator. The unsupported row has no observed cases and therefore undefined percentages, not 0% estimated support.

| Claude support | N | Q5=1 | Q5=2 | Q5=3 | Q5=4 | Q5=5 |
| --- | --- | --- | --- | --- | --- | --- |
| supported | 21 | 0 (0.00%) | 1 (4.76%) | 5 (23.81%) | 2 (9.52%) | 13 (61.90%) |
| partially_supported | 15 | 0 (0.00%) | 1 (6.67%) | 3 (20.00%) | 3 (20.00%) | 8 (53.33%) |
| unsupported | 0 | 0 (not defined) | 0 (not defined) | 0 (not defined) | 0 (not defined) | 0 (not defined) |

Overall Q5 distribution (1→5) is **0, 2, 8, 5, 21**. The Claude selected-case distribution remains **21 supported, 15 partially_supported, zero unsupported**.

For an explicitly supplementary descriptive grouping, Q5 scores 4–5 occur in **26/36 cases (72.22%)**, score 3 in **8/36**, and scores 1–2 in **2/36**. These bands are analyst choices, not a conversion to Claude verdicts or an assertion that all 4–5 scores are equivalent. Among supported cases, 15/21 have Q5 4–5; among partial cases, 11/15 have Q5 4–5. Row-wise raw ratings remain the primary result.

### System and story context

| System / one response row each | N | Q5=1 | Q5=2 | Q5=3 | Q5=4 | Q5=5 |
| --- | --- | --- | --- | --- | --- | --- |
| SYS01 | 7 | 0 | 0 | 1 | 1 | 5 |
| SYS02 | 12 | 0 | 0 | 4 | 1 | 7 |
| SYS03 | 8 | 0 | 0 | 0 | 1 | 7 |
| SYS04 | 9 | 0 | 2 | 3 | 2 | 2 |

`by_system.csv` and `by_story.csv` give full support × exact-Q5 cross-tabulations, including empty verdict rows. Each system has only one response, so evaluator effects cannot be separated from system effects. The same catalog patterns recur across stories and decisions are clustered within respondents and systems; 36 case ratings are not 36 independent experts.

## Individual review of the 15 partially_supported cases

The codes below reproduce the previous analysis's explicitly post-hoc qualitative coding; they are interpretations of Claude's text, not human judgments or newly adjudicated defects. Existing code definitions and annotations remain unchanged and are hashed in provenance. Full unedited Claude texts, human Q1–Q5 and comments are in the case exports. Comments were invited about the ADR generally, not specifically Q5; no causal attribution of a rating is inferred from them.

| Case | Human Q5 | Existing post-hoc codes | Original general ADR comment |
| --- | --- | --- | --- |
| SYS01-US03 × P001 | 4 | A1, A3, A4 | (no substantive comment) |
| SYS01-US03 × P013 | 5 | A1, A3, A5 | (no substantive comment) |
| SYS01-US03 × P060 | 5 | A1, A3, A7 | (no substantive comment) |
| SYS02-US01 × P002 | 5 | A1, A2, A7 | O tópico "Consequências" poderia ter mais detalhes. |
| SYS02-US02 × P001 | 5 | A1, A4, A7 | (no substantive comment) |
| SYS02-US02 × P002 | 3 | A1, A2, A5 | (no substantive comment) |
| SYS02-US02 × P060 | 3 | A1, A3 | (no substantive comment) |
| SYS02-US02 × P064 | 5 | A1, A3, A5 | (no substantive comment) |
| SYS02-US02 × P070 | 4 | A1, A7 | Não necessariamente existe a necessidade de modelos diferentes. |
| SYS02-US03 × P002 | 5 | A1, A2, A7 | (no substantive comment) |
| SYS03-US02 × P001 | 5 | A1, A4 | (no substantive comment) |
| SYS03-US03 × P050 | 5 | A6, A7 | (no substantive comment) |
| SYS04-US02 × P028 | 3 | A3, A4 | (no substantive comment) |
| SYS04-US03 × P001 | 2 | A1, A3 | (no substantive comment) |
| SYS04-US03 × P003 | 4 | A5, A6, A7 | (no substantive comment) |

The 11 partial-support cases with Q5 4–5 show that a judge's qualification of evidential support can coexist with a higher human applicability rating. They do not demonstrate that the judge was wrong or that the expert endorsed every rationale or mechanism. The remaining partial cases' ratings similarly do not independently confirm each recorded gap.

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
