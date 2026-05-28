from abc import ABC, abstractmethod

from ..models import CodeParsingResult


class BaseParser(ABC):
    """Interface for all language parsers.

    Each parser takes raw source text and a file path (for metadata),
    and returns a CodeParsingResult. No filesystem access occurs.
    """

    @abstractmethod
    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        """Parse source code and return structured CodeUnits.

        Args:
            source_text: Raw source code as a string.
            file_path: Original file path — used only for metadata
                       (filePath, qualifiedName, module derivation).
                       Nothing is read from disk.

        Returns:
            CodeParsingResult with extracted units and any warnings.
        """
        ...