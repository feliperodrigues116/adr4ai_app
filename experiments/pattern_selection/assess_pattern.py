"""Assess one requirement case and pattern, with a separate single-test entry point."""

import json
import os
from pathlib import Path
import sys

from prepare_data import REPOSITORY_ROOT, load_patterns, load_requirement_cases


MODEL = "gpt-6-sol"
REASONING_EFFORT = "high"
USER_STORY_ID = "SYS01-US01"
PATTERN_ID = "001"
OUTPUT_PATH = Path(__file__).resolve().parent / "outputs/test_assessment_v2.json"
CLASSIFICATIONS = ("applicable", "not_applicable", "insufficient_information")

INSTRUCTIONS = """You are assessing whether one architectural pattern is applicable to one software requirement case.

A REQUIREMENT CASE consists of:

- System Purpose: contextual information about the system.
- User Story: the stakeholder need being analyzed.
- Acceptance Criteria: conditions that specify or constrain the expected behavior of the User Story.

Determine the applicability of the ARCHITECTURAL PATTERN based only on the provided requirement case.

Evidence for applicability must come from the User Story and/or its Acceptance Criteria. The System Purpose may be used as contextual information, but it is not sufficient by itself to establish applicability.

Do not assume requirements, technologies, constraints, or system characteristics that are not supported by the provided information.

Classify the pattern using exactly one of the following:

- applicable:
  The User Story and/or Acceptance Criteria provide positive evidence of a need, problem, constraint, or quality concern addressed by the pattern.

- not_applicable:
  The User Story and/or Acceptance Criteria provide evidence that the pattern does not fit the stated need, problem, constraint, or context.

- insufficient_information:
  There is not enough evidence in the User Story and Acceptance Criteria to establish either applicability or non-applicability.

Absence of contradictory evidence is not evidence of applicability. A pattern must not be classified as applicable merely because it could be useful.

Applicability requires evidence that the requirement case exhibits the need, problem, constraint, or quality concern addressed by the pattern. Evidence that the pattern could be used to implement, test, improve, or support the requirement is not sufficient by itself.

Assess the pattern based on its underlying architectural intent, not on literal terminology. The pattern may apply in different technological contexts when the same architectural problem or need is present.

For an applicable classification, identify at least one supporting User Story or Acceptance Criterion identifier.

The rationale must briefly explain the relationship between the cited evidence and the pattern. Do not propose an architecture, implementation, technology, or new requirement."""

ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": list(CLASSIFICATIONS)},
        "requirement_refs": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["classification", "requirement_refs", "rationale"],
    "additionalProperties": False,
}


def build_prompt(case, pattern):
    """Include the requirement text and only the five permitted pattern fields."""
    for field in ("id", "name", "motivation", "solution", "consequences"):
        if field not in pattern or not isinstance(pattern[field], str):
            raise ValueError(f"Pattern {pattern.get('id')}: missing or invalid field {field!r}")
    return (
        f"REQUIREMENT CASE\n\n{case['requirement_text']}\n\n"
        f"ARCHITECTURAL PATTERN\n\n"
        f"Pattern ID:\n{pattern['id']}\n\n"
        f"Name:\n{pattern['name']}\n\n"
        f"Motivation:\n{pattern['motivation']}\n\n"
        f"Solution:\n{pattern['solution']}\n\n"
        f"Consequences:\n{pattern['consequences']}"
    )


def validate_assessment(assessment, case):
    """Reject invalid model output without inferring or repairing any values."""
    expected_fields = {"classification", "requirement_refs", "rationale"}
    if not isinstance(assessment, dict) or set(assessment) != expected_fields:
        raise ValueError("Assessment must contain exactly classification, requirement_refs, and rationale")
    if assessment["classification"] not in CLASSIFICATIONS:
        raise ValueError("Assessment contains an invalid classification")
    refs = assessment["requirement_refs"]
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("Assessment requirement_refs must be an array of strings")
    valid_refs = {case["user_story_id"]}
    valid_refs.update(
        criterion["acceptance_criterion_id"] for criterion in case["acceptance_criteria"]
    )
    for ref in refs:
        if ref not in valid_refs:
            raise ValueError(f"Assessment cites an unknown requirement identifier: {ref!r}")
    if assessment["classification"] == "applicable" and not refs:
        raise ValueError("An applicable assessment must cite at least one valid requirement identifier")
    if not isinstance(assessment["rationale"], str):
        raise ValueError("Assessment rationale must be a string")


def assess_pattern(client, case, pattern):
    """Make one strict Structured Output request and validate the returned assessment."""
    prompt = build_prompt(case, pattern)
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": REASONING_EFFORT},
        instructions=INSTRUCTIONS,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "pattern_assessment",
                "strict": True,
                "schema": ASSESSMENT_SCHEMA,
            }
        },
    )

    if response.status != "completed":
        raise ValueError(f"API response did not complete: {response.status}")
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "refusal":
                    raise ValueError(f"Model refused the assessment: {content.refusal}")
    if not response.output_text:
        raise ValueError("API response did not contain a structured assessment")
    # Decode output constrained by the strict API schema, then check local references.
    assessment = json.loads(response.output_text)
    validate_assessment(assessment, case)
    return {
        "user_story_id": case["user_story_id"],
        "pattern_id": pattern["id"],
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        **assessment,
    }


def main():
    cases = load_requirement_cases(REPOSITORY_ROOT / "data/user_histories_orig.csv")
    patterns = load_patterns(REPOSITORY_ROOT / "catalogs/patterns")
    case = next((case for case in cases if case["user_story_id"] == USER_STORY_ID), None)
    pattern = next((pattern for pattern in patterns if pattern["id"] == PATTERN_ID), None)
    if case is None or pattern is None:
        raise ValueError(f"Required test inputs not found: {USER_STORY_ID} × {PATTERN_ID}")
    build_prompt(case, pattern)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set; no API request was made")

    from openai import OpenAI

    print(f"user_story_id: {USER_STORY_ID}")
    print(f"pattern_id: {PATTERN_ID}")
    print(f"model: {MODEL}")
    print(f"reasoning_effort: {REASONING_EFFORT}", flush=True)

    # Disable SDK retries; retry policy belongs to the experiment runner.
    with OpenAI(api_key=api_key, max_retries=0) as client:
        result = assess_pattern(client, case, pattern)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"classification: {result['classification']}")
    print(f"requirement_refs: {json.dumps(result['requirement_refs'], ensure_ascii=False)}")
    print(f"rationale: {result['rationale']}")
    print(f"output file: {OUTPUT_PATH.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ImportError) as error:
        print(f"Assessment failed: {error}", file=sys.stderr)
        sys.exit(1)
