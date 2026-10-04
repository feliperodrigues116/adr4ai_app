"""Preflight by default; use --run only when ready to launch the official experiment."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

from assess_pattern import (
    CLASSIFICATIONS, MODEL, REASONING_EFFORT, assess_pattern, build_prompt,
    validate_assessment,
)
from prepare_data import REPOSITORY_ROOT, load_patterns, load_requirement_cases


OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "outputs"
MAX_ATTEMPTS = 3
RECORD_FIELDS = {
    "user_story_id", "pattern_id", "model", "reasoning_effort",
    "classification", "requirement_refs", "rationale",
}


def read_jsonl(path):
    """Reject malformed existing files rather than silently discarding records."""
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                if not line.endswith("\n"):
                    raise ValueError("missing final newline; check for an interrupted JSONL write")
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("expected a JSON object")
            except ValueError as error:
                raise ValueError(f"{path}, line {line_number}: {error}") from error
            records.append(record)
    return records


def load_assessments(path, cases, patterns):
    """Validate official records and stop on invalid metadata or duplicate pairs."""
    cases_by_id = {case["user_story_id"]: case for case in cases}
    pattern_ids = {pattern["id"] for pattern in patterns}
    completed = {}
    for line_number, record in enumerate(read_jsonl(path), start=1):
        try:
            if set(record) != RECORD_FIELDS:
                raise ValueError("unexpected or missing assessment fields")
            story_id, pattern_id = record["user_story_id"], record["pattern_id"]
            if not isinstance(story_id, str) or story_id not in cases_by_id:
                raise ValueError("unknown user_story_id")
            if not isinstance(pattern_id, str) or pattern_id not in pattern_ids:
                raise ValueError("unknown pattern_id")
            if record["model"] != MODEL or record["reasoning_effort"] != REASONING_EFFORT:
                raise ValueError("assessment model configuration does not match the experiment")
            validate_assessment(
                {field: record[field] for field in ("classification", "requirement_refs", "rationale")},
                cases_by_id[story_id],
            )
            pair = (story_id, pattern_id)
            if pair in completed:
                raise ValueError(f"duplicate assessment pair: {pair}")
            completed[pair] = record
        except ValueError as error:
            raise ValueError(f"{path}, line {line_number}: {error}") from error
    return completed


def load_failures(path, expected_pairs, completed):
    """Recover unresolved attempt counts, including attempts interrupted mid-request."""
    failures = {}
    fields = {"user_story_id", "pattern_id", "attempts", "error_type", "error_message"}
    for line_number, record in enumerate(read_jsonl(path), start=1):
        location = f"{path}, line {line_number}"
        if set(record) != fields:
            raise ValueError(f"{location}: unexpected or missing failure fields")
        if not all(isinstance(record[field], str) for field in (
            "user_story_id", "pattern_id", "error_type", "error_message"
        )):
            raise ValueError(f"{location}: failure identifiers and errors must be strings")
        pair = (record["user_story_id"], record["pattern_id"])
        if pair not in expected_pairs or pair in failures:
            raise ValueError(f"{location}: unexpected or duplicate failure pair {pair}")
        if type(record["attempts"]) is not int or not 1 <= record["attempts"] <= MAX_ATTEMPTS:
            raise ValueError(f"{location}: invalid attempt count")
        failures[pair] = record
    return {pair: record for pair, record in failures.items() if pair not in completed}


def write_failures(path, failures):
    """Atomically persist unresolved failures and reserved attempts."""
    temporary = path.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for record in failures.values():
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def load_inputs():
    cases = load_requirement_cases(REPOSITORY_ROOT / "data/user_histories_orig.csv")
    patterns = load_patterns(REPOSITORY_ROOT / "catalogs/patterns")
    expected_ids = [f"{number:03d}" for number in range(1, 71)]
    if sorted(pattern["id"] for pattern in patterns) != expected_ids:
        raise ValueError("Pattern IDs must be exactly 001 through 070")
    patterns = sorted(patterns, key=lambda pattern: int(pattern["id"]))
    for pattern in patterns:
        build_prompt(cases[0], pattern)
    if len(cases) * len(patterns) != 840:
        raise ValueError("Expected exactly 12 × 70 = 840 combinations")
    return cases, patterns


def preflight(cases, patterns, output_directory):
    """Validate inputs and resume files without creating outputs or making requests."""
    expected_pairs = {(case["user_story_id"], pattern["id"]) for case in cases for pattern in patterns}
    completed = load_assessments(output_directory / "assessments.jsonl", cases, patterns)
    failures = load_failures(output_directory / "failures.jsonl", expected_pairs, completed)
    key_available = bool(os.environ.get("OPENAI_API_KEY"))
    print("Pattern Selection preflight")
    print(f"Systems: {len({case['system'] for case in cases})}")
    print(f"User stories: {len(cases)}")
    print(f"Acceptance criteria: {sum(len(case['acceptance_criteria']) for case in cases)}")
    print(f"Patterns: {len(patterns)}")
    print(f"Expected assessments: {len(expected_pairs)}")
    print(f"Existing valid assessments: {len(completed)}")
    print(f"Remaining assessments: {len(expected_pairs) - len(completed)}")
    print(f"Unresolved failures already at attempt limit: {sum(record['attempts'] == MAX_ATTEMPTS for record in failures.values())}")
    print(f"Model: {MODEL}")
    print(f"Reasoning effort: {REASONING_EFFORT}")
    print("Structured Output: strict, unchanged schema")
    print("Execution: sequential, one user story × one pattern per request")
    print("Order: CSV story order; ascending pattern IDs")
    print(f"First pair: {cases[0]['user_story_id']} × {patterns[0]['id']}")
    print(f"Last pair: {cases[-1]['user_story_id']} × {patterns[-1]['id']}")
    print(f"Maximum attempts per pair: {MAX_ATTEMPTS}; SDK retries disabled")
    print("Pilot test_assessment.json: excluded")
    print(f"Output directory: {output_directory}")
    print(f"OPENAI_API_KEY available: {'yes' if key_available else 'no'}")
    print(f"Preflight status: {'READY' if key_available else 'BLOCKED: missing OPENAI_API_KEY'}")
    return key_available


def write_selected_patterns(directory, cases, patterns, completed):
    """Write only applicable pattern references after the completeness check passes."""
    directory.mkdir(parents=True, exist_ok=True)
    for case in cases:
        story_id = case["user_story_id"]
        selected = []
        for pattern in patterns:
            record = completed[(story_id, pattern["id"])]
            if record["classification"] == "applicable":
                selected.append({field: record[field] for field in (
                    "pattern_id", "requirement_refs", "rationale"
                )})
        result = {"user_story_id": story_id, "selected_patterns": selected}
        path = directory / f"{story_id}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


def run_experiment(client, cases, patterns, output_directory):
    """Append validated results; retry unresolved pairs in up to three ordered passes."""
    assessments_path = output_directory / "assessments.jsonl"
    failures_path = output_directory / "failures.jsonl"
    pairs = [(case, pattern) for case in cases for pattern in patterns]
    expected_pairs = {(case["user_story_id"], pattern["id"]) for case, pattern in pairs}
    completed = load_assessments(assessments_path, cases, patterns)
    failures = load_failures(failures_path, expected_pairs, completed)
    output_directory.mkdir(parents=True, exist_ok=True)
    write_failures(failures_path, failures)
    with assessments_path.open("a", encoding="utf-8") as output:
        for pass_number in range(1, MAX_ATTEMPTS + 1):
            print(f"Pass {pass_number}/{MAX_ATTEMPTS}", flush=True)
            for index, (case, pattern) in enumerate(pairs, start=1):
                pair = (case["user_story_id"], pattern["id"])
                if pair in completed:
                    continue
                attempts = failures.get(pair, {}).get("attempts", 0)
                if attempts >= MAX_ATTEMPTS:
                    continue
                # Reserve the attempt before calling: interrupted requests still count.
                failures[pair] = {
                    "user_story_id": pair[0], "pattern_id": pair[1],
                    "attempts": attempts + 1,
                    "error_type": "InterruptedAttempt",
                    "error_message": "Attempt started; no validated assessment recorded",
                }
                write_failures(failures_path, failures)
                try:
                    record = assess_pattern(client, case, pattern)
                except Exception as error:
                    message = " ".join(str(error).split())
                    api_key = os.environ.get("OPENAI_API_KEY")
                    if api_key:
                        message = message.replace(api_key, "[REDACTED]")
                    message = message[:300]
                    failures[pair].update(error_type=type(error).__name__, error_message=message)
                    write_failures(failures_path, failures)
                    print(f"[{index}/{len(pairs)}] {pair[0]} × {pair[1]} -> ERROR", flush=True)
                    continue
                # Keep write failures fatal: continuing could duplicate a partially written result.
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
                completed[pair] = record
                del failures[pair]
                write_failures(failures_path, failures)
                print(f"[{index}/{len(pairs)}] {pair[0]} × {pair[1]} -> {record['classification']}", flush=True)
            if len(completed) == len(expected_pairs):
                break

    # Re-read the official file to check every record, reference, and pair on disk.
    completed = load_assessments(assessments_path, cases, patterns)
    complete = set(completed) == expected_pairs
    counts = Counter(record["classification"] for record in completed.values())
    stories = {record["user_story_id"] for record in completed.values()}
    counts_by_story = Counter(record["user_story_id"] for record in completed.values())
    complete = complete and len(stories) == 12 and all(
        counts_by_story[case["user_story_id"]] == 70 for case in cases
    )
    write_failures(failures_path, failures)
    selected_directory = output_directory / "selected_patterns"
    if complete:
        write_selected_patterns(selected_directory, cases, patterns, completed)

    print("\nExperiment summary")
    print(f"Expected assessments: {len(expected_pairs)}")
    print(f"Valid assessments: {len(completed)}")
    for classification in CLASSIFICATIONS:
        print(f"{classification}: {counts[classification]}")
    print(f"Unresolved failures: {len(expected_pairs - set(completed))}")
    print("Duplicate pairs: 0")
    print(f"Experiment status: {'COMPLETE' if complete else 'INCOMPLETE'}")
    print(f"Assessments: {assessments_path}")
    print(f"Failures: {failures_path}")
    if complete:
        print(f"Selected patterns: {selected_directory}")
    return complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Launch official API assessments after preflight")
    args = parser.parse_args()
    cases, patterns = load_inputs()
    ready = preflight(cases, patterns, OUTPUT_DIRECTORY)
    if not args.run:
        print("Preflight only: no API requests made")
        return 0 if ready else 1
    if not ready:
        raise ValueError("OPENAI_API_KEY is not set; no API requests made")
    from openai import OpenAI

    # Lock the official file so two launched runners cannot assess the same pair.
    import fcntl

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_DIRECTORY / "assessments.jsonl").open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another official experiment runner is already active") from error
        with OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0) as client:
            complete = run_experiment(client, cases, patterns, OUTPUT_DIRECTORY)
    return 0 if complete else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, ImportError) as error:
        print(f"Experiment stopped: {error}", file=sys.stderr)
        sys.exit(1)
