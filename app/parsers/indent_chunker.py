"""
Indent-based structural chunker.

Splits source text into logical components based on indentation levels.
Language-agnostic — can be used as a building block by any parser that
needs to chunk indented text files.
"""

from dataclasses import dataclass, field


@dataclass
class IndentChunk:
    """A structural chunk identified by indentation boundaries."""

    signature: str
    source_text: str
    indent_level: int
    start_line: int
    end_line: int
    children: list["IndentChunk"] = field(default_factory=list)


MAX_CHUNK_LINES = 333


class IndentChunker:
    """Splits source text into chunks based on indentation structure.

    A chunk starts at a line with indent level N and includes all subsequent
    lines that are deeper than N, until another line at level N or shallower
    is encountered.

    Chunks exceeding MAX_CHUNK_LINES are force-split into segments.
    """

    def __init__(self, max_chunk_lines: int = MAX_CHUNK_LINES):
        self._max_chunk_lines = max_chunk_lines

    def chunk(self, source_text: str) -> list[IndentChunk]:
        """Split source text into top-level indent-based chunks."""
        lines = source_text.splitlines()
        if not lines:
            return []

        # Find the base indent level (shallowest non-empty line)
        base_level = self._find_base_indent(lines)

        raw_chunks = self._split_at_level(lines, base_level, line_offset=0)

        # Force-split oversized chunks
        result: list[IndentChunk] = []
        for chunk in raw_chunks:
            if self._chunk_line_count(chunk) > self._max_chunk_lines:
                result.extend(self._force_split(chunk))
            else:
                result.append(chunk)

        return result

    def _find_base_indent(self, lines: list[str]) -> int:
        """Find the shallowest indent level across all non-empty lines."""
        min_indent = float("inf")
        for line in lines:
            if self._is_blank(line):
                continue
            level = self._indent_level(line)
            min_indent = min(min_indent, level)
        return int(min_indent) if min_indent != float("inf") else 0

    def _split_at_level(
        self,
        lines: list[str],
        target_level: int,
        line_offset: int,
    ) -> list[IndentChunk]:
        """Split lines into chunks where each chunk starts at target_level."""
        chunks: list[IndentChunk] = []
        current_start: int | None = None
        current_signature: str | None = None

        for i, line in enumerate(lines):
            if self._is_blank(line):
                continue

            level = self._indent_level(line)

            if level <= target_level:
                # Close the previous chunk if one is open
                if current_start is not None:
                    chunk = self._build_chunk(
                        lines, current_start, i, current_signature, target_level, line_offset
                    )
                    chunks.append(chunk)

                current_start = i
                current_signature = line.strip()

        # Close the last chunk
        if current_start is not None:
            chunk = self._build_chunk(
                lines, current_start, len(lines), current_signature, target_level, line_offset
            )
            chunks.append(chunk)

        return chunks

    def _build_chunk(
        self,
        lines: list[str],
        start: int,
        end: int,
        signature: str | None,
        indent_level: int,
        line_offset: int,
    ) -> IndentChunk:
        """Build a chunk from a line range, trimming trailing blank lines."""
        # Trim trailing blank lines
        actual_end = end
        while actual_end > start and self._is_blank(lines[actual_end - 1]):
            actual_end -= 1

        chunk_lines = lines[start:actual_end]
        source_text = "\n".join(chunk_lines)

        return IndentChunk(
            signature=signature or "",
            source_text=source_text,
            indent_level=indent_level,
            start_line=line_offset + start + 1,  # 1-indexed
            end_line=line_offset + actual_end,
        )

    def _force_split(self, chunk: IndentChunk) -> list[IndentChunk]:
        """Split an oversized chunk into segments of max_chunk_lines."""
        lines = chunk.source_text.splitlines()
        segments: list[IndentChunk] = []
        total = len(lines)

        i = 0
        part = 1
        while i < total:
            seg_end = min(i + self._max_chunk_lines, total)

            # Try to break at a blank line near the boundary for cleaner splits
            if seg_end < total:
                search_start = max(i + self._max_chunk_lines - 30, i)
                best_break = seg_end
                for j in range(seg_end, search_start, -1):
                    if j < total and self._is_blank(lines[j]):
                        best_break = j + 1
                        break
                seg_end = best_break

            seg_lines = lines[i:seg_end]
            first_non_blank = next(
                (l.strip() for l in seg_lines if not self._is_blank(l)), ""
            )

            sig = f"{chunk.signature} (part {part})" if part > 1 else chunk.signature

            segments.append(IndentChunk(
                signature=sig,
                source_text="\n".join(seg_lines),
                indent_level=chunk.indent_level,
                start_line=chunk.start_line + i,
                end_line=chunk.start_line + seg_end - 1,
            ))

            i = seg_end
            part += 1

        return segments

    @staticmethod
    def _chunk_line_count(chunk: IndentChunk) -> int:
        return chunk.end_line - chunk.start_line + 1

    @staticmethod
    def _indent_level(line: str) -> int:
        """Count leading whitespace as indent level.

        Tabs count as 4 spaces to normalize mixed indentation.
        """
        count = 0
        for char in line:
            if char == " ":
                count += 1
            elif char == "\t":
                count += 4
            else:
                break
        return count

    @staticmethod
    def _is_blank(line: str) -> bool:
        return line.strip() == ""