# Operational amendment op1: continue after response-validation failures

This is an explicit **execution-policy amendment**, not a change to the scientific
support protocol. Protocol v1.1, instructions, verdict definitions, schema,
original inputs, prompt construction, validator, model, adaptive/high settings,
SDK, token limit, timeout, and per-pair attempt limit remain unchanged.

The original `run_experiment.py` and `protocol.py` are intentionally untouched.
The official manifest hashes those files, so editing them would break safe
resumption. The separate `continue_experiment.py` entry point reuses their
original `prepare`, `resume_state`, `judge`, locking, and provenance checks.
No comparison is weakened, hashes ignored, historical manifest rewritten, or
old source-version exemption introduced. The original entry point remains
fail-fast; this optional amendment is specified in `operational_policy.json`.

The existing official manifest remains the scientific contract. Its old fail-fast
retry-policy description is historical execution provenance; each amended
execution explicitly links to a separate operational-policy manifest explaining
the newly opted-in behavior. Results from before and after the operational
boundary share unchanged scientific prompts/configuration, but operational
conditions and failure/availability rates must be reported transparently.

## Current recovery plan

Read-only checks found:

- 840 planned pairs; 260 persisted, validated, unique judgments.
- SYS02-US01 × 051 has two invalid attempts; neither is a validated judgment.
- 579 pairs have never been attempted.

Continuation skips both the 260 validated pairs and **every already-attempted,
unvalidated pair**. It schedules only the 579 never-attempted pairs in their
original plan order. P051 consumes no third attempt just to unblock later work.
The same rule applies on later continuation invocations: failed/interrupted
pairs are deferred, never retried implicitly. Attempt limits are preserved;
exhausted pairs are also deferred and remain visible in summaries.

For a newly attempted pair, local `ResponseValidationError` causes the runner to:

1. Preserve its raw answer text(s), provider metadata, IDs, usage, and exact
   validation error in an appended failure event.
2. Leave it out of `results.jsonl`, marking it invalid/pending in the summary.
3. Continue to the next never-attempted pair with a fresh independent request.

No reference is corrected, normalized, dropped, guessed, or accepted after
validation failure. The frozen scientific validator is used without changes.
HTTP/authentication/rate-limit/transport errors, source/provenance mismatches,
and storage/journal errors still stop the operation. SDK retries remain zero.
Where journals remain readable, an interrupted operation also writes a partial
summary. A damaged/truncated journal fails closed and requires investigation;
summary generation cannot safely proceed over unreadable source evidence.

If every new response validates, this continuation would end with **839 validated
judgments and one unresolved pair**, not a completed 840-judgment scientific run.
Additional failures increase the pending count. Exhaustion of the work list is
not reported as complete coverage.

## Offline preflight and exact resume command

From the repository root, with Python 3.10+:

```bash
python -B experiments/llm_judge_support_rq1/continue_experiment.py --preflight --max-tokens 32768 --timeout 600 --output-dir experiments/llm_judge_support_rq1/outputs/claude-sonnet-5-5/v1.1/full
```

This performs read-only checks, shows counts and fingerprints, and neither
creates an API client nor changes official files.

After setting `ANTHROPIC_API_KEY` and installing the existing pinned dependency,
the explicit live continuation command for later authorization is:

```bash
python -B experiments/llm_judge_support_rq1/continue_experiment.py --full-run --continue-on-validation-error --max-tokens 32768 --timeout 600 --output-dir experiments/llm_judge_support_rq1/outputs/claude-sonnet-5-5/v1.1/full
```

Both live flags are required. There is deliberately no `--retry-unfinished`
option here. The old frozen runner remains available for separately authorized
bounded retries; continuation does not perform those retries automatically.
A no-flag invocation is offline preflight.

The historical manifest uses timeout `600.0`. Although Python compares `600`
and `600.0` as equal, their JSON encodings and hashes differ. The new CLI's timeout
default is explicitly float and `--timeout 600` parses as `600.0`, preserving the
recorded representation. No stored number or manifest is rewritten to work around
this issue. Explicit scientific configuration mismatches still reject resumption.

## Journals, operational provenance, and validation summaries

Official `manifest.json` is never rewritten. Existing JSONL bytes are retained
as prefixes; only new attempts, validated results, and execution events append.
Only existing event types are used, so the frozen resume parser remains usable.
A pair validation failure closes one execution segment with `execution_failed`;
the next segment starts before processing the next pair. The last segment can
finish with `coverage_validated=false` and `status=finished_with_pending`.
This explicitly distinguishes execution progress from scientific completeness.

Separate files are exclusively created in
`experiments/llm_judge_support_rq1/operational_outputs/<operation UUID>/`:

- `amendment.json`: exact operational policy, scientific manifest digest and raw
  hash, original scientific code hashes, new operational source hashes, all
  pre-operation journal sizes/hashes, skipped/deferred pairs, new work list,
  operation ID, and timestamp.
