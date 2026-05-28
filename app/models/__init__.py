from enum import StrEnum

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class UnitType(StrEnum):
    Module = "Module"
    Class = "Class"
    Function = "Function"
    ImportBlock = "ImportBlock"
    Declaration = "Declaration"


class ReferenceType(StrEnum):
    Imports = "Imports"
    Extends = "Extends"
    Implements = "Implements"
    Calls = "Calls"
    References = "References"
    Annotations = "Annotations"
    Overrides = "Overrides"
    UsesTypes = "UsesTypes"


class Language(StrEnum):
    Python = "Python"
    Kotlin = "Kotlin"
    Dart = "Dart"
    JavaScript = "JavaScript"
    TypeScript = "TypeScript"
    Cobol = "Cobol"
    C ="C"
    Cpp = "Cpp"


# ── Core models ────────────────────────────────────────────────────────────────


class CodeReference(BaseModel):
    type: ReferenceType
    target: str
    qualifiedTarget: str | None = None


class CodeUnit(BaseModel):
    type: UnitType
    name: str
    language: Language
    sourceText: str
    filePath: str
    startLine: int
    endLine: int
    qualifiedName: str | None = None
    signature: str | None = None
    references: list[CodeReference] = Field(default_factory=list)
    parentName: str | None = None
    children: list[str] = Field(default_factory=list)


class CodeParsingResult(BaseModel):
    units: list[CodeUnit]
    filePath: str
    language: Language
    warnings: list[str] = Field(default_factory=list)


# ── Request/Response ───────────────────────────────────────────────────────────


class ParseRequest(BaseModel):
    source_text: str = Field(description="Raw source code to parse")
    file_path: str = Field(description="Original file path — used for metadata only, not file access")
    language: Language