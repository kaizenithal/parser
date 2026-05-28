"""
C / C++ parser using tree-sitter via tree-sitter-language-pack.

Handles .c, .h, .cpp, .hpp, .cc, .cxx, .hxx files with a single parser.
C++ grammar is a superset of C — C++-specific node types (classes,
templates, namespaces) simply don't appear when parsing C.

All filesystem access removed — operates entirely on in-memory source text.
"""

from tree_sitter import Node
from tree_sitter_language_pack import get_parser as get_ts_parser

from ..models import (
    CodeParsingResult,
    CodeReference,
    CodeUnit,
    Language as CodeLanguage,
    ReferenceType,
    UnitType,
)
from .base import BaseParser


# Extensions that should use the C parser (not C++)
_C_EXTENSIONS = (".c", ".h")
_CPP_EXTENSIONS = (".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".h++", ".hh")


class CppParser(BaseParser):
    def __init__(self):
        self._cpp_parser = get_ts_parser("cpp")
        self._c_parser = get_ts_parser("c")

    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        is_cpp = self._is_cpp_file(file_path)
        language = CodeLanguage.Cpp if is_cpp else CodeLanguage.C
        parser = self._cpp_parser if is_cpp else self._c_parser

        source_bytes = source_text.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        units: list[CodeUnit] = []
        top_level_children: list[str] = []

        import_unit, import_references = self._extract_includes(
            root, source_bytes, file_path, language
        )
        if import_unit:
            units.append(import_unit)

        for child in self._effective_children(root):
            extracted = self._extract_top_level_node(
                child, source_bytes, file_path, language
            )
            if extracted is None:
                continue

            if isinstance(extracted, tuple):
                parent_unit, member_units = extracted
                units.append(parent_unit)
                units.extend(member_units)
                top_level_children.append(parent_unit.name)
            else:
                units.append(extracted)
                top_level_children.append(extracted.name)

        # Module unit
        suffix = _file_suffix(file_path)
        module_name = file_path.rsplit("/", 1)[-1].removesuffix(suffix)

        units.insert(0, CodeUnit(
            type=UnitType.Module,
            name=module_name,
            qualifiedName=module_name,
            language=language,
            sourceText=source_text,
            references=import_references,
            filePath=file_path,
            startLine=1,
            endLine=len(source_text.splitlines()),
            children=top_level_children,
        ))

        return CodeParsingResult(
            units=units,
            filePath=file_path,
            language=language,
        )

    def _is_cpp_file(self, file_path: str) -> bool:
        lower = file_path.lower()
        for ext in _CPP_EXTENSIONS:
            if lower.endswith(ext):
                return True
        # .h is ambiguous — default to C unless parsed with C++ features
        return False

    # ── Top-level dispatch ─────────────────────────────────────────────

    def _effective_children(self, root: Node) -> list[Node]:
        """Flatten preprocessor guard blocks to get effective top-level nodes."""
        children = []
        for child in root.children:
            if child.type in ("preproc_ifdef", "preproc_if", "preproc_else"):
                children.extend(c for c in child.children)
            else:
                children.append(child)
        return children

    def _extract_top_level_node(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit | tuple[CodeUnit, list[CodeUnit]] | None:

        if node.type == "function_definition":
            return self._extract_function(node, source_bytes, file_path, language)

        if node.type == "declaration":
            return self._extract_declaration(node, source_bytes, file_path, language)

        if node.type in ("struct_specifier", "union_specifier"):
            return self._extract_struct(node, source_bytes, file_path, language)

        if node.type in ("enum_specifier", "enum_class_specifier"):
            return self._extract_enum(node, source_bytes, file_path, language)

        if node.type == "type_definition":
            return self._extract_typedef(node, source_bytes, file_path, language)

        # C++ specific
        if node.type == "class_specifier":
            return self._extract_class(node, source_bytes, file_path, language)

        if node.type == "namespace_definition":
            return self._extract_namespace(node, source_bytes, file_path, language)

        if node.type == "template_declaration":
            return self._extract_template(node, source_bytes, file_path, language)

        if node.type in ("preproc_ifdef", "preproc_if", "preproc_else"):
            results = []
            for child in node.children:
                extracted = self._extract_top_level_node(child, source_bytes, file_path, language)
                if extracted is not None:
                    if isinstance(results, list):
                        results.append(extracted)
            return results if len(results) == 1 else results or None

        return None

    # ── Include extraction ─────────────────────────────────────────────

    def _extract_includes(
        self,
        root_node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> tuple[CodeUnit | None, list[CodeReference]]:
        include_nodes: list[Node] = []
        references: list[CodeReference] = []

        for child in self._effective_children(root_node):
            if child.type != "preproc_include":
                continue

            include_nodes.append(child)

            path_node = _find_child_by_type(child, "string_literal") or \
                        _find_child_by_type(child, "system_lib_string")
            if path_node:
                raw = _node_text(path_node, source_bytes).strip('"<>')
                short_name = raw.rsplit("/", 1)[-1]
                for ext in (".h", ".hpp", ".hxx", ".hh"):
                    short_name = short_name.removesuffix(ext)
                references.append(CodeReference(
                    type=ReferenceType.Imports,
                    target=short_name,
                    qualifiedTarget=raw,
                ))

        if not include_nodes:
            return None, []

        include_text = "\n".join(_node_text(n, source_bytes) for n in include_nodes)

        import_unit = CodeUnit(
            type=UnitType.ImportBlock,
            name="includes",
            language=language,
            sourceText=include_text,
            references=references,
            filePath=file_path,
            startLine=_node_start_line(include_nodes[0]),
            endLine=_node_end_line(include_nodes[-1]),
        )

        return import_unit, references

    # ── Function extraction ────────────────────────────────────────────

    def _extract_function(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit:
        references: list[CodeReference] = []

        # Find function name from declarator
        func_name = self._extract_function_name(node, source_bytes)

        # Extract type references from parameters and return type
        references.extend(self._extract_type_references(node, source_bytes))

        # Extract call references from body
        body = _find_child_by_type(node, "compound_statement")
        if body:
            references.extend(self._extract_call_references(body, source_bytes))

        # Check for override keyword in source
        source = _node_text(node, source_bytes)
        if "override" in source and parent_name:
            references.append(CodeReference(
                type=ReferenceType.Overrides,
                target=func_name,
                qualifiedTarget=parent_name,
            ))
        qualified_name = f"{parent_name}.{func_name}" if parent_name else func_name

        return CodeUnit(
            type=UnitType.Function,
            name=func_name,
            qualifiedName=qualified_name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=self._build_function_signature(node, source_bytes),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    def _extract_function_name(self, node: Node, source_bytes: bytes) -> str:
        """Extract function name, handling nested declarators."""
        declarator = _find_child_by_type(node, "function_declarator") or \
                     _find_child_by_type(node, "pointer_declarator")

        if declarator is None:
            # Walk children for a declarator
            for child in node.children:
                if "declarator" in child.type:
                    declarator = child
                    break

        if declarator is None:
            return "<anonymous>"

        # Drill into nested declarators to find the identifier
        current = declarator
        while current:
            id_node = _find_child_by_type(current, "identifier") or \
                      _find_child_by_type(current, "field_identifier")
            if id_node:
                return _node_text(id_node, source_bytes)

            # C++ qualified names
            qualified = _find_child_by_type(current, "qualified_identifier")
            if qualified:
                return _node_text(qualified, source_bytes)

            # Drill deeper
            next_decl = None
            for child in current.children:
                if "declarator" in child.type:
                    next_decl = child
                    break
            current = next_decl

        return "<anonymous>"

    # ── Class extraction (C++) ─────────────────────────────────────────

    def _extract_class(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        references: list[CodeReference] = []
        children: list[str] = []
        member_units: list[CodeUnit] = []

        name_node = _find_child_by_type(node, "type_identifier") or \
                    _find_child_by_type(node, "identifier")
        class_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"
        qualified_name = f"{parent_name}.{class_name}" if parent_name else class_name

        # Base class specifiers
        base_list = _find_child_by_type(node, "base_class_clause")
        if base_list:
            for type_id in _collect_descendants_by_type(base_list, "type_identifier"):
                references.append(CodeReference(
                    type=ReferenceType.Extends,
                    target=_node_text(type_id, source_bytes),
                ))

        # Class body
        field_list = _find_child_by_type(node, "field_declaration_list")
        if field_list:
            for member in field_list.children:
                if member.type in ("{", "}", "access_specifier"):
                    continue

                if member.type == "function_definition":
                    method = self._extract_function(
                        member, source_bytes, file_path, language,
                        parent_name=qualified_name,
                    )
                    member_units.append(method)
                    children.append(method.name)

                elif member.type == "declaration":
                    # Could be a method declaration or field
                    has_func_decl = _find_descendant_by_type(member, "function_declarator")
                    if has_func_decl:
                        decl = self._extract_method_declaration(
                            member, source_bytes, file_path, language,
                            parent_name=qualified_name,
                        )
                        if decl:
                            member_units.append(decl)
                            children.append(decl.name)
                    else:
                        field = self._extract_field(
                            member, source_bytes, file_path, language,
                            parent_name=qualified_name,
                        )
                        if field:
                            member_units.append(field)
                            children.append(field.name)

        signature = self._build_class_signature(node, source_bytes)

        class_unit = CodeUnit(
            type=UnitType.Class,
            name=class_name,
            qualifiedName=qualified_name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=signature,
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
            children=children,
        )

        return class_unit, member_units

    def _extract_method_declaration(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        """Extract a method declaration (no body, just signature)."""
        func_decl = _find_descendant_by_type(node, "function_declarator")
        if not func_decl:
            return None

        id_node = _find_child_by_type(func_decl, "identifier") or \
                  _find_child_by_type(func_decl, "field_identifier")
        name = _node_text(id_node, source_bytes) if id_node else "<anonymous>"

        references = self._extract_type_references(node, source_bytes)

        # Check for virtual/override
        source = _node_text(node, source_bytes)
        if "override" in source:
            references.append(CodeReference(
                type=ReferenceType.Overrides,
                target=name,
                qualifiedTarget=parent_name,
            ))

        qualified_name = f"{parent_name}.{name}" if parent_name else name

        return CodeUnit(
            type=UnitType.Function,
            name=name,
            qualifiedName=qualified_name,
            language=language,
            sourceText=source,
            signature=source.strip().rstrip(";"),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    def _extract_field(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        """Extract a class/struct field declaration."""
        id_node = _find_descendant_by_type(node, "field_identifier") or \
                  _find_descendant_by_type(node, "identifier")
        if not id_node:
            return None

        name = _node_text(id_node, source_bytes)
        references = self._extract_type_references(node, source_bytes)
        source = _node_text(node, source_bytes)

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=f"{parent_name}.{name}" if parent_name else name,
            language=language,
            sourceText=source,
            signature=source.strip().rstrip(";"),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Struct extraction ──────────────────────────────────────────────

    def _extract_struct(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        name_node = _find_child_by_type(node, "type_identifier") or \
                    _find_child_by_type(node, "identifier")
        struct_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"
        qualified_name = f"{parent_name}.{struct_name}" if parent_name else struct_name

        children: list[str] = []
        member_units: list[CodeUnit] = []

        field_list = _find_child_by_type(node, "field_declaration_list")
        if field_list:
            for member in field_list.children:
                if member.type in ("{", "}"):
                    continue
                if member.type == "field_declaration":
                    field = self._extract_field(
                        member, source_bytes, file_path, language,
                        parent_name=qualified_name,
                    )
                    if field:
                        member_units.append(field)
                        children.append(field.name)

        keyword = "union" if node.type == "union_specifier" else "struct"
        signature = f"{keyword} {struct_name}"

        struct_unit = CodeUnit(
            type=UnitType.Class,
            name=struct_name,
            qualifiedName=qualified_name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=signature,
            references=[],
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
            children=children,
        )

        return struct_unit, member_units

    # ── Enum extraction ────────────────────────────────────────────────

    def _extract_enum(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit:
        name_node = _find_child_by_type(node, "type_identifier") or \
                    _find_child_by_type(node, "identifier")
        name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        keyword = "enum class" if node.type == "enum_class_specifier" else "enum"

        return CodeUnit(
            type=UnitType.Class,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=f"{keyword} {name}",
            references=[],
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Typedef extraction ─────────────────────────────────────────────

    def _extract_typedef(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit | tuple[CodeUnit, list[CodeUnit]] | None:
        """Extract typedef. If it wraps a struct/enum, extract that instead."""
        # Check if typedef wraps a struct or enum
        inner_struct = _find_child_by_type(node, "struct_specifier") or \
                       _find_child_by_type(node, "union_specifier")
        inner_enum = _find_child_by_type(node, "enum_specifier")

        if inner_struct:
            typedef_name = _find_child_by_type(node, "type_identifier")
            if typedef_name:
                result = self._extract_struct(
                    inner_struct, source_bytes, file_path, language
                )
                struct_unit, members = result
                name = _node_text(typedef_name, source_bytes)
                # Update member parentName to match the typedef name
                members = [
                    CodeUnit(
                        type=m.type,
                        name=m.name,
                        qualifiedName=f"{name}.{m.name}",
                        language=language,
                        sourceText=m.sourceText,
                        signature=m.signature,
                        references=m.references,
                        parentName=name,
                        filePath=file_path,
                        startLine=m.startLine,
                        endLine=m.endLine,
                    )
                    for m in members
                ]
                struct_unit = CodeUnit(
                    type=struct_unit.type,
                    name=name,
                    qualifiedName=name,
                    language=language,
                    sourceText=_node_text(node, source_bytes),
                    signature=struct_unit.signature,
                    references=struct_unit.references,
                    filePath=file_path,
                    startLine=_node_start_line(node),
                    endLine=_node_end_line(node),
                    children=struct_unit.children,
                )
                return struct_unit, members

        if inner_enum:
            typedef_name = _find_child_by_type(node, "type_identifier")
            if typedef_name:
                enum_unit = self._extract_enum(
                    inner_enum, source_bytes, file_path, language
                )
                name = _node_text(typedef_name, source_bytes)
                return CodeUnit(
                    type=enum_unit.type,
                    name=name,
                    qualifiedName=name,
                    language=language,
                    sourceText=_node_text(node, source_bytes),
                    signature=enum_unit.signature,
                    references=[],
                    filePath=file_path,
                    startLine=_node_start_line(node),
                    endLine=_node_end_line(node),
                )

        # Simple typedef (e.g. typedef int MyInt;)
        source = _node_text(node, source_bytes)
        id_node = None
        # The last type_identifier is usually the new name
        type_ids = _collect_descendants_by_type(node, "type_identifier")
        if type_ids:
            id_node = type_ids[-1]

        name = _node_text(id_node, source_bytes) if id_node else "<anonymous>"

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=source,
            signature=source.strip().rstrip(";"),
            references=[],
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Declaration extraction (top-level variables) ───────────────────

    def _extract_declaration(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit | None:
        """Extract top-level variable/constant declarations."""
        # Skip function declarations (prototypes) — they have function_declarator
        if _find_descendant_by_type(node, "function_declarator"):
            return None

        id_node = _find_descendant_by_type(node, "identifier")
        if not id_node:
            return None

        name = _node_text(id_node, source_bytes)
        references = self._extract_type_references(node, source_bytes)
        source = _node_text(node, source_bytes)

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=source,
            signature=source.strip().rstrip(";"),
            references=references,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Namespace extraction (C++) ─────────────────────────────────────

    def _extract_namespace(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        name_node = _find_child_by_type(node, "identifier")
        ns_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        children: list[str] = []
        member_units: list[CodeUnit] = []

        body = _find_child_by_type(node, "declaration_list")
        if body:
            for child in body.children:
                extracted = self._extract_top_level_node(
                    child, source_bytes, file_path, language
                )
                if extracted is None:
                    continue
                if isinstance(extracted, tuple):
                    unit, members = extracted
                    member_units.append(unit)
                    member_units.extend(members)
                    children.append(unit.name)
                else:
                    # Set parent name for namespace members
                    extracted = CodeUnit(
                        type=extracted.type,
                        name=extracted.name,
                        qualifiedName=f"{ns_name}.{extracted.name}",
                        language=language,
                        sourceText=extracted.sourceText,
                        signature=extracted.signature,
                        references=extracted.references,
                        parentName=ns_name,
                        filePath=file_path,
                        startLine=extracted.startLine,
                        endLine=extracted.endLine,
                    )
                    member_units.append(extracted)
                    children.append(extracted.name)

        ns_unit = CodeUnit(
            type=UnitType.Class,
            name=ns_name,
            qualifiedName=ns_name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=f"namespace {ns_name}",
            references=[],
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
            children=children,
        )

        return ns_unit, member_units

    # ── Template extraction (C++) ──────────────────────────────────────

    def _extract_template(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit | tuple[CodeUnit, list[CodeUnit]] | None:
        """Extract a template declaration by delegating to the inner declaration."""
        # The template wraps a function_definition, class_specifier, or declaration
        for child in node.children:
            result = self._extract_top_level_node(
                child, source_bytes, file_path, language
            )
            if result is not None:
                # Replace source text with the full template text
                if isinstance(result, tuple):
                    unit, members = result
                    unit = CodeUnit(
                        type=unit.type,
                        name=unit.name,
                        qualifiedName=unit.qualifiedName,
                        language=language,
                        sourceText=_node_text(node, source_bytes),
                        signature=self._build_function_signature(node, source_bytes),
                        references=unit.references,
                        parentName=unit.parentName,
                        filePath=file_path,
                        startLine=_node_start_line(node),
                        endLine=_node_end_line(node),
                        children=unit.children,
                    )
                    return unit, members
                else:
                    return CodeUnit(
                        type=result.type,
                        name=result.name,
                        qualifiedName=result.qualifiedName,
                        language=language,
                        sourceText=_node_text(node, source_bytes),
                        signature=self._build_function_signature(node, source_bytes),
                        references=result.references,
                        filePath=file_path,
                        startLine=_node_start_line(node),
                        endLine=_node_end_line(node),
                    )
        return None

    # ── Reference extraction helpers ───────────────────────────────────

    def _extract_type_references(
        self, node: Node, source_bytes: bytes
    ) -> list[CodeReference]:
        references: list[CodeReference] = []
        seen: set[str] = set()

        for type_id in _collect_descendants_by_type(node, "type_identifier"):
            type_name = _node_text(type_id, source_bytes)
            if type_name not in seen:
                seen.add(type_name)
                references.append(CodeReference(
                    type=ReferenceType.UsesTypes,
                    target=type_name,
                ))

        return references

    def _extract_call_references(
        self, node: Node, source_bytes: bytes
    ) -> list[CodeReference]:
        references: list[CodeReference] = []
        seen: set[str] = set()

        for call in _collect_descendants_by_type(node, "call_expression"):
            func = call.children[0] if call.children else None
            if func is None:
                continue

            if func.type == "identifier":
                target = _node_text(func, source_bytes)
            elif func.type == "field_expression":
                target = _node_text(func, source_bytes)
            elif func.type == "qualified_identifier":
                target = _node_text(func, source_bytes)
            else:
                continue

            if target and target not in seen:
                seen.add(target)
                references.append(CodeReference(
                    type=ReferenceType.Calls,
                    target=target,
                ))

        return references

    # ── Signature builders ─────────────────────────────────────────────

    def _build_function_signature(self, node: Node, source_bytes: bytes) -> str:
        source = _node_text(node, source_bytes)
        brace_idx = source.find("{")
        if brace_idx != -1:
            sig = source[:brace_idx].strip()
        else:
            sig = source.split("\n")[0].strip()
        return sig

    def _build_class_signature(self, node: Node, source_bytes: bytes) -> str:
        source = _node_text(node, source_bytes)
        brace_idx = source.find("{")
        if brace_idx != -1:
            return source[:brace_idx].strip()
        return source.split("\n")[0].strip()


# ── Tree-sitter node helpers (module-level, stateless) ─────────────────


def _node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8")


def _node_start_line(node: Node) -> int:
    return node.start_point[0] + 1


def _node_end_line(node: Node) -> int:
    return node.end_point[0] + 1


def _find_child_by_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_children_by_type(node: Node, type_name: str) -> list[Node]:
    return [child for child in node.children if child.type == type_name]


def _find_descendant_by_type(node: Node, type_name: str) -> Node | None:
    """Find first descendant of a given type (DFS)."""
    for child in node.children:
        if child.type == type_name:
            return child
        found = _find_descendant_by_type(child, type_name)
        if found:
            return found
    return None


def _collect_descendants_by_type(node: Node, type_name: str) -> list[Node]:
    results: list[Node] = []

    def walk(n: Node):
        if n.type == type_name:
            results.append(n)
        for child in n.children:
            walk(child)

    walk(node)
    return results


def _file_suffix(file_path: str) -> str:
    for suffix in (".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".h++", ".hh", ".c", ".h"):
        if file_path.endswith(suffix):
            return suffix
    return ""