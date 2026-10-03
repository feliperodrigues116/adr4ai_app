"""Load the canonical AI design patterns without altering their source content."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator


CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalogs" / "all-patterns.json"


class Pattern(BaseModel):
    """Original catalog fields; empty descriptions and list entries are valid."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    name: str
    aka: str
    motivation: str
    solution: str
    consequences: str
    examples: str
    related: list[str]
    categories: list[str]
    resources: list[str]

    @field_validator("id", "name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Pattern IDs and names must be non-empty")
        return value


def _read_records(text: str) -> list[object]:
    """Accept an array or the canonical file's concatenated JSON objects.

    Decode each object explicitly: do not repair malformed JSON, skip invalid
    records, or modify field values.
    """
    if text.lstrip().startswith("["):
        return json.loads(text)

    decoder = json.JSONDecoder()
    records = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        record, position = decoder.raw_decode(text, position)
        records.append(record)
    return records


def load_pattern_catalog(path: str | Path | None = None) -> list[Pattern]:
    """Validate a non-empty catalog with unique IDs and valid names.

    The default source is resolved from this module, independently of the
    working directory. An explicit path supports other copies and testing.
    Missing fields and incorrect types raise Pydantic validation errors;
    invalid JSON, counts, and duplicate IDs raise ValueError subclasses.
    """
    catalog_path = CATALOG_PATH if path is None else Path(path)
    records = _read_records(catalog_path.read_text(encoding="utf-8"))
    patterns = [Pattern.model_validate(record) for record in records]
    if not patterns:
        raise ValueError("Pattern catalog must not be empty")
    ids = [pattern.id for pattern in patterns]
    if len(set(ids)) != len(ids):
        raise ValueError("Pattern IDs must be unique")
    return patterns
