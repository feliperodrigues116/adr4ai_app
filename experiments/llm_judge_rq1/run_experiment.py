"""Independent Claude replication of RQ1. Default invocation is entirely offline."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid

ORIGINAL = Path(__file__).resolve().parents[1] / "pattern_selection"
sys.path.insert(0, str(ORIGINAL))
from prepare_data import REPOSITORY_ROOT, load_patterns, load_requirement_cases
from assess_pattern import INSTRUCTIONS, ASSESSMENT_SCHEMA, build_prompt, validate_assessment

DEFAULT_MODEL = "claude-sonnet-5-5"
REASONING_EFFORT = "high"
DEFAULT_MAX_TOKENS = 32768
DEFAULT_TIMEOUT = 600
SDK_VERSION = "1.17.0"


class ResponseValidationError(ValueError):
    """Preserve response metadata for failed attempts, without saving reasoning."""

    def __init__(self, message, metadata):
        super().__init__(message)
        self.response_metadata = metadata


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def dataset():
    cases = load_requirement_cases(REPOSITORY_ROOT / "data/user_histories_orig.csv")
    patterns = load_patterns(REPOSITORY_ROOT / "catalogs/patterns")
    pairs = [(case, pattern) for case in cases for pattern in patterns]
    if len(pairs) != 840:
        raise ValueError("Expected exactly 840 independent assessments")
    # Validate every prompt even in dry-run mode.
    for case, pattern in pairs:
        build_prompt(case, pattern)
    return pairs


def request_config(model, max_tokens):
    return {"model": model, "max_tokens": max_tokens,
            "system": INSTRUCTIONS,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": REASONING_EFFORT,
                              "format": {"type": "json_schema", "schema": ASSESSMENT_SCHEMA}}}


def assess(client, case, pattern, config):
    start = time.monotonic()
    response = client.messages.create(
        **config, messages=[{"role": "user", "content": build_prompt(case, pattern)}])
    metadata = {"response_id": response.id, "response_model": response.model,
                "request_id": getattr(response, "_request_id", None),
                "stop_reason": response.stop_reason,
                "usage": response.usage.model_dump(mode="json"),
                "content_block_types": [block.type for block in response.content],
                "elapsed_seconds": time.monotonic() - start}
    try:
        # Even valid-looking JSON is rejected when the overall response is incomplete.
        if response.stop_reason != "end_turn":
            raise ValueError(f"Incomplete or refused response: {response.stop_reason}")
        if any(block.type not in {"text", "thinking", "redacted_thinking"}
               for block in response.content):
            raise ValueError("Unexpected response content block")
        text_blocks = [block for block in response.content if block.type == "text"]
        if len(text_blocks) != 1:
            raise ValueError("Expected exactly one structured text block")
        assessment = json.loads(text_blocks[0].text)
        validate_assessment(assessment, case)
        if response.model != config["model"]:
            raise ValueError(f"Returned model {response.model!r} differs from configured model")
    except ValueError as error:
        raise ResponseValidationError(str(error), metadata) from error
    return assessment, metadata


def append(path, row):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def rows(path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"Truncated journal {path}; inspect and repair manually before resuming")
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()]


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another runner holds this output directory") from error
        yield


def provenance(pairs, config, mode, sdk_version, timeout):
    return {"format_version": 2, "provider": "anthropic", "mode": mode,
            "configuration": config, "sdk_version": sdk_version, "timeout_seconds": timeout,
            "sdk_max_retries": 0, "instructions_sha256": digest(INSTRUCTIONS),
            "schema_sha256": digest(ASSESSMENT_SCHEMA), "inputs_sha256": digest(pairs),
            "prompts_sha256": digest([build_prompt(c, p) for c, p in pairs]),
            "source_sha256": {str(p.relative_to(REPOSITORY_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (ORIGINAL / "prepare_data.py", ORIGINAL / "assess_pattern.py",
                                        Path(__file__).resolve())},
            "pair_ids": [[c["user_story_id"], p["id"]] for c, p in pairs]}


def resume_state(directory, manifest, pairs):
    path = directory / "manifest.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["experiment"] != manifest:
            raise ValueError("Manifest mismatch: use the original configuration/inputs or a new directory")
    else:
        if any(directory.glob("*.jsonl")):
            raise ValueError("Journals exist without a manifest")
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"created_at": now(), "experiment": manifest}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    expected = {(c["user_story_id"], p["id"]): (c, p) for c, p in pairs}
    fingerprint = digest(manifest)
    done = set()
    for row in rows(directory / "results.jsonl"):
        key = (row["user_story_id"], row["pattern_id"])
        if key not in expected or key in done or row["experiment_sha256"] != fingerprint:
            raise ValueError("Unexpected, duplicate, or incompatible saved result")
        c, p = expected[key]
        validate_assessment({field: row[field] for field in ASSESSMENT_SCHEMA["required"]}, c)
        if (row["prompt_sha256"] != digest(build_prompt(c, p))
                or row["input_sha256"] != digest([c, p])
                or row["model"] != manifest["configuration"]["model"]
                or row["response_model"] != row["model"]
                or row["effort"] != manifest["configuration"]["output_config"]["effort"]
                or row["thinking"] != manifest["configuration"]["thinking"]
                or row["stop_reason"] != "end_turn"):
            raise ValueError("Saved result provenance mismatch")
        done.add(key)
    attempted = set()
    for row in rows(directory / "attempts.jsonl"):
        key = (row["user_story_id"], row["pattern_id"])
        if key not in expected or row["experiment_sha256"] != fingerprint:
            raise ValueError("Incompatible attempt journal")
        attempted.add(key)
    return done, attempted - done


def execute(client, directory, pairs, manifest, retry_unfinished=False):
    done, unfinished = resume_state(directory, manifest, pairs)
    if unfinished and not retry_unfinished:
        raise ValueError("Unfinished attempts exist; inspect attempts/events and use --retry-unfinished explicitly")
    fingerprint = digest(manifest)
    execution_id = str(uuid.uuid4())
    append(directory / "events.jsonl", {"event": "execution_started", "execution_id": execution_id,
           "at": now(), "python": platform.python_version(), "platform": platform.platform(),
           "argv": sys.argv, "experiment_sha256": fingerprint, "already_completed": len(done),
           "retry_unfinished": retry_unfinished})
    attempt = None
    try:
        for case, pattern in pairs:
            key = (case["user_story_id"], pattern["id"])
            if key in done:
                continue
            attempt = {"attempt_id": str(uuid.uuid4()), "execution_id": execution_id,
                       "user_story_id": key[0], "pattern_id": key[1], "started_at": now(),
                       "experiment_sha256": fingerprint,
                       "prompt_sha256": digest(build_prompt(case, pattern)),
                       "input_sha256": digest([case, pattern])}
            append(directory / "attempts.jsonl", attempt)
            assessment, metadata = assess(client, case, pattern, manifest["configuration"])
            append(directory / "results.jsonl", {**attempt, **assessment, **metadata,
                   "model": manifest["configuration"]["model"],
                   "effort": manifest["configuration"]["output_config"]["effort"],
                   "thinking": manifest["configuration"]["thinking"], "completed_at": now()})
            done.add(key)
            print(f"Validated {len(done)}/{len(pairs)}: {key[0]} × {key[1]}", flush=True)
    except BaseException as error:
        append(directory / "events.jsonl", {"event": "execution_failed", "execution_id": execution_id,
               "at": now(), "error_type": type(error).__name__,
               "attempt_id": attempt["attempt_id"] if attempt else None,
               "response_metadata": getattr(error, "response_metadata", None)})
        raise
    append(directory / "events.jsonl", {"event": "execution_completed", "execution_id": execution_id,
           "at": now(), "validated_results": len(done)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Offline validation (default)")
    mode.add_argument("--pilot", type=int, metavar="N", help="Technical pilot of 1–10 pairs")
    mode.add_argument("--full-run", action="store_true", help="Explicitly authorize all 840 API requests")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model ID (default: {DEFAULT_MODEL}); must support adaptive thinking and JSON outputs")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"Combined thinking and JSON output limit (default: {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--retry-unfinished", action="store_true")
    args = parser.parse_args(argv)
    if args.max_tokens < 1 or not 0 < args.timeout < float("inf"):
        parser.error("max-tokens and timeout must be positive and finite")
    if args.pilot is not None and not 1 <= args.pilot <= 10:
        parser.error("pilot size must be 1–10")
    if not args.model or not args.model.startswith("claude-"):
        parser.error("model must be a claude-... ID")
    config = request_config(args.model, args.max_tokens)
    pairs = dataset()
    if not args.full_run and args.pilot is None:
        print(f"Offline validation passed: {len(pairs)} pairs, original instructions/schema/prompts. No API calls or files written.")
        print(f"Instructions SHA256: {digest(INSTRUCTIONS)}")
        print(f"Prompts SHA256: {digest([build_prompt(c, p) for c, p in pairs])}")
        print(f"Configuration: model={args.model}, effort={REASONING_EFFORT}, "
              f"thinking=adaptive, max_tokens={args.max_tokens}, timeout={args.timeout}")
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("ANTHROPIC_API_KEY is required for live execution")
    mode_name = "full" if args.full_run else "technical_pilot"
    if args.pilot is not None:
        pairs = pairs[:args.pilot]
    directory = args.output_dir or Path(__file__).resolve().parent / "outputs" / args.model / mode_name
    directory = directory.resolve()
    # Never write into existing scientific inputs or the GPT experiment directory.
    allowed = Path(__file__).resolve().parent / "outputs"
    if not directory.is_relative_to(allowed):
        parser.error(f"output-dir must be inside {allowed}")
    import anthropic
    sdk_version = importlib.metadata.version("anthropic")
    if sdk_version != SDK_VERSION:
        parser.error(f"SDK {SDK_VERSION} is required; install this experiment's requirements.txt")
    manifest = provenance(pairs, config, mode_name, sdk_version, args.timeout)
    with locked(directory):
        with anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=0,
                                 timeout=args.timeout, base_url="https://api.anthropic.com") as client:
            execute(client, directory, pairs, manifest, args.retry_unfinished)


if __name__ == "__main__":
    main()
