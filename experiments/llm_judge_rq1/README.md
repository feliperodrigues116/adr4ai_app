# Independent Claude assessment of ADR4AI RQ1

This runner replicates the original 12 User Stories × 70 patterns (840 assessments).
It imports `INSTRUCTIONS`, `build_prompt`, `ASSESSMENT_SCHEMA`, and
`validate_assessment` directly from `../pattern_selection/assess_pattern.py` and
uses the original loaders from `../pattern_selection/prepare_data.py`. It reads
only `data/user_histories_orig.csv` and `catalogs/patterns/P*.json` as scientific
inputs. Only the original five pattern fields reach Claude. No GPT output files,
classifications, rationales, comparisons, or RAG baseline are read or used.
Each request has a fresh, single user message; no conversation history is shared.

## Offline checks

From the repository root (no API key or network required):

```bash
python experiments/llm_judge_rq1/run_experiment.py
python -m unittest discover -s experiments/llm_judge_rq1 -p 'test_*.py' -v
```

Default execution, or explicit `--dry-run`, validates all 840 prompts without
importing Anthropic, creating a client, or writing experiment output.
The core tests also run without the SDK. Install the pinned dependency below to
include the SDK serialization/parsing test, which uses an in-memory mock HTTP
transport and never connects to an API. Without the SDK that one test is skipped.

## Explicit live execution

Create a dedicated environment and install the verified SDK (Python 3.10+):

```bash
python -m venv /tmp/adr4ai-rq1-venv
source /tmp/adr4ai-rq1-venv/bin/activate
python -m pip install -r experiments/llm_judge_rq1/requirements.txt
python -m unittest discover -s experiments/llm_judge_rq1 -p 'test_*.py' -v
python experiments/llm_judge_rq1/run_experiment.py --dry-run
```

