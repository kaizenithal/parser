"""
COBOL parser using keyword-aware structural splitting.

Splits COBOL source files into logical components by recognizing
COBOL structural markers (divisions, sections, paragraphs), with
COBOL-specific extraction for COPY statements (imports) and
fixed-format column handling. Falls back to indent-based chunking
for oversized sections.

All filesystem access removed — operates entirely on in-memory source text.
"""

import re

from ..models import (
    CodeParsingResult,
    CodeReference,
    CodeUnit,
    Language as CodeLanguage,
    ReferenceType,
    UnitType,
)
from .base import BaseParser
from .indent_chunker import IndentChunker


# Fixed-format COBOL: columns 1-6 sequence, 7 indicator, 8-72 code, 73-80 ident
_FIXED_FORMAT_LINE_RE = re.compile(r"^.{6}[ \-\*dD/]")
_COPY_RE = re.compile(r"\bCOPY\s+([\w\-]+)", re.IGNORECASE)
_SEQUENCE_COLS = 6
_CODE_END_COL = 72

class CobolParser(BaseParser):
    def __init__(self):
        self._chunker = IndentChunker()

    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        source_lines = source_text.splitlines()

        is_fixed = self._detect_fixed_format(source_lines)
        clean_lines = self._strip_fixed_format_lines(source_lines) if is_fixed else source_lines

        # Strip comment lines
        stripped_lines = self._strip_comments(clean_lines)
        clean_text = "\n".join(stripped_lines)

        units: list[CodeUnit] = []
        top_level_children: list[str] = []

        # Extract COPY references from the full source
        import_unit, import_references = self._extract_copies(
            source_text, source_lines, file_path
        )
        if import_unit:
            units.append(import_unit)

        # Chunk by indentation
        chunks = self._chunker.chunk(clean_text)

        for chunk in chunks:
            unit = CodeUnit(
                type=UnitType.Declaration,
                name=chunk.signature.strip().rstrip("."),
                qualifiedName=chunk.signature.strip().rstrip("."),
                language=CodeLanguage.Cobol,
                sourceText=chunk.source_text,
                signature=chunk.signature.strip(),
                references=self._extract_perform_references(chunk.source_text),
                filePath=file_path,
                startLine=chunk.start_line,
                endLine=chunk.end_line,
            )
            units.append(unit)
            top_level_children.append(unit.name)

        # Module unit
        module_name = file_path.rsplit("/", 1)[-1]
        for ext in (".cob", ".cbl", ".cpy", ".CBL", ".COB", ".CPY"):
            module_name = module_name.removesuffix(ext)

        units.insert(0, CodeUnit(
            type=UnitType.Module,
            name=module_name,
            qualifiedName=module_name,
            language=CodeLanguage.Cobol,
            sourceText=source_text,
            references=import_references,
            filePath=file_path,
            startLine=1,
            endLine=len(source_lines),
            children=top_level_children,
        ))

        return CodeParsingResult(
            units=units,
            filePath=file_path,
            language=CodeLanguage.Cobol,
        )

    def _strip_comments(self, lines: list[str]) -> list[str]:
        """Replace comment lines with empty lines to preserve line numbering."""
        result = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("*") or stripped.startswith("/"):
                result.append("")
            else:
                result.append(line)
        return result

    # ── Fixed-format handling ──────────────────────────────────────────

    def _detect_fixed_format(self, lines: list[str]) -> bool:
        """Heuristic: if a majority of non-empty lines look fixed-format, treat as fixed."""
        if not lines:
            return False

        fixed_count = 0
        total = 0
        for line in lines[:100]:
            if not line.strip():
                continue
            total += 1
            if len(line) >= 7 and _FIXED_FORMAT_LINE_RE.match(line):
                fixed_count += 1

        return total > 0 and (fixed_count / total) > 0.5

    def _strip_fixed_format_lines(self, lines: list[str]) -> list[str]:
        """Strip sequence numbers (cols 1-6) and identification (cols 73-80).

        Preserves the indicator column (7) as part of the content so that
        comment lines (* in col 7) remain visible.
        """
        cleaned: list[str] = []
        for line in lines:
            if len(line) <= _SEQUENCE_COLS:
                cleaned.append("")
                continue
            code_portion = (
                line[_SEQUENCE_COLS:_CODE_END_COL]
                if len(line) > _CODE_END_COL
                else line[_SEQUENCE_COLS:]
            )
            cleaned.append(code_portion.rstrip())
        return cleaned

    # ── COPY extraction ────────────────────────────────────────────────

    def _extract_copies(
        self,
        source_text: str,
        source_lines: list[str],
        file_path: str,
    ) -> tuple[CodeUnit | None, list[CodeReference]]:
        """Extract COPY statements as import references."""
        references: list[CodeReference] = []
        copy_lines: list[int] = []

        for i, line in enumerate(source_lines):
            matches = _COPY_RE.findall(line)
            for match in matches:
                copybook_name = match.strip().rstrip(".")
                references.append(CodeReference(
                    type=ReferenceType.Imports,
                    target=copybook_name,
                ))
                copy_lines.append(i)

        if not references:
            return None, []

        copy_text = "\n".join(source_lines[i] for i in copy_lines)

        import_unit = CodeUnit(
            type=UnitType.ImportBlock,
            name="copies",
            language=CodeLanguage.Cobol,
            sourceText=copy_text,
            references=references,
            filePath=file_path,
            startLine=copy_lines[0] + 1,
            endLine=copy_lines[-1] + 1,
        )

        return import_unit, references

    # ── PERFORM extraction ─────────────────────────────────────────────

    def _extract_perform_references(self, source_text: str) -> list[CodeReference]:
        """Extract PERFORM targets as call references."""
        references: list[CodeReference] = []
        seen: set[str] = set()

        for match in re.finditer(r"\bPERFORM\s+([\w\-]+)", source_text, re.IGNORECASE):
            target = match.group(1).strip()
            if target.upper() in ("UNTIL", "VARYING", "WITH", "TEST", "TIMES"):
                continue
            if target not in seen:
                seen.add(target)
                references.append(CodeReference(
                    type=ReferenceType.Calls,
                    target=target,
                ))

        return references