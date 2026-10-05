"""Validate official assessments and export two UTF-8 CSV files."""

from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys


OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "outputs"
COLUMNS = ("system", "user_story_id", "pattern_id", "classification", "requirement_refs", "rationale")
CLASSIFICATIONS = ("applicable", "not_applicable", "insufficient_information")


def load_rows(path):
    """Validate all input records before creating either CSV."""
    rows = []
    pairs = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("expected a JSON object")
                story_id = record["user_story_id"]
                pattern_id = record["pattern_id"]
                classification = record["classification"]
                refs = record["requirement_refs"]
                rationale = record["rationale"]
                if not isinstance(story_id, str) or not re.fullmatch(r"SYS\d{2}-US\d{2}", story_id):
                    raise ValueError("invalid user_story_id")
                if not isinstance(pattern_id, str) or not re.fullmatch(r"\d{3}", pattern_id):
                    raise ValueError("pattern_id must be a three-digit string")
                if not 1 <= int(pattern_id) <= 70:
                    raise ValueError("pattern_id must be between 001 and 070")
                if classification not in CLASSIFICATIONS:
                    raise ValueError(f"invalid classification: {classification!r}")
                if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                    raise ValueError("requirement_refs must be an array of strings")
                if not isinstance(rationale, str):
                    raise ValueError("rationale must be a string")
                pair = (story_id, pattern_id)
                if pair in pairs:
                    raise ValueError(f"duplicate pair: {story_id} × {pattern_id}")
                pairs.add(pair)
                rows.append({
                    "system": story_id.split("-", 1)[0],
                    "user_story_id": story_id,
                    "pattern_id": pattern_id,
                    "classification": classification,
                    "requirement_refs": ";".join(refs),
                    "rationale": rationale,
                })
            except (ValueError, KeyError) as error:
                raise ValueError(f"{path}, line {line_number}: {error}") from error

    if len(pairs) != 840:
        raise ValueError(f"{path}: expected 840 unique assessment pairs, found {len(pairs)}")
    counts = Counter(row["classification"] for row in rows)
    if counts["applicable"] != 36:
        raise ValueError(f"{path}: expected 36 applicable assessments, found {counts['applicable']}")
    rows.sort(key=lambda row: (row["user_story_id"], row["pattern_id"]))
    return rows, counts


def write_csv(path, rows):
    """Create a CSV without overwriting an existing result file."""
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows, counts = load_rows(OUTPUT_DIRECTORY / "assessments.jsonl")
    all_path = OUTPUT_DIRECTORY / "pattern_assessments.csv"
    applicable_path = OUTPUT_DIRECTORY / "applicable_patterns.csv"
    for path in (all_path, applicable_path):
        if path.exists():
            raise ValueError(f"Output already exists; refusing to overwrite: {path}")
    write_csv(all_path, rows)
    write_csv(applicable_path, [row for row in rows if row["classification"] == "applicable"])
    print(f"Total rows: {len(rows)}")
    print(f"Unique pairs: {len(rows)}")
    print("Duplicate pairs: 0")
    for classification in CLASSIFICATIONS:
        print(f"{classification}: {counts[classification]}")
    print(f"All assessments: {all_path}")
    print(f"Applicable assessments: {applicable_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        sys.exit(1)
