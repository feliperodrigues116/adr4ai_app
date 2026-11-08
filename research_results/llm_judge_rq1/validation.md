# Validation audit

Status: **PASS**. All checks are mandatory; a mismatch aborts analysis.

- GPT: 840 unique pairs; model gpt-6-sol, effort high.
- Claude: 840 unique pairs; mode full; actual/requested model claude-sonnet-5-5;
  effort high; adaptive thinking; max_tokens 32768;
  SDK 1.17.0; timeout 600.0 seconds;
  SDK retries 0.
- Same 12 stories × 70 patterns; four systems; three stories per system;
  35 acceptance criteria. Complete cross product verified in both datasets.
- Original classification schema constraints and reference ownership validated.
- Full original instruction/schema/input/prompt/runner/loader hashes verified.
- Each Claude result matches its reserved attempt and experiment fingerprint;
  response IDs are unique; model/configuration/stop reason/block types and usage
  are checked. All 840 accepted results have stop_reason=end_turn.
- Final full-run execution event records 840 validated results.
- Official input: `experiments/llm_judge_rq1/outputs/claude-sonnet-5-5/full/results.jsonl`.
- GPT input: `experiments/pattern_selection/outputs/assessments.jsonl`.
- Claude execution audit:
  - executions: 1
  - attempts: 840
  - pairs_with_multiple_attempts: 0
  - attempts_without_validated_result: 0
  - failure_events: 0
  - executions_without_terminal_event: 0
  - explicit_retry_executions: 0
  - incomplete_response_failure_events: 0
- Pilots are excluded by mode/model selection. Analysis never calls the runner's
  mutation or execution helpers, creates clients, or imports an LLM SDK.
- GPT lacks equivalent historical response/hash metadata; retrospective execution
  provenance is correspondingly limited (see report.md).
