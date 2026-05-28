from app.parsers.python_parser import PythonParser


FILE_PATH = "src/services/user_service.py"


class TestPythonParser:
    def setup_method(self):
        self.parser = PythonParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.py")
        return self.parser.parse(source, FILE_PATH)

    # ── Module ─────────────────────────────────────────────────────────

    def test_produces_valid_result(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.warnings == []
        assert result.language == "Python"
        assert result.filePath == FILE_PATH

    def test_module_is_first_unit(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.type == "Module"
        assert module.startLine == 1

    def test_module_qualified_name_from_path(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        # Dots replace slashes, extension stripped
        assert "/" not in module.qualifiedName
        assert module.qualifiedName.endswith(module.name)

    def test_module_has_children(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert len(module.children) > 0

    # ── Imports ────────────────────────────────────────────────────────

    def test_imports_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1
        assert len(import_blocks[0].references) > 0
        assert all(r.type == "Imports" for r in import_blocks[0].references)

    # ── Classes ────────────────────────────────────────────────────────

    def test_classes_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        assert len(classes) > 0

    def test_classes_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        for cls in classes:
            assert cls.signature is not None
            assert cls.signature.startswith("class ")

    def test_subclass_has_extends_reference(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        subclasses = [c for c in classes if any(r.type == "Extends" for r in c.references)]
        assert len(subclasses) > 0, "Expected at least one class with inheritance"

    def test_class_children_are_methods(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class" and len(u.children) > 0]
        assert len(classes) > 0
        for cls in classes:
            # Each child name should correspond to a Function unit
            functions = [u for u in result.units if u.type == "Function" and u.parentName == cls.name]
            assert len(functions) > 0

    # ── Functions ──────────────────────────────────────────────────────

    def test_functions_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        assert len(functions) > 0

    def test_methods_have_parent(self, load_fixture):
        result = self._parse(load_fixture)
        methods = [u for u in result.units if u.type == "Function" and u.parentName is not None]
        assert len(methods) > 0
        for method in methods:
            assert method.qualifiedName == f"{method.parentName}.{method.name}"

    def test_standalone_functions_have_no_parent(self, load_fixture):
        result = self._parse(load_fixture)
        standalone = [u for u in result.units if u.type == "Function" and u.parentName is None]
        assert len(standalone) > 0

    def test_functions_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        for func in functions:
            assert func.signature is not None
            assert "def " in func.signature

    def test_type_references_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        all_type_refs = [
            r for f in functions for r in f.references if r.type == "UsesTypes"
        ]
        assert len(all_type_refs) > 0

    def test_call_references_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        all_calls = [
            r for f in functions for r in f.references if r.type == "Calls"
        ]
        assert len(all_calls) > 0

    def test_decorator_references_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        all_annotations = [
            r for f in functions for r in f.references if r.type == "Annotations"
        ]
        assert len(all_annotations) > 0

    def test_override_detection(self, load_fixture):
        result = self._parse(load_fixture)
        overridden = [
            u for u in result.units
            if u.type == "Function"
            and any(r.type == "Overrides" for r in u.references)
        ]
        assert len(overridden) > 0, "Expected at least one overridden method"
        for unit in overridden:
            override_ref = next(r for r in unit.references if r.type == "Overrides")
            assert override_ref.qualifiedTarget == unit.parentName

    def test_async_functions_detected(self, load_fixture):
        result = self._parse(load_fixture)
        async_funcs = [
            u for u in result.units
            if u.type == "Function" and u.signature and u.signature.startswith("async def")
        ]
        assert len(async_funcs) > 0

    # ── Declarations ───────────────────────────────────────────────────

    def test_declarations_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        assert len(decls) > 0

    def test_typed_declarations_have_type_references(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        typed = [d for d in decls if any(r.type == "UsesTypes" for r in d.references)]
        assert len(typed) > 0, "Expected at least one typed declaration"

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

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_handles_syntax_error(self):
        result = self.parser.parse("def broken(:\n  pass", "bad.py")
        assert len(result.warnings) > 0
        assert result.units == []

    def test_handles_empty_file(self):
        result = self.parser.parse("", "empty.py")
        assert len(result.units) == 1
        assert result.units[0].type == "Module"