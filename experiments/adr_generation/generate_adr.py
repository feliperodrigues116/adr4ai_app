"""Generate exactly one controlled ADR pilot; never retry an API request."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import string
import sys


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'research_results/pattern_selection_results.csv'
OUTPUT = Path(__file__).resolve().parent / 'outputs/pilot_SYS01-US01_P001.json'
MODEL = 'gpt-6-sol'
REASONING_EFFORT = 'high'
USER_STORY_ID = 'SYS01-US01'
PATTERN_ID = '001'
FIELDS = ('title', 'context', 'decision', 'consequences')
INPUT_FIELDS = (
    'system_purpose', 'user_story_id', 'user_story', 'acceptance_criteria',
    'pattern_id', 'pattern_name', 'pattern_motivation', 'pattern_solution',
    'pattern_consequences', 'evidence_refs', 'evidence_text', 'rationale',
)
SCHEMA = {
    'type': 'object',
    'properties': {field: {'type': 'string'} for field in FIELDS},
    'required': list(FIELDS),
    'additionalProperties': False,
}
PROMPT_TEMPLATE = """You are generating one Architecture Decision Record (ADR) for an AI-based software system.

The ADR must follow the structure and writing principles proposed by Michael Nygard:

- Title: a short noun phrase describing the architectural decision.
- Context: describe the forces at play and the architectural problem that motivates the decision. Present the context neutrally.
- Decision: describe the architectural response to those forces using complete sentences and active voice. State the decision as "We will ...".
- Consequences: describe the resulting context after applying the decision, including relevant positive, negative, and neutral consequences.

The ADR status is fixed by the experimental protocol as "Proposed" and is not part of your output.

You are given:

1. A REQUIREMENT CASE containing:
   - System Purpose
   - User Story
   - Acceptance Criteria

2. ONE SELECTED ARCHITECTURAL PATTERN containing:
   - Pattern ID
   - Name
   - Motivation
   - Solution
   - Consequences

3. APPLICABILITY EVIDENCE from a previous assessment containing:
   - Evidence References
   - Evidence Text
   - Applicability Rationale

Your task is to generate ONE architectural decision grounded in the selected pattern and contextualized to the requirement case.

GROUNDING RULES

- Base the ADR only on the information provided in the Requirement Case, Selected Architectural Pattern, and Applicability Evidence.
- Use the System Purpose only as contextual information.
- Treat the User Story and Acceptance Criteria as the source of requirement information.
- Use the Applicability Evidence to understand why the selected pattern is relevant to this requirement case.
- Do not introduce requirements, constraints, technologies, components, protocols, products, platforms, or system characteristics that are not supported by the provided information.
- Do not invent implementation details merely to make the ADR more specific.
- Do not propose additional architectural decisions beyond the decision grounded in the selected pattern.
- Generate exactly one architectural decision.
- The decision must instantiate the architectural intent of the selected pattern in the specific requirement context.
- Do not merely state that the system will "use", "adopt", or "implement" the named pattern.
- The Decision must explain what architectural structure or behavior will be established as a consequence of applying the pattern.
- Do not mention the applicability assessment process, the language model, the experiment, the prompt, or the evidence identifiers in the ADR.
- Do not include the Pattern ID or pattern name merely as justification for the decision.
- Do not copy the generic pattern description as the architectural decision. Contextualize it to the requirement case.
- Consequences must follow from the proposed decision and the provided information. Include relevant benefits and trade-offs when supported by the input, rather than presenting the decision as universally beneficial.
- If the provided information does not support a specific implementation detail, keep the decision at the appropriate architectural level instead of inventing that detail.

ONE-SHOT EXAMPLE

The following synthetic example demonstrates the expected transformation from requirements and an architectural pattern into a contextualized ADR.

The requirement case is synthetic and is not part of the experimental dataset.
The architectural pattern is an actual pattern from the architectural pattern catalog, but it is not among the patterns evaluated in the ADR generation cases.

REQUIREMENT CASE

System Purpose:
An AI-based recruitment platform supports organizations in screening job applications and providing candidate recommendations.

