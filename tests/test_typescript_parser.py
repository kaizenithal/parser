from app.parsers.typescript_parser import TypeScriptParser


TS_FILE_PATH = "src/services/user.service.ts"
JS_FILE_PATH = "src/services/user.service.js"


class TestTypeScriptParser:
    """Tests for TypeScript parsing behavior. No fixture-specific names or counts."""

    def setup_method(self):
        self.parser = TypeScriptParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.ts")
        return self.parser.parse(source, TS_FILE_PATH)

    # ── Module invariants ──────────────────────────────────────────────

    def test_produces_valid_result(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.warnings == []
        assert result.language == "TypeScript"
        assert result.filePath == TS_FILE_PATH

    def test_module_is_first_unit(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.type == "Module"
        assert module.startLine == 1

    def test_module_name_derived_from_path(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.name is not None
        assert len(module.name) > 0
        assert "/" not in module.name

    def test_module_has_children(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert len(module.children) > 0

    def test_module_children_exist_as_units(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        unit_names = {u.name for u in result.units}
        for child in module.children:
            assert child in unit_names, f"Module child '{child}' has no corresponding unit"

    # ── Imports ────────────────────────────────────────────────────────

    def test_imports_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1

    def test_import_references_are_imports(self, load_fixture):
        result = self._parse(load_fixture)
        import_block = next(u for u in result.units if u.type == "ImportBlock")
        assert len(import_block.references) > 0
        assert all(r.type == "Imports" for r in import_block.references)

    def test_import_references_have_qualified_targets(self, load_fixture):
        result = self._parse(load_fixture)
        import_block = next(u for u in result.units if u.type == "ImportBlock")
        for ref in import_block.references:
            assert ref.qualifiedTarget is not None
            assert len(ref.qualifiedTarget) > 0

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
            assert len(cls.signature) > 0

    def test_at_least_one_class_has_extends(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        has_extends = any(
            any(r.type == "Extends" for r in c.references)
            for c in classes
        )
        assert has_extends, "Expected at least one class with inheritance"

    def test_at_least_one_class_has_implements(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        has_implements = any(
            any(r.type == "Implements" for r in c.references)
            for c in classes
        )
        assert has_implements, "Expected at least one class implementing an interface"

    def test_class_children_map_to_units(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class" and len(u.children) > 0]
        assert len(classes) > 0
        for cls in classes:
            child_units = [
                u for u in result.units
                if u.type == "Function" and u.parentName == cls.qualifiedName
            ]
            assert len(child_units) > 0, (
                f"Class '{cls.name}' has children but no Function units reference it as parent"
            )

    # ── Functions ──────────────────────────────────────────────────────

    def test_functions_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        assert len(functions) > 0

    def test_methods_have_parent_and_qualified_name(self, load_fixture):
        result = self._parse(load_fixture)
        methods = [
            u for u in result.units if u.type == "Function" and u.parentName is not None
        ]
        assert len(methods) > 0
        for method in methods:
            assert method.qualifiedName == f"{method.parentName}.{method.name}"

    def test_at_least_one_standalone_function(self, load_fixture):
        result = self._parse(load_fixture)
        standalone = [
            u for u in result.units
            if u.type == "Function" and u.parentName is None
        ]
        assert len(standalone) > 0

    def test_all_functions_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        for func in functions:
            assert func.signature is not None
            assert len(func.signature) > 0

    def test_at_least_one_function_has_type_references(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        has_types = any(
            any(r.type == "UsesTypes" for r in f.references)
            for f in functions
        )
        assert has_types

    def test_at_least_one_function_has_call_references(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        has_calls = any(
            any(r.type == "Calls" for r in f.references)
            for f in functions
        )
        assert has_calls

    def test_at_least_one_decorator_reference(self, load_fixture):
        result = self._parse(load_fixture)
        has_annotations = any(
            any(r.type == "Annotations" for r in u.references)
            for u in result.units
        )
        assert has_annotations

    def test_at_least_one_override_detected(self, load_fixture):
        result = self._parse(load_fixture)
        overridden = [
            u for u in result.units
            if u.type == "Function"
            and any(r.type == "Overrides" for r in u.references)
        ]
        assert len(overridden) > 0

    def test_override_references_point_to_parent(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            for ref in unit.references:
                if ref.type == "Overrides":
                    assert ref.qualifiedTarget == unit.parentName

    def test_at_least_one_async_function(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        has_async = any("async" in (f.signature or "") for f in functions)
        assert has_async

    # ── Arrow functions ────────────────────────────────────────────────

    def test_arrow_functions_extracted_as_functions(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function" and u.parentName is None]
        arrow_fns = [f for f in functions if "=>" in (f.signature or "")]
        assert len(arrow_fns) > 0

    def test_arrow_functions_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        arrow_fns = [
            u for u in result.units
            if u.type == "Function" and u.parentName is None and "=>" in (u.signature or "")
        ]
        for fn in arrow_fns:
            assert len(fn.signature) > 0

    # ── Declarations ───────────────────────────────────────────────────

    def test_at_least_one_declaration(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        assert len(decls) > 0

    def test_at_least_one_typed_declaration(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        has_types = any(
            any(r.type == "UsesTypes" for r in d.references)
            for d in decls
        )
        assert has_types, "Expected at least one typed declaration"

    # ── TS-specific: interfaces ────────────────────────────────────────

    def test_at_least_one_interface(self, load_fixture):
        result = self._parse(load_fixture)
        interfaces = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("interface ")
        ]
        assert len(interfaces) > 0

    def test_at_least_one_interface_extends(self, load_fixture):
        result = self._parse(load_fixture)
        interfaces = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("interface ")
        ]
        has_extends = any(
            any(r.type == "Extends" for r in i.references)
            for i in interfaces
        )
        assert has_extends, "Expected at least one interface extending another"

    # ── TS-specific: type aliases ──────────────────────────────────────

    def test_type_aliases_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        assert len(decls) > 0

    # ── TS-specific: enums ─────────────────────────────────────────────

    def test_at_least_one_enum(self, load_fixture):
        result = self._parse(load_fixture)
        enums = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("enum ")
        ]
        assert len(enums) > 0

    # ── Universal invariants ───────────────────────────────────────────

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

    def test_all_units_have_names(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.name is not None
            assert len(unit.name) > 0

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_empty_file(self):
        result = self.parser.parse("", "empty.ts")
        assert len(result.units) == 1
        assert result.units[0].type == "Module"

    def test_js_file_language(self):
        source = "function hello() { return 'world'; }"
        result = self.parser.parse(source, "hello.js")
        assert result.language == "JavaScript"

    def test_tsx_file_language(self):
        result = self.parser.parse("const App = () => <div />;", "app.tsx")
        assert result.language == "TypeScript"

    def test_jsx_file_language(self):
        result = self.parser.parse("const App = () => <div />;", "app.jsx")
        assert result.language == "JavaScript"


class TestJavaScriptFixture:
    """Validate the JS path — no TS-specific nodes should appear."""

    def setup_method(self):
        self.parser = TypeScriptParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.js")
        return self.parser.parse(source, JS_FILE_PATH)

    def test_language_is_javascript(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.language == "JavaScript"

    def test_module_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        assert module.type == "Module"
        assert module.name is not None
        assert len(module.name) > 0

    def test_has_imports(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1
        assert all(r.type == "Imports" for r in import_blocks[0].references)

    def test_has_classes(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        assert len(classes) > 0

    def test_at_least_one_class_has_extends(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class"]
        has_extends = any(
            any(r.type == "Extends" for r in c.references)
            for c in classes
        )
        assert has_extends

    def test_has_functions(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        assert len(functions) > 0

    def test_has_standalone_and_methods(self, load_fixture):
        result = self._parse(load_fixture)
        standalone = [u for u in result.units if u.type == "Function" and u.parentName is None]
        methods = [u for u in result.units if u.type == "Function" and u.parentName is not None]
        assert len(standalone) > 0
        assert len(methods) > 0

    def test_has_arrow_functions(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function" and u.parentName is None]
        arrow_fns = [f for f in functions if "=>" in (f.signature or "")]
        assert len(arrow_fns) > 0

    def test_has_async_functions(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        has_async = any("async" in (f.signature or "") for f in functions)
        assert has_async

    def test_has_call_references(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        has_calls = any(
            any(r.type == "Calls" for r in f.references)
            for f in functions
        )
        assert has_calls

    def test_no_type_references(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        type_refs = [r for f in functions for r in f.references if r.type == "UsesTypes"]
        assert len(type_refs) == 0, "JS files should have no type references"

    def test_no_interfaces_or_enums(self, load_fixture):
        result = self._parse(load_fixture)
        ts_only = [
            u for u in result.units
            if u.type == "Class"
            and any(
                (u.signature or "").startswith(kw)
                for kw in ("interface ", "enum ")
            )
        ]
        assert len(ts_only) == 0, "JS files should have no interfaces or enums"

    def test_all_units_valid(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.sourceText is not None and len(unit.sourceText) > 0
            assert unit.startLine >= 1
            assert unit.endLine >= unit.startLine