Set `ANTHROPIC_API_KEY` in your environment before either live command. The
default model is now `claude-sonnet-5-5`, selected for lower per-token cost than
the previous Fable 5.1 model. Anthropic lists Sonnet at $2/million input and
$10/million output tokens; see the [model specifications and pricing](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
The scientific protocol is unchanged. Requests explicitly use
`thinking={"type": "adaptive"}` and `output_config.effort="high"`, alongside the
unchanged original three-field JSON schema in `output_config.format`.
`--model` remains available for a deliberately selected compatible model.
There is no model fallback or automatic configuration downgrade. The returned
model ID must equal the requested ID; use a concrete model ID, not a moving alias.

Technical pilot (three requests, first three pairs in original input order):

```bash
python experiments/llm_judge_rq1/run_experiment.py --pilot 3 --model claude-sonnet-5-5 --max-tokens 32768 --timeout 600
```

Full independent experiment (all 840 pairs, including new assessments for the
pilot pairs; pilot results are never promoted into the official run):

```bash
python experiments/llm_judge_rq1/run_experiment.py --full-run --model claude-sonnet-5-5 --max-tokens 32768 --timeout 600
```

Pilot sizes are limited to 1–10. The pilot tests API delivery and validation,
not scientific outcomes. Do not use pilot classifications to tune the scientific
instructions. Live execution requires a live mode; omitting `--model` uses the
recorded `claude-sonnet-5-5` default. Effort is fixed at `high` in this protocol.

## Persistence and resumption

Default directories are `outputs/<model>/technical_pilot/` and
`outputs/<model>/full/` next to this README. For the new default these are
`outputs/claude-sonnet-5-5/technical_pilot/` and
`outputs/claude-sonnet-5-5/full/`. `--output-dir` may select a new directory inside this experiment's
`outputs/` tree. Pilot and full manifests are incompatible even when an explicit
directory is supplied. Generated outputs are ignored by Git.

The completed Fable 5.1 technical pilot remains unchanged in the legacy
`outputs/technical_pilot/` directory, including its original manifest, hashes,
results, attempts, and events. It is historical evidence from the earlier runner
version. Nothing is renamed, migrated, copied into the Sonnet experiment, or
rewritten to match the updated runner source hash. Its recorded source hash
identifies the code used at that time; it is expected to differ from the updated
runner. Even with `--model claude-fable-5-1`, this version defaults to the new
model-specific directory and does not resume or modify that legacy pilot.
Explicitly targeting the old directory fails the existing manifest check.
New Sonnet pilot and official results are collected independently in separate
directories; a model change never reuses another model's validated results.

- `manifest.json`: exact model/API configuration, SDK version, timeout, disabled
  SDK retries, instructions/schema/input/prompt SHA256 hashes, ordered pair IDs,
  runner and original loader/assessment source hashes, creation timestamp.
- `results.jsonl`: one fsynced record immediately after each validated assessment,
  retaining `classification`, `requirement_refs`, `rationale` as top-level fields,
  pair IDs, input/prompt hashes, requested and actual response model IDs, effort,
  thinking configuration, response/request IDs, content block types, token usage,
  timestamps, elapsed time, execution and attempt IDs, and manifest hash.
- `attempts.jsonl`: fsynced intent record before each API call.
- `events.jsonl`: execution start/completion/failure metadata, environment,
  arguments, and explicit retry decisions. Rejected API responses retain
  response/request IDs, actual model, stop reason, usage, timing, block types,
  and attempt ID here. API keys and thinking content are not recorded.

Repeat the exact pilot/full command to resume. All saved assessments are
revalidated with the original validator before skipping completed pairs.
Configuration, SDK, code, input, prompt, or mode changes reject resumption;
choose a new output directory for a deliberately different experiment.
The adaptive-thinking configuration uses manifest format version 2. Older
manifests/results are intentionally incompatible; they are not migrated or reused.
A process lock prevents simultaneous writers to the same directory.

Errors fail closed: no repairing model output, retrying automatically, treating
errors as classifications, or accepting truncated/refused responses. Completed
validated records survive failures. An attempted pair without a validated result
requires inspection, then explicit `--retry-unfinished` on the same command.
This may repeat a request already processed/billed by Anthropic; exactly-once
remote execution cannot be guaranteed across network/process failures.
A truncated JSONL journal is rejected and must be inspected/repaired manually;
the runner never silently discards bytes. Failed raw model responses are not
stored as scientific results. Error types and attempt identifiers remain in the
journals; API exceptions also surface on the console.

## API-specific differences

Scientific instruction and prompt strings and classification schema are unchanged.
Delivery uses Anthropic's Messages API: original `INSTRUCTIONS` in `system`,
original prompt in a single `messages` user entry, original schema in
`output_config.format` with `type: json_schema`. This replaces OpenAI Responses
`instructions`, `input`, and named strict `text.format`; no tool or extra prose
instructions are added. See the [Anthropic structured outputs documentation](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

Claude Sonnet 5.5 supports adaptive thinking, including the explicit
`thinking={"type": "adaptive"}` configuration. The API accepts `high` effort in
`output_config` together with JSON `format`. No legacy `budget_tokens`, sampling
overrides, forced tool calls, or beta headers are sent. See the
[Sonnet 5.5 documentation](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
Using `high` in both providers does not establish equivalent reasoning budgets.

The default `max_tokens` is 32768, increased from 2048 to leave room for both
adaptive reasoning and the brief JSON answer. Anthropic counts reasoning and
answer tokens against this shared cap; see
[thinking cost controls](https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost).
This is a generous initial cap for this task, not a guarantee that every response
will finish. Overrides apply to the whole run and are recorded. Any exhaustion
fails even if the response text looks like complete JSON. There is no automatic
budget increase or effort reduction. If the technical pilot exhausts the cap,
select a larger cap in a new pilot directory before fixing the official protocol.

Adaptive responses may include `thinking` or `redacted_thinking` blocks before
the answer. The parser selects exactly one `text` block by type, decodes only
that block, and applies the original validator without changes. Thinking blocks
are not assessment evidence and are never stored or sent to another request.
Unexpected content types, missing/multiple text blocks, model mismatch, invalid
assessments, refusals, and every stop reason other than `end_turn` fail closed.

SDK retries are disabled. Timeout defaults to 600 seconds to accommodate adaptive
reasoning. The official Anthropic endpoint is explicit; base-URL environment
overrides are not used. SDK version and all explicit request settings are recorded.

## Configuration review verification

`requirements.txt` pins `anthropic==1.17.0`, the current SDK inspected during this
review. Its `Messages.create` signature accepts `thinking` and `output_config`;
`OutputConfigParam` supports both `effort` and JSON `format`, and
`ThinkingConfigAdaptiveParam` supports `type="adaptive"`. Live mode rejects a
different installed SDK version before creating a client. Updating the pin is
a deliberate protocol change requiring another offline compatibility check.

All 18 tests passed with that SDK installed in an isolated temporary environment,
including an actual SDK request serialized into a mock transport and a synthetic
adaptive-thinking response parsed through the SDK. All 840 original pairs and
prompts validated offline. Original instructions and prompt hashes match the
initial implementation. Pilot/full directory isolation, mode mismatch rejection,
explicit model overrides, incomplete responses, and reasoning/model provenance
checks are covered, including rejection of a Sonnet resume against a Fable
manifest without changing its files. No Claude API requests, Sonnet pilot, or
official run were executed during this update. Sonnet account/model access and
live completion within the token cap remain unverified until the explicitly
invoked Sonnet technical pilot.
