from app.parsers.cpp_parser import CppParser


CPP_FILE_PATH = "src/services/user_service.cpp"
C_FILE_PATH = "src/services/user_service.c"
H_FILE_PATH = "src/services/user_service.h"


class TestCppParser:
    """Tests for C++ parsing behavior. No fixture-specific names or counts."""

    def setup_method(self):
        self.parser = CppParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.cpp")
        return self.parser.parse(source, CPP_FILE_PATH)

    # ── Module invariants ──────────────────────────────────────────────

    def test_produces_valid_result(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.warnings == []
        assert result.language == "Cpp"
        assert result.filePath == CPP_FILE_PATH

    def test_module_is_first_unit(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.units[0].type == "Module"
        assert result.units[0].startLine == 1

    def test_module_end_line_matches_source(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        source_line_count = len(module.sourceText.splitlines())
        assert module.endLine == source_line_count

    def test_module_has_children(self, load_fixture):
        result = self._parse(load_fixture)
        assert len(result.units[0].children) > 0

    def test_module_children_exist_as_units(self, load_fixture):
        result = self._parse(load_fixture)
        module = result.units[0]
        unit_names = {u.name for u in result.units}
        for child in module.children:
            assert child in unit_names, f"Module child '{child}' has no corresponding unit"

    # ── Includes ───────────────────────────────────────────────────────

    def test_includes_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1

    def test_include_references_are_imports(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1
        assert len(import_blocks[0].references) > 0
        assert all(r.type == "Imports" for r in import_blocks[0].references)

    def test_include_references_have_qualified_targets(self, load_fixture):
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

    def test_class_children_map_to_units(self, load_fixture):
        result = self._parse(load_fixture)
        classes = [u for u in result.units if u.type == "Class" and len(u.children) > 0]
        for cls in classes:
            child_units = [
                u for u in result.units if u.parentName == cls.qualifiedName
            ]
            assert len(child_units) > 0, (
                f"Class '{cls.name}' has children {cls.children} but no units reference it as parent"
            )

    # ── Functions ──────────────────────────────────────────────────────

    def test_functions_extracted(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        assert len(functions) > 0

    def test_all_functions_have_signatures(self, load_fixture):
        result = self._parse(load_fixture)
        for func in (u for u in result.units if u.type == "Function"):
            assert func.signature is not None
            assert len(func.signature) > 0

    def test_methods_have_parent_and_qualified_name(self, load_fixture):
        result = self._parse(load_fixture)
        methods = [u for u in result.units if u.type == "Function" and u.parentName is not None]
        assert len(methods) > 0
        for method in methods:
            assert method.qualifiedName == f"{method.parentName}.{method.name}"

    def test_at_least_one_standalone_function(self, load_fixture):
        result = self._parse(load_fixture)
        standalone = [u for u in result.units if u.type == "Function" and u.parentName is None]
        assert len(standalone) > 0

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

    # ── Structs ────────────────────────────────────────────────────────

    def test_at_least_one_struct(self, load_fixture):
        result = self._parse(load_fixture)
        structs = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("struct ")
        ]
        assert len(structs) > 0

    def test_structs_with_children_have_matching_units(self, load_fixture):
        result = self._parse(load_fixture)
        structs = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("struct ")
            and len(u.children) > 0
        ]
        for s in structs:
            child_units = [u for u in result.units if u.parentName == s.qualifiedName]
            assert len(child_units) > 0

    # ── Enums ──────────────────────────────────────────────────────────

    def test_at_least_one_enum(self, load_fixture):
        result = self._parse(load_fixture)
        enums = [
            u for u in result.units
            if u.type == "Class" and "enum" in (u.signature or "")
        ]
        assert len(enums) > 0

    # ── Namespace ──────────────────────────────────────────────────────

    def test_at_least_one_namespace(self, load_fixture):
        result = self._parse(load_fixture)
        namespaces = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("namespace ")
        ]
        assert len(namespaces) > 0

    def test_namespace_children_have_matching_units(self, load_fixture):
        result = self._parse(load_fixture)
        namespaces = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("namespace ")
        ]
        for ns in namespaces:
            assert len(ns.children) > 0
            members = [u for u in result.units if u.parentName == ns.name]
            assert len(members) > 0

    # ── Declarations ───────────────────────────────────────────────────

    def test_at_least_one_declaration(self, load_fixture):
        result = self._parse(load_fixture)
        decls = [u for u in result.units if u.type == "Declaration"]
        assert len(decls) > 0

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

    def test_all_units_have_language(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.language == "Cpp"

    def test_all_units_have_names(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.name is not None
            assert len(unit.name) > 0

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_empty_file(self):
        result = self.parser.parse("", "empty.cpp")
        assert len(result.units) == 1
        assert result.units[0].type == "Module"

    def test_cpp_extensions(self):
        for ext in (".cpp", ".hpp", ".cc", ".cxx", ".hxx"):
            result = self.parser.parse("int x = 1;", f"test{ext}")
            assert result.language == "Cpp", f"Expected Cpp for {ext}"

    def test_c_extensions(self):
        for ext in (".c", ".h"):
            result = self.parser.parse("int x = 1;", f"test{ext}")
            assert result.language == "C", f"Expected C for {ext}"


class TestCFixture:
    """Validate C path — no C++-specific constructs should appear."""

    def setup_method(self):
        self.parser = CppParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.c")
        return self.parser.parse(source, C_FILE_PATH)

    def test_language_is_c(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.language == "C"

    def test_has_includes(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1
        assert len(import_blocks[0].references) > 0

    def test_has_functions(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        assert len(functions) > 0

    def test_has_typedefs(self, load_fixture):
        result = self._parse(load_fixture)
        non_module = [u for u in result.units if u.type in ("Class", "Declaration")]
        assert len(non_module) > 0

    def test_has_call_references(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        has_calls = any(
            any(r.type == "Calls" for r in f.references) for f in functions
        )
        assert has_calls

    def test_no_cpp_constructs(self, load_fixture):
        result = self._parse(load_fixture)
        cpp_only = [
            u for u in result.units
            if u.type == "Class"
            and any(
                (u.signature or "").startswith(kw)
                for kw in ("class ", "namespace ")
            )
        ]
        assert len(cpp_only) == 0, "C files should have no classes or namespaces"

    def test_all_units_valid(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.sourceText is not None and len(unit.sourceText) > 0
            assert unit.startLine >= 1
            assert unit.endLine >= unit.startLine


class TestCHeaderFixture:
    """Validate .h header parsing — typedefs, structs, no function bodies."""

    def setup_method(self):
        self.parser = CppParser()

    def _parse(self, load_fixture):
        source = load_fixture("test.h")
        return self.parser.parse(source, H_FILE_PATH)

    def test_language_is_c(self, load_fixture):
        result = self._parse(load_fixture)
        assert result.language == "C"

    def test_has_includes(self, load_fixture):
        result = self._parse(load_fixture)
        import_blocks = [u for u in result.units if u.type == "ImportBlock"]
        assert len(import_blocks) == 1

    def test_has_struct_or_typedef_units(self, load_fixture):
        result = self._parse(load_fixture)
        structs_or_decls = [u for u in result.units if u.type in ("Class", "Declaration")]
        assert len(structs_or_decls) > 0

    def test_no_function_implementations(self, load_fixture):
        result = self._parse(load_fixture)
        functions = [u for u in result.units if u.type == "Function"]
        assert len(functions) == 0, "Header prototypes should not produce Function units"

    def test_structs_with_children_have_field_units(self, load_fixture):
        result = self._parse(load_fixture)
        structs = [
            u for u in result.units
            if u.type == "Class" and (u.signature or "").startswith("struct ")
            and len(u.children) > 0
        ]
        for s in structs:
            child_units = [u for u in result.units if u.parentName == s.qualifiedName]
            assert len(child_units) > 0

    def test_all_units_valid(self, load_fixture):
        result = self._parse(load_fixture)
        for unit in result.units:
            assert unit.sourceText is not None and len(unit.sourceText) > 0
            assert unit.startLine >= 1
            assert unit.endLine >= unit.startLine