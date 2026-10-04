"""Run one user story against all patterns, using separate resumable pilot outputs."""

import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import sys

from assess_pattern import MODEL, REASONING_EFFORT, assess_pattern, build_prompt
from prepare_data import REPOSITORY_ROOT, load_patterns, load_requirement_cases
from run_experiment import MAX_ATTEMPTS, load_assessments, load_failures, write_failures


def run_pilot(client, case, patterns, directory):
    """Skip valid results and retry unresolved patterns within the shared attempt limit."""
    assessments_path = directory / "assessments.jsonl"
    failures_path = directory / "failures.jsonl"
    summary_path = directory / "summary.json"
    story_id = case["user_story_id"]
    expected_pairs = {(story_id, pattern["id"]) for pattern in patterns}
    directory.mkdir(parents=True, exist_ok=True)
    with assessments_path.open("a", encoding="utf-8") as output:
        try:
            fcntl.flock(output.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another runner is already using this pilot directory") from error
        completed = load_assessments(assessments_path, [case], patterns)
        failures = load_failures(failures_path, expected_pairs, completed)
        for index, pattern in enumerate(patterns, start=1):
            if (story_id, pattern["id"]) in completed:
                print(f"[{index}/{len(patterns)}] {story_id} × {pattern['id']} -> SKIPPED (valid resumed assessment)", flush=True)
        write_failures(failures_path, failures)
        for pass_number in range(1, MAX_ATTEMPTS + 1):
            for index, pattern in enumerate(patterns, start=1):
                pair = (story_id, pattern["id"])
                attempts = failures.get(pair, {}).get("attempts", 0)
                if pair in completed or attempts >= MAX_ATTEMPTS:
                    continue
                # Persist the attempt before requesting so interruption cannot reset the limit.
                failures[pair] = {
                    "user_story_id": story_id, "pattern_id": pattern["id"],
                    "attempts": attempts + 1, "error_type": "InterruptedAttempt",
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
                    failures[pair].update(error_type=type(error).__name__, error_message=message[:300])
                    write_failures(failures_path, failures)
                    print(f"[{index}/{len(patterns)}] {story_id} × {pattern['id']} -> ERROR (pass {pass_number})", flush=True)
                    continue
                # Stop on storage errors rather than risk repeating a partially saved result.
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
                completed[pair] = record
                del failures[pair]
                write_failures(failures_path, failures)
                print(f"[{index}/{len(patterns)}] {story_id} × {pattern['id']} -> {record['classification']}", flush=True)
            if set(completed) == expected_pairs:
                break

        completed = load_assessments(assessments_path, [case], patterns)
        counts = Counter(record["classification"] for record in completed.values())
        summary = {
            "user_story_id": story_id,
            "expected_assessments": len(patterns), "valid_assessments": len(completed),
            "applicable": counts["applicable"], "not_applicable": counts["not_applicable"],
            "insufficient_information": counts["insufficient_information"],
            "failed": len(expected_pairs - set(completed)),
            "applicable_pattern_ids": [pattern["id"] for pattern in patterns
                if completed.get((story_id, pattern["id"]), {}).get("classification") == "applicable"],
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nExpected assessments: {summary['expected_assessments']}")
    print(f"Valid assessments: {summary['valid_assessments']}")
    print(f"Applicable: {summary['applicable']}")
    print(f"Not applicable: {summary['not_applicable']}")
    print(f"Insufficient information: {summary['insufficient_information']}")
    print(f"Failed: {summary['failed']}")
    print(f"Applicable pattern IDs: {json.dumps(summary['applicable_pattern_ids'])}")
    complete = set(completed) == expected_pairs
    print(f"Pilot status: {'COMPLETE' if complete else 'INCOMPLETE'}")
    print(f"Assessments: {assessments_path}")
    print(f"Summary: {summary_path}")
    return complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_story_id", help="Existing user story to assess against all 70 patterns")
    args = parser.parse_args()
    cases = load_requirement_cases(REPOSITORY_ROOT / "data/user_histories_orig.csv")
    patterns = load_patterns(REPOSITORY_ROOT / "catalogs/patterns")
    case = next((case for case in cases if case["user_story_id"] == args.user_story_id), None)
    if case is None:
        raise ValueError(f"Unknown user story: {args.user_story_id!r}")
    if sorted(pattern["id"] for pattern in patterns) != [f"{number:03d}" for number in range(1, 71)]:
        raise ValueError("Expected pattern IDs 001 through 070")
    patterns = sorted(patterns, key=lambda pattern: int(pattern["id"]))
    for pattern in patterns:
        build_prompt(case, pattern)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set; no API requests made")

    from openai import OpenAI

    print(f"Pilot User Story: {case['user_story_id']}")
    print(f"Patterns: {len(patterns)}")
    print(f"Expected assessments: {len(patterns)}")
    print(f"Model: {MODEL}")
    print(f"Reasoning effort: {REASONING_EFFORT}")
    print("Official experiment outputs: NOT USED", flush=True)
    directory = Path(__file__).resolve().parent / "outputs" / f"pilot_{case['user_story_id']}"
    with OpenAI(api_key=api_key, max_retries=0) as client:
        complete = run_pilot(client, case, patterns, directory)
    return 0 if complete else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, ImportError) as error:
        print(f"Pilot stopped: {error}", file=sys.stderr)
        sys.exit(1)
