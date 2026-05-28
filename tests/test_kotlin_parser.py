from app.parsers.kotlin_parser import KotlinParser


FILE_PATH = "src/main/kotlin/com/example/service/UserService.kt"


class TestKotlinParser:
    def setup_method(self):
        self.parser = KotlinParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.kt")
        return self.parser.parse(source, FILE_PATH)

    # ── Module ─────────────────────────────────────────────────────────

    def test_produces_valid_result(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.language == "Kotlin"
        assert result.filePath == FILE_PATH

    def test_module_is_first_unit(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.type == "Module"
        assert module.startLine == 1

    def test_module_has_children(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert len(module.children) > 0

    def test_module_qualified_name_includes_package(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        # If the file has a package declaration, qualified name should reflect it
        if "." in module.qualifiedName:
            assert module.qualifiedName.endswith(module.name)

    # ── Imports ────────────────────────────────────────────────────────

    def test_imports_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1
        assert len(import_blocks[0].references) > 0

    def test_imports_have_qualified_targets(self, load_fixture):
        result = self._parse(load_fixture)
        import_block = next(u for u in result.units if u.type == "ImportBlock")
        for ref in import_block.references:
            assert ref.type == "Imports"
            assert ref.target is not None
            assert ref.qualifiedTarget is not None
            assert "." in ref.qualifiedTarget

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

    def test_class_inheritance_detected(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        subclasses = [c for c in classes if any(r.type == "Extends" for r in c.references)]
        assert len(subclasses) > 0, "Expected at least one class with inheritance"

    def test_class_children_are_functions(self, load_fixture):
        result = self._parse(load_fixture)
        classes_with_children = [
            u for u in result.units if u.type == "Class" and len(u.children) > 0
        ]
        assert len(classes_with_children) > 0
        for cls in classes_with_children:
            child_units = [
                u for u in result.units
                if u.parentName == cls.qualifiedName or u.parentName == cls.name
            ]
            assert len(child_units) > 0

    def test_class_annotations_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        all_annotations = [
            r for c in classes for r in c.references if r.type == "Annotations"
        ]
        assert len(all_annotations) > 0, "Expected at least one annotated class"

    # ── Companion / nested objects ─────────────────────────────────────

    def test_companion_or_nested_object_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        nested = [
            u for u in result.units
            if u.type == "Class" and u.parentName is not None
        ]
        assert len(nested) > 0, "Expected at least one nested class or companion object"

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

    def test_functions_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        for func in functions:
            assert func.signature is not None
            assert "fun " in func.signature

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

    def test_suspend_function_detected(self, load_fixture):
        result = self._parse(load_fixture)
        suspend_funcs = [
            u for u in result.units
            if u.type == "Function" and u.signature and "suspend" in u.signature
        ]
        assert len(suspend_funcs) > 0, "Expected at least one suspend function"

    # ── Properties / Declarations ──────────────────────────────────────

    def test_declarations_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        assert len(decls) > 0

    def test_declarations_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        for decl in decls:
            assert decl.signature is not None
            assert len(decl.signature) > 0

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

    def test_handles_empty_file(self):
        result = self.parser.parse("", "empty.kt")
        assert len(result.units) == 1
        assert result.units[0].type == "Module"