User Story:
[EX-US01] As a compliance officer, I want users to be able to verify that the AI-based candidate screening service satisfies the organization's responsible AI requirements so that its compliance claims can be independently checked.

Acceptance Criteria:
[EX-US01-AC01] The system must provide verifiable evidence of compliance with the defined responsible AI requirements.
[EX-US01-AC02] Authorized users must be able to verify the validity of the compliance evidence.
[EX-US01-AC03] The compliance evidence must remain maintainable when its validity or underlying requirements change.

SELECTED ARCHITECTURAL PATTERN

Pattern ID:
007

Name:
Ethics credentials

Motivation:
Responsible AI requirements are either omitted or mostly stated as high-level objectives, and not specified explicitly in a verifiable way as expected system outputs. Because of this, users may trust an AI system less, or even refrain from using it.

Solution:
Provide verifiable ethics credentials for your AI system or component. Using publicly accessible and trusted data infrastructure, the credentials can be verified as proof of ethical compliance. Additionally, users may also have to verify their credentials before getting access to the AI system.

Consequences:
Trust and system acceptance increases, and awareness of ethical issues is raised. However, a trusted public data infrastructure is needed, and credentials need to be maintained and potentially refreshed from time to time.

APPLICABILITY EVIDENCE

Evidence References:
EX-US01-AC01;EX-US01-AC02;EX-US01-AC03

Evidence Text:
[EX-US01-AC01] The system must provide verifiable evidence of compliance with the defined responsible AI requirements. | [EX-US01-AC02] Authorized users must be able to verify the validity of the compliance evidence. | [EX-US01-AC03] The compliance evidence must remain maintainable when its validity or underlying requirements change.

Applicability Rationale:
The acceptance criteria explicitly require responsible AI compliance claims to be represented through verifiable evidence, allow their validity to be checked, and require that this evidence can be maintained as its validity or underlying requirements change. These needs correspond to the pattern's intent of representing ethical compliance through verifiable and maintainable credentials.

EXPECTED ADR

Title:
Provide Verifiable Responsible AI Credentials

Context:
The candidate screening service is required to provide evidence that its responsible AI requirements are satisfied rather than relying only on compliance claims. Authorized users need to be able to verify this evidence, and the evidence must remain maintainable when its validity or the underlying requirements change. The architecture therefore needs a mechanism through which responsible AI compliance can be represented and independently verified.

Decision:
We will represent evidence of responsible AI compliance as verifiable credentials associated with the AI-based screening service. These credentials will provide the evidence required for authorized users to verify compliance claims and will be maintained when their validity or the underlying responsible AI requirements change.

Consequences:
Responsible AI compliance claims will become explicitly verifiable, supporting transparency and increasing confidence in the screening service. The architecture will also introduce responsibility for maintaining the credentials and keeping them aligned with changes to their validity and the underlying requirements. Verification will additionally depend on the availability of a trusted mechanism through which the credentials can be validated.

END OF EXAMPLE

Now generate the ADR for the following experimental case.

REQUIREMENT CASE

System Purpose:
{system_purpose}

User Story:
[{user_story_id}] {user_story}

Acceptance Criteria:
{acceptance_criteria}

SELECTED ARCHITECTURAL PATTERN

Pattern ID:
{pattern_id}

Name:
{pattern_name}

Motivation:
{pattern_motivation}

Solution:
{pattern_solution}

Consequences:
{pattern_consequences}

APPLICABILITY EVIDENCE

Evidence References:
{evidence_refs}

Evidence Text:
{evidence_text}

Applicability Rationale:
{rationale}

