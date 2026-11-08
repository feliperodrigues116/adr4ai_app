# RQ1 support evaluation: single technical reference correction

## Decision and coverage

The malformed reference `SYS02-US01-US01` is unambiguously attributable to the
User Story `SYS02-US01` in this specific case. A single identifier replacement
was applied through the existing `technical_corrections.py` mechanism to a
separate analytical record. No original experimental record was modified.

| Origin | Count |
| --- | ---: |
| Official API-validated judgments | 839 |
| Technically corrected analytical records | 1 |
| Total unique analytical coverage | 840 / 840 |

The official run still has 839 validated original judgments and one unresolved
pair. Its scientific manifest/events do **not** claim 840 validated original
responses. Only the separately labeled analytical dataset has complete coverage.

## Review of both original responses

Pair: `SYS02-US01 × 051` (Asynchronous pattern).
Original GPT classification: `not_applicable`.

| Attempt | Response identifier | Verdict | Identified gaps |
| --- | --- | --- | --- |
| 1 | `msg_011CgqWNf2yhXzAYoUTz9wP6` | `supported` | `[]` |
| 2 | `msg_011CgqmMm36ixiDwX58mcCin` | `supported` | `[]` |

Both return these original references:

```json
["SYS02-US01-AC02", "SYS02-US01-AC05", "SYS02-US01-US01"]
```

The rationales are **not identical**. Both justify the same substantive verdict:
AC02 variable substitution and AC05 document assembly depend on model output,
whereas the pattern's stated motivation assumes that the next business-process
step does not depend on prediction. Attempt 2 adds discussion that asynchronous
delivery could still be technically possible; that qualification is not merged
into attempt 1's rationale. Neither response is treated as a duplicate merely
because its references match. Both complete original answers and metadata are
preserved in `p051_correction_review.json` and the immutable source events.

## Why the mapping is supported

The actual User Story is labeled `[SYS02-US01]` and reads:

> Eu como usuário desejo que o sistema gere um documento inicial de acordo com o registro cadastrado no sistema de licitações

Attempt 1 explicitly says:

> The user story also asks the system to generate an initial document

Attempt 2 explicitly says:

> The story is about generating an initial document from a registered record

There is exactly one User Story in the evaluated case, and both passages refer
to its content. The malformed identifier repeats the `US01` segment of its label.
No separate `SYS02-US01-US01` requirement exists. AC02 and AC05 already have their
own correct, distinct references. The other criteria describe layout selection,
layout conformance, and language style rather than the cited User Story's request
to generate an initial document from a registered record.

Thus this is more than a lexical guess or an arbitrary choice among possible
criteria: the label structure and both rationale passages identify the same
unique User Story. The malformed reference need not be deleted as merely
redundant; its intended source can be retained with the valid existing label.
This reasoning is specific to this response/case, not a general normalization
rule for future malformed identifiers.

The minimal correction preserves order and changes only the final array element:

```json
["SYS02-US01-AC02", "SYS02-US01-AC05", "SYS02-US01"]
```

## Selected record, authorization, and audit trail

The **earliest recorded attempt (attempt 1)** was selected deterministically,
not the more favorable verdict or preferred rationale. Attempt 2 remains
corroborating review evidence and contributes no additional analytical row.

- Source attempt: `21f66b1f-300e-4732-b071-b583389f4dc7`.
- Source response: `msg_011CgqWNf2yhXzAYoUTz9wP6`.
- Correction/review timestamp: `2026-11-08T18:14:39.440580+00:00`.
- Verdict remains `supported`.
- Original rationale and `identified_gaps=[]` remain exactly unchanged.

The user explicitly authorized correction conditional on unambiguous evidence.
Codex performed that technical review and recorded this authorization basis in
the plan, reviewer identity, and review report. This is **not an independent
human/architect adjudication**. The existing tool's fixed
`human_approved_reference_correction_for_analysis_only` record-kind label is
retained; the explicit reviewer and approval-basis fields describe the actual
review process and must not be interpreted as new expert evidence.

