"""Load and validate the original inputs for the pattern selection experiment."""

import csv
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_COLUMNS = (
    "system",
    "system_purpose",
    "user_story_id",
    "user_story",
    "acceptance_criterion_id",
    "acceptance_criterion",
)


def load_requirement_cases(path):
    """Validate CSV rows and group stories without changing their text or order."""
    cases_by_id = {}
    criterion_ids = set()
    stories_by_system = {}

    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            if None in row or any(row[column] is None for column in REQUIRED_COLUMNS):
                raise ValueError(f"{path}: malformed CSV row {row_number}")
            story_id = row["user_story_id"]
            criterion_id = row["acceptance_criterion_id"]
            if not story_id.strip():
                raise ValueError(f"{path}: empty user_story_id at row {row_number}")
            if not criterion_id.strip():
                raise ValueError(f"{path}: empty acceptance_criterion_id at row {row_number}")
            if criterion_id in criterion_ids:
                raise ValueError(f"{path}: duplicate acceptance_criterion_id {criterion_id!r}")
            criterion_ids.add(criterion_id)

            if story_id not in cases_by_id:
                cases_by_id[story_id] = {
                    "system": row["system"],
                    "system_purpose": row["system_purpose"],
                    "user_story_id": story_id,
                    "user_story": row["user_story"],
                    "acceptance_criteria": [],
                }
            case = cases_by_id[story_id]
            for column in ("system", "system_purpose", "user_story"):
                if case[column] != row[column]:
                    raise ValueError(
                        f"{path}: inconsistent {column} for user_story_id "
                        f"{story_id!r} at row {row_number}"
                    )
            case["acceptance_criteria"].append({
                "acceptance_criterion_id": criterion_id,
                "acceptance_criterion": row["acceptance_criterion"],
            })
            stories_by_system.setdefault(row["system"], set()).add(story_id)

    for label, actual, expected in (
        ("systems", len(stories_by_system), 4),
        ("user stories", len(cases_by_id), 12),
        ("acceptance criteria", len(criterion_ids), 35),
    ):
        if actual != expected:
            raise ValueError(f"{path}: expected {expected} {label}, found {actual}")
    for system, story_ids in stories_by_system.items():
        if len(story_ids) != 3:
            raise ValueError(
                f"{path}: expected 3 user stories for {system!r}, found {len(story_ids)}"
            )

    cases = list(cases_by_id.values())
    for case in cases:
        criteria_text = "\n".join(
            f"[{criterion['acceptance_criterion_id']}] {criterion['acceptance_criterion']}"
            for criterion in case["acceptance_criteria"]
        )
        case["requirement_text"] = (
            f"System Purpose:\n{case['system_purpose']}\n\n"
            f"User Story:\n[{case['user_story_id']}] {case['user_story']}\n\n"
            f"Acceptance Criteria:\n{criteria_text}"
        )
    return cases


def load_patterns(directory):
    """Load individual JSON files in filename order, preserving their contents."""
    paths = sorted(path for path in directory.glob("P*.json") if path.is_file())
    if len(paths) != 70:
        raise ValueError(f"{directory}: expected 70 JSON files, found {len(paths)}")

    patterns = []
    id_files = {}
    for path in paths:
        try:
            with path.open(encoding="utf-8") as source:
                pattern = json.load(source)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"{path}: invalid JSON: {error}") from error
        if not isinstance(pattern, dict):
            raise ValueError(f"{path}: expected a pattern JSON object")
        pattern_id = pattern.get("id")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            raise ValueError(f"{path}: missing or invalid pattern ID")
        if pattern_id in id_files:
            raise ValueError(
                f"{path}: duplicate pattern ID {pattern_id!r}; "
                f"also present in {id_files[pattern_id]}"
            )
        id_files[pattern_id] = path
        patterns.append(pattern)
    return patterns


def main():
    cases = load_requirement_cases(REPOSITORY_ROOT / "data/user_histories_orig.csv")
    patterns = load_patterns(REPOSITORY_ROOT / "catalogs/patterns")

    print("Dataset validation\n------------------")
    print(f"Systems: {len({case['system'] for case in cases})}")
    print(f"User stories: {len(cases)}")
    print(f"Acceptance criteria: {sum(len(case['acceptance_criteria']) for case in cases)}")
    print("\nPattern catalog validation\n--------------------------")
    print(f"Patterns: {len(patterns)}")
    print("\nFirst requirement case\n----------------------")
    print(cases[0]["requirement_text"])
    print("\nFirst pattern\n-------------")
    print(f"ID: {patterns[0]['id']}")
    print(f"Name: {patterns[0].get('name', '')}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        sys.exit(1)
