from .cobol_parser import CobolParser
from .cpp_parser import CppParser
from .typescript_parser import TypeScriptParser
from ..models import Language
from .base import BaseParser
from .dart_parser import DartParser
from .kotlin_parser import KotlinParser
from .python_parser import PythonParser

# Parsers are instantiated once and reused — tree-sitter parsers
# in particular benefit from not being recreated per request.
_parsers: dict[Language, BaseParser] = {
    Language.Python: PythonParser(),
    Language.Kotlin: KotlinParser(),
    Language.Dart: DartParser(),
    Language.C: CppParser(),
    Language.Cpp: CppParser(),
    Language.Cobol: CobolParser(),
    Language.TypeScript: TypeScriptParser(),
    Language.JavaScript: TypeScriptParser(),
}


def get_parser(language: Language) -> BaseParser:
    parser = _parsers.get(language)
    if parser is None:
        raise ValueError(f"No parser registered for language: {language}")
    return parser