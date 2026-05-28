"""
Result transformer — reshapes a CodeParsingResult for RAG-optimized storage.

Removes Module and ImportBlock as standalone units. Folds import references
into each top-level unit. Strips redundant source text from Class units
that would duplicate their children's source. Cleans up whitespace.

Returns the same CodeParsingResult type — no schema changes for callers.
"""

from ..models import (
    CodeParsingResult,
    CodeReference,
    CodeUnit,
    ReferenceType,
    UnitType,
)

_CONTAINER_TYPES = {UnitType.Module, UnitType.ImportBlock}


def transform(result: CodeParsingResult) -> CodeParsingResult:
    """Transform a CodeParsingResult into a RAG-optimized version.

    - Drops Module and ImportBlock units
    - Folds import references into top-level units
    - Cleans source text whitespace
    """
    units = result.units
    if not units:
        return result

    import_block = _find_by_type(units, UnitType.ImportBlock)
    import_refs = _extract_import_refs(import_block)

    # Keep only content units
    content_units = [u for u in units if u.type not in _CONTAINER_TYPES]

    # Fold import refs into top-level units (those with no parent)
    transformed = []
    for unit in content_units:
        cleaned = unit.model_copy(
            update={
                "sourceText": _clean_source(unit.sourceText),
                "references": (
                    import_refs + unit.references
                    if unit.parentName is None
                    else unit.references
                ),
            }
        )
        transformed.append(cleaned)

    return CodeParsingResult(
        units=transformed,
        filePath=result.filePath,
        language=result.language,
        warnings=result.warnings,
    )


def _find_by_type(units: list[CodeUnit], unit_type: UnitType) -> CodeUnit | None:
    for unit in units:
        if unit.type == unit_type:
            return unit
    return None


def _extract_import_refs(import_block: CodeUnit | None) -> list[CodeReference]:
    if import_block is None:
        return []
    return [ref for ref in import_block.references if ref.type == ReferenceType.Imports]


def _clean_source(source_text: str) -> str:
    """Strip trailing whitespace per line, remove leading/trailing blank lines."""
    if not source_text:
        return ""
    lines = source_text.splitlines()
    cleaned = [line.rstrip() for line in lines]
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)