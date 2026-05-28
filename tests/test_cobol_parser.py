from app.parsers.cobol_parser import CobolParser


FILE_PATH = "src/cobol/CUSTMGMT.cob"


class TestCobolParser:
    def setup_method(self):
        self.parser = CobolParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.cob")
        return self.parser.parse(source, FILE_PATH)

    # ── Module ─────────────────────────────────────────────────────────

    def test_produces_valid_result(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.warnings == []
        assert result.language == "Cobol"
        assert result.filePath == FILE_PATH

    def test_module_is_first_unit(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.type == "Module"
        assert module.startLine == 1

    def test_module_name_from_path(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.name == "CUSTMGMT"

    def test_module_has_children(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert len(module.children) > 0

    def test_module_strips_various_extensions(self):
        for ext in (".cob", ".cbl", ".cpy", ".CBL", ".COB", ".CPY"):
            result = self.parser.parse("       IDENTIFICATION DIVISION.", f"TEST{ext}")
            module = result.units[0]
            assert module.name == "TEST"

    # ── Imports (COPY statements) ──────────────────────────────────────

    def test_copy_statements_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1
        assert all(r.type == "Imports" for r in import_blocks[0].references)

    def test_copy_targets_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        import_block = next(u for u in result.units if u.type == "ImportBlock")
        targets = [r.target for r in import_block.references]
        assert "ERRHANDL" in targets
        assert "RPTFMT" in targets

    def test_import_block_name(self, load_fixture):
        result = self._parse(load_fixture)
        import_block = next(u for u in result.units if u.type == "ImportBlock")
        assert import_block.name == "copies"

    # ── PERFORM references (calls) ─────────────────────────────────────

    def test_perform_references_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        all_calls = [r for u in result.units for r in u.references if r.type == "Calls"]
        assert len(all_calls) > 0

    def test_at_least_one_unit_has_perform_calls(self, load_fixture):
        result = self._parse(load_fixture)
        units_with_calls = [
            u for u in result.units
            if any(r.type == "Calls" for r in u.references)
        ]
        assert len(units_with_calls) > 0

    def test_perform_skips_keywords(self, load_fixture):
        result = self._parse(load_fixture)
        all_units = result.units
        all_calls = [r for u in all_units for r in u.references if r.type == "Calls"]
        call_targets = [r.target for r in all_calls]
        # PERFORM UNTIL should not create a call to "UNTIL"
        assert "UNTIL" not in call_targets

    # ── Source text and line numbers ───────────────────────────────────

    def test_all_units_have_source_text(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.sourceText is not None
            assert len(unit.sourceText) > 0

    def test_all_units_have_valid_line_numbers(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.startLine >= 1
            assert unit.endLine >= unit.startLine

    def test_chunks_do_not_overlap(self, load_fixture):
        result = self._parse(load_fixture)
        # Exclude the module (spans entire file) and import block
        chunks = [
            u for u in result.units
            if u.type not in ("Module", "ImportBlock")
        ]
        sorted_chunks = sorted(chunks, key=lambda u: u.startLine)
        for i in range(len(sorted_chunks) - 1):
            assert sorted_chunks[i].endLine <= sorted_chunks[i + 1].startLine, (
                f"Chunk '{sorted_chunks[i].name}' (ends {sorted_chunks[i].endLine}) "
                f"overlaps with '{sorted_chunks[i + 1].name}' (starts {sorted_chunks[i + 1].startLine})"
            )

    # ── Fixed-format detection ─────────────────────────────────────────

    def test_detects_fixed_format(self, load_fixture):
        fixed_source = (
            "000100 IDENTIFICATION DIVISION.\n"
            "000200 PROGRAM-ID. TEST.\n"
            "000300 PROCEDURE DIVISION.\n"
            "000400     DISPLAY 'HELLO'.\n"
            "000500     STOP RUN.\n"
        )
        result = self.parser.parse(fixed_source, "fixed.cob")
        # Should parse without errors — fixed format detected and stripped
        assert len(result.units) > 0
        assert result.units[0].type == "Module"

    def test_handles_free_format(self, load_fixture):
        free_source = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEST.\n"
            "PROCEDURE DIVISION.\n"
            "    DISPLAY 'HELLO'.\n"
            "    STOP RUN.\n"
        )
        result = self.parser.parse(free_source, "free.cob")
        assert len(result.units) > 0
        assert result.units[0].type == "Module"

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_handles_empty_file(self):
        result = self.parser.parse("", "empty.cob")
        assert len(result.units) == 1
        assert result.units[0].type == "Module"

    def test_handles_comments_only(self):
        source = (
            "      * This is a comment\n"
            "      * Another comment\n"
        )
        result = self.parser.parse(source, "comments.cob")
        assert result.units[0].type == "Module"

    def test_no_copy_means_no_import_block(self):
        source = (
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. SIMPLE.\n"
            "       PROCEDURE DIVISION.\n"
            "           DISPLAY 'HELLO'.\n"
            "           STOP RUN.\n"
        )
        result = self.parser.parse(source, "simple.cob")
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 0


class TestIndentChunkerIntegration:
    """Test the IndentChunker behavior through the COBOL parser."""

    def setup_method(self):
        self.parser = CobolParser()

    def test_force_splits_large_chunks(self):
        # Build a chunk larger than 333 lines
        lines = ["       PROCEDURE DIVISION."]
        for i in range(400):
            lines.append(f"           DISPLAY 'LINE {i}'.")
        source = "\n".join(lines)

        result = self.parser.parse(source, "big.cob")
        chunks = [u for u in result.units if u.type != "Module"]
        total_lines = sum(u.endLine - u.startLine + 1 for u in chunks)

        # Should have been split into multiple chunks
        assert len(chunks) > 1
        # Each chunk should be at or under the limit
        for chunk in chunks:
            chunk_size = chunk.endLine - chunk.startLine + 1
            assert chunk_size <= 363  # 333 + some tolerance for break-at-blank logic