Generate exactly one ADR."""


def validate_input(row):
    """Preserve catalog descriptions verbatim, including legitimate empty strings."""
    optional_descriptions = {'pattern_motivation', 'pattern_solution', 'pattern_consequences'}
    for field in (*INPUT_FIELDS, 'classification'):
        if field not in row or not isinstance(row[field], str):
            raise ValueError(f'Missing or non-string input field: {field}')
        if field not in optional_descriptions and not row[field].strip():
            raise ValueError(f'Missing or empty input field: {field}')
    if row['classification'] != 'applicable':
        raise ValueError('The selected row must be classified as applicable')


def build_prompt():
    """Load the unique pilot row and substitute only the specified placeholders."""
    with SOURCE.open(encoding='utf-8', newline='') as source:
        matches = [row for row in csv.DictReader(source)
                   if row.get('user_story_id') == USER_STORY_ID
                   and row.get('pattern_id') == PATTERN_ID]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one pilot row; found {len(matches)}')
    row = matches[0]
    if row.get('classification') != 'applicable':
        raise ValueError('The selected pilot row must be classified as applicable')
    validate_input(row)
    placeholders = {name for _, name, _, _ in
                    string.Formatter().parse(PROMPT_TEMPLATE) if name is not None}
    if placeholders != set(INPUT_FIELDS):
        raise ValueError('Prompt placeholders do not match the allowed input fields')
    return PROMPT_TEMPLATE.format(**{field: row[field] for field in INPUT_FIELDS})


def validate_adr(adr):
    """Validate exact semantic fields without modifying generated text."""
    if not isinstance(adr, dict) or set(adr) != set(FIELDS):
        raise ValueError('Generated ADR must contain exactly the four semantic fields')
    for field in FIELDS:
        if not isinstance(adr[field], str) or not adr[field].strip():
            raise ValueError(f'Generated ADR field must be a non-empty string: {field}')


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate generated JSON field: {key}')
        result[key] = value
    return result


def generate(prompt):
    """Make one Responses API request with SDK retries explicitly disabled."""
    from openai import OpenAI

    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise ValueError('OPENAI_API_KEY is not available in the environment; no API call was made')
    with OpenAI(api_key=key, base_url='https://api.openai.com/v1',
                max_retries=0, timeout=600.0) as client:
        print('Making exactly one Responses API request; automatic retries disabled.', flush=True)
        response = client.responses.create(
            model=MODEL,
            reasoning={'effort': REASONING_EFFORT},
            input=prompt,
            text={'format': {
                'type': 'json_schema', 'name': 'adr_pilot',
                'strict': True, 'schema': SCHEMA,
            }},
        )
    if response.status != 'completed':
        raise ValueError(f'Response did not complete: {response.status}; no retry will be made')
    for item in response.output:
        if item.type == 'message':
            for content in item.content:
                if content.type == 'refusal':
                    raise ValueError('The model refused the pilot request; no retry will be made')
    adr = json.loads(response.output_text, object_pairs_hook=reject_duplicate_keys)
    validate_adr(adr)
    return adr, response.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Validate the pilot input and schema locally without API calls')
    args = parser.parse_args()
    try:
        prompt = build_prompt()
        if args.check:
            print('Pilot input and prompt validated: SYS01-US01 x 001.')
            print('Strict schema: exactly title, context, decision, consequences.')
            print('RAG information excluded. API calls made: 0.')
            return 0
        if OUTPUT.exists():
            raise ValueError('Pilot output already exists; refusing another API call or overwrite')
        adr, response_id = generate(prompt)
        adr = {
            'title': adr['title'], 'context': adr['context'],
            'decision': adr['decision'], 'status': 'Proposed',
            'consequences': adr['consequences'],
        }
        artifact = {
            'user_story_id': USER_STORY_ID, 'pattern_id': PATTERN_ID,
            'model': MODEL, 'reasoning_effort': REASONING_EFFORT,
            'response_id': response_id, 'api_calls': 1,
            'source_file': str(SOURCE.relative_to(ROOT)),
            'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
            'structured_outputs': {'strict': True, 'validation_succeeded': True},
            'adr': adr,
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open('x', encoding='utf-8', newline='') as output:
            json.dump(artifact, output, ensure_ascii=False, indent=2)
            output.write('\n')
        print(f'Saved: {OUTPUT}')
        print('Structured Outputs validation succeeded. API calls made: 1.')
        for field in ('title', 'context', 'decision', 'status', 'consequences'):
            print(f'\n{field.title()}:\n{adr[field]}')
        return 0
    except Exception as error:
        # Report errors without credentials and never retry the request.
        message = str(error)
        key = os.environ.get('OPENAI_API_KEY')
        if key:
            message = message.replace(key, '[REDACTED]')
        print(f'Pilot failed: {message}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