The existing tool was used without modification. The exact reviewed plan is
`p051_reference_correction_plan.json`. The resulting correction bundle is:

`experiments/llm_judge_support_rq1/operational_outputs/p051-reference-correction-v1.1/`

It contains:

- `approved_plan.json`: exact plan bytes, explicit justification, reviewer, approval,
  timestamp, selected attempt, and original raw-response hash.
- `corrected_analytical_records.jsonl`: original raw response/metadata, original
  invalid judgment, corrected analytical judgment, response ID, and validation
  status explicitly distinguishing correction from original validation.
- `correction_log.jsonl`: original/replacement reference arrays, approval details,
  and corrected-record hash.
- `correction_manifest.json`: scientific source snapshot, tool/plan/output hashes,
  and the unchanged official count of 839 validated judgments.

No further model request or retry was made. The original 841 attempts (839
validated responses plus two failed P051 responses), all events/raw responses,
all manifests, and the blind experiments remain preserved.

## Consolidated analytical exports

- `analytical_judgments.jsonl`: all 840 pairs, each with its strict four-field
  judgment, origin label, original-validation boolean, source response/attempt ID,
  source-record hash, source location, and complete preserved source record.
- `analytical_judgments.csv`: the same scientific judgments with origin/provenance
  columns; reference/gap arrays are JSON cells and rationales remain verbatim.
- `validation_report.json`: coverage, uniqueness, schema/reference checks, 839+1
  origin counts, original official incompleteness, and correction timestamp.
- `analysis_provenance.json`: source/code/input/output hashes, including scientific
  files, the approved plan, both-response review, correction bundle, and operational
  amendment artifacts.
- `consolidate.py` and `test_consolidation.py`: reproducible offline consolidation
  and validation. They consume the explicit correction; they do not infer or apply
  another correction or make API calls.

The schema applies to each row's `judgment` object, separate from the provenance
envelope. CSV readers should import `pattern_id` as text to preserve leading
zeros. Both arrays are JSON-encoded without changing their order or values.

## Offline validation and reproduction

From the repository root, standard-library Python 3.10+ is sufficient:

```bash
python -B research_results/llm_judge_support_rq1/consolidate.py
python -B -m unittest discover -s research_results/llm_judge_support_rq1 -p 'test_*.py' -v
```

All 9 new offline tests passed. They validate:

- Both original failed answers against preserved event metadata, including distinct
  rationale texts and agreement of verdict/gaps.
- Exact one-identifier replacement, valid case membership, unchanged verdict,
  rationale, gaps, earliest-attempt selection, and correction hash/plan provenance.
- All 840 unique expected pairs, 12 stories × 70 patterns over four systems.
- 839 original validated judgments plus exactly one analytical correction, with
  no duplicated or falsely labeled original validation.
- Rejection of missing/duplicate pairs, altered source/judgment/hash, foreign
  identifiers, invalid schema values, and misleading origin labels.
- CSV round-trip preservation, unchanged scientific sources, and byte-identical
  regenerated exports.

Consolidation validates the frozen v1.1 manifest, code/input/prompt hashes, op1
amendment compatibility/prefix checks, all 839 original records, both failed
response locations, correction source and output hashes, and the full analytical
cross product. It refuses to overwrite a derived file if regenerated bytes differ.
The original correction tool also refuses to overwrite its bundle; do not rerun
it into the same directory. Reproduction consumes the preserved bundle instead.

## Interpretation limit

This resolves a technical reference-label defect for analytical use; it does not
turn the failed API response into an originally validated response or establish
architectural correctness. The response-conditioned evaluation, model verdict,
scientific protocol v1.1, and expert evaluation evidence remain unchanged. Any
later analysis must retain the original-versus-corrected distinction and report
both the official count (839) and analytical coverage (840).