- `validation_summary.json` and `validation_summary.csv`: total expected,
  validated, invalid/pending, and never-attempted counts; each missing pair's
  original GPT classification, status, attempt count/limit, exact validation
  failures, failed attempt IDs, raw-response hashes, and journal line/field
  locations. JSON retains nested details; CSV uses JSON arrays in quoted cells.
- `operation_result.json`: completion/fatal status and summary hash.

Every amended execution-start event links to the immutable amendment's hash.
Later inspection checks the amendment, scientific compatibility, operational code
hashes, and unchanged historical journal prefixes. Altered operational code needs
a separately documented amendment rather than silently bypassing those checks.
Operational sidecars must accompany the official journals when transferring the
run. They are not inserted into the original scientific output directory, whose
inventory checks remain unchanged.

The two historical failures did not record the exception message itself. Their
summary messages are reproduced by replaying the frozen validator against their
preserved raw answers, and explicitly labeled `replayed_from_preserved_raw_response`.
The original failure events are never edited. New failures store the exact message
and are cross-checked against validator replay. No verdict distributions are
computed here.

A standalone, reproducible summary can be written without API calls:

```bash
python -B experiments/llm_judge_support_rq1/continue_experiment.py --summarize-only --timeout 600
```

It creates a new `operational_outputs/summary-<summary hash>/` directory and
refuses to overwrite one already present. The implementation generated a baseline
summary of the current 260 validated / 580 missing pairs, including the two P051
failure records and their original raw-response locations. No official journal
was changed to generate it.

## Separate later technical corrections

`technical_corrections.py` implements **no automatic corrections**. A reviewer
must supply a complete, explicit, approved reference-only replacement plan.
The tool accepts only pending invalid attempts whose preserved four-field answer
can be parsed. It validates the corrected reference array against the original
case but cannot establish the intended reference or its semantic adequacy.
That is the reviewer's responsibility, documented in the reason and approval.

Plan format (placeholders must be replaced through explicit review; this is not
an approved plan for P051):

```json
{
  "scientific_manifest_sha256": "<exact raw manifest file hash>",
  "corrections": [
    {
      "attempt_id": "<invalid attempt ID from summary>",
      "raw_response_sha256": "<canonical hash from summary>",
      "field": "evidence_refs",
      "replacement": ["<reviewer-approved exact original requirement identifier>"],
      "reason": "<document why this is a technical reference correction>",
      "reviewed_by": "<reviewer identity>",
      "approved_at": "<ISO timestamp with timezone>",
      "approved": true
    }
  ]
}
```

Later command, only after creating a genuinely approved plan:

```bash
python -B experiments/llm_judge_support_rq1/technical_corrections.py --run-dir experiments/llm_judge_support_rq1/outputs/claude-sonnet-5-5/v1.1/full --plan approved_reference_corrections.json --output-dir experiments/llm_judge_support_rq1/operational_outputs/reviewed-corrections-001 --max-tokens 32768 --timeout 600
```

The tool writes exclusively to a new separate directory:

- `approved_plan.json`: exact reviewed plan bytes.
- `corrected_analytical_records.jsonl`: original raw response and metadata,
  original invalid judgment, corrected analytical record, and explicit labels
  that it is **not an original validated judgment**.
- `correction_log.jsonl`: original/replacement reference arrays, reviewer,
  approval, reason, source hashes, and corrected record hash.
- `correction_manifest.json`: scientific source snapshot, plan/tool/output hashes,
  and the unchanged official validated count.

Verdict, rationale, and identified_gaps remain exactly unchanged. Extra plan fields,
verdict edits, unapproved plans, wrong hashes, duplicate/unknown attempts, invalid
replacement identifiers, no-op changes, or existing output directories fail before
writing corrections. The tool does not propose replacements, reinterpret reasons,
promote records into official results, or count corrections as completed original
judgments. Repeating the same approved plan/source snapshot into a different new
directory produces byte-identical outputs. No actual correction plan was approved
or applied to experimental responses during implementation.

## Offline tests and limits

```bash
python -B -m unittest discover -s experiments/llm_judge_support_rq1 -p 'test_*.py' -v
```

41 tests passed with the existing pinned SDK installed. The operational tests use
synthetic clients and temporary journals only. A complete clone of the current
260-result official run was continued using 579 synthetic responses: the 260
original judgments stayed byte-identical as a prefix, P051 remained at two
attempts, and only never-attempted pairs were called. This is a regression fixture,
not a real experimental continuation or evidence about support verdicts.

Tests also cover invalid-response continuation, exact errors/raw preservation,
repeat continuation without duplicates, attempt exhaustion without forced retry,
manifest/source/amendment tampering rejection, fatal transport errors, read-only
preflight without an SDK, summary determinism, exclusive outputs, explicitly
approved corrections, forbidden semantic edits, and unchanged official files.
All scientific tests remain in place and pass. No Anthropic API calls were made.

Operationally deferring failures changes the pattern of available data; pending
pairs and all attempts must remain visible in any later analysis. Technical
corrections are a separate analytical layer, not ground truth, model retries,
or human adjudication of architectural correctness. Do not silently pool corrected
analytical records with untouched original validated responses.
