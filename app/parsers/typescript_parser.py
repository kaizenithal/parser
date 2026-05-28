"""
TypeScript / JavaScript parser using tree-sitter via tree-sitter-language-pack.

Handles .ts, .tsx, .js, and .jsx files with a single parser.
TypeScript's grammar is a superset of JavaScript — TS-specific node types
(interfaces, type annotations, enums) simply don't appear when parsing JS.

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


class TypeScriptParser(BaseParser):
    def __init__(self):
        self._ts_parser = get_ts_parser("typescript")
        self._js_parser = get_ts_parser("javascript")

    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        is_ts = file_path.endswith((".ts", ".tsx"))
        language = CodeLanguage.TypeScript if is_ts else CodeLanguage.JavaScript
        parser = self._ts_parser if is_ts else self._js_parser

        source_bytes = source_text.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        units: list[CodeUnit] = []
        top_level_children: list[str] = []

        import_unit, import_references = self._extract_imports(
            root, source_bytes, file_path, language
        )
        if import_unit:
            units.append(import_unit)

        for child in root.children:
            extracted = self._extract_top_level_node(
                child, source_bytes, file_path, language
            )
            if extracted is None:
                continue

            if isinstance(extracted, tuple):
                class_unit, member_units = extracted
                units.append(class_unit)
                units.extend(member_units)
                top_level_children.append(class_unit.name)
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

    # ── Top-level dispatch ─────────────────────────────────────────────────

    def _extract_top_level_node(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit | tuple[CodeUnit, list[CodeUnit]] | None:
        """Route a top-level AST node to the appropriate extractor."""

        # Unwrap export wrappers to get the actual declaration
        inner = node
        is_exported = False

        if node.type in ("export_statement", "export_default_declaration"):
            is_exported = True
            declaration = _find_child_by_type(node, "declaration") or _find_first_by_types(
                node,
                [
                    "class_declaration",
                    "abstract_class_declaration",
                    "function_declaration",
                    "generator_function_declaration",
                    "lexical_declaration",
                    "variable_declaration",
                    "interface_declaration",
                    "type_alias_declaration",
                    "enum_declaration",
                ],
            )
            if declaration:
                inner = declaration
            else:
                return None

        if inner.type in ("class_declaration", "abstract_class_declaration"):
            return self._extract_class(inner, source_bytes, file_path, language)

        if inner.type in ("function_declaration", "generator_function_declaration"):
            return self._extract_function(inner, source_bytes, file_path, language)

        if inner.type in ("lexical_declaration", "variable_declaration"):
            return self._extract_declaration(inner, source_bytes, file_path, language)

        # TS-specific: interfaces and type aliases act like class-level constructs
        if inner.type == "interface_declaration":
            return self._extract_interface(inner, source_bytes, file_path, language)

        if inner.type == "type_alias_declaration":
            return self._extract_type_alias(inner, source_bytes, file_path, language)

        if inner.type == "enum_declaration":
            return self._extract_enum(inner, source_bytes, file_path, language)

        return None

    # ── Import extraction ──────────────────────────────────────────────────

    def _extract_imports(
        self,
        root_node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> tuple[CodeUnit | None, list[CodeReference]]:
        import_nodes: list[Node] = []
        references: list[CodeReference] = []

        for child in root_node.children:
            if child.type != "import_statement":
                continue

            import_nodes.append(child)

            source_node = _find_child_by_type(child, "string") or _find_child_by_type(
                child, "string_fragment"
            )
            if source_node:
                raw = _node_text(source_node, source_bytes).strip("'\"")
                short_name = (
                    raw.rsplit("/", 1)[-1]
                    .removesuffix(".ts")
                    .removesuffix(".tsx")
                    .removesuffix(".js")
                    .removesuffix(".jsx")
                )
                references.append(CodeReference(
                    type=ReferenceType.Imports,
                    target=short_name,
                    qualifiedTarget=raw,
                ))

        if not import_nodes:
            return None, []

        import_text = "\n".join(_node_text(n, source_bytes) for n in import_nodes)

        import_unit = CodeUnit(
            type=UnitType.ImportBlock,
            name="imports",
            language=language,
            sourceText=import_text,
            references=references,
            filePath=file_path,
            startLine=_node_start_line(import_nodes[0]),
            endLine=_node_end_line(import_nodes[-1]),
        )

        return import_unit, references

    # ── Function extraction ────────────────────────────────────────────────

    def _extract_function(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit:
        references: list[CodeReference] = []

        # Decorators (TS experimental / JS proposals)
        references.extend(self._extract_decorator_references(node, source_bytes))

        name_node = _find_child_by_type(node, "identifier")
        func_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        # Type annotations on parameters and return type (TS)
        references.extend(self._extract_type_annotation_references(node, source_bytes))

        # Call references from function body
        body = _find_child_by_type(node, "statement_block")
        if body:
            references.extend(self._extract_call_references(body, source_bytes))

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

    # ── Class extraction ───────────────────────────────────────────────────

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

        references.extend(self._extract_decorator_references(node, source_bytes))

        name_node = _find_child_by_type(node, "type_identifier") or _find_child_by_type(
            node, "identifier"
        )
        class_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"
        qualified_name = f"{parent_name}.{class_name}" if parent_name else class_name

        # extends
        heritage = _find_child_by_type(node, "class_heritage")
        if heritage:
            extends_clause = _find_child_by_type(heritage, "extends_clause")
            if extends_clause:
                ext_type = _find_first_by_types(
                    extends_clause, ["type_identifier", "identifier"]
                )
                if ext_type:
                    references.append(CodeReference(
                        type=ReferenceType.Extends,
                        target=_node_text(ext_type, source_bytes),
                    ))
            else:
                # JS grammar: identifier is direct child of class_heritage
                ext_type = _find_child_by_type(heritage, "identifier")
                if ext_type:
                    references.append(CodeReference(
                        type=ReferenceType.Extends,
                        target=_node_text(ext_type, source_bytes),
                    ))

            # implements (TS)
            implements_clause = _find_child_by_type(heritage, "implements_clause")
            if implements_clause:
                for type_id in _collect_descendants_by_type(
                    implements_clause, "type_identifier"
                ):
                    references.append(CodeReference(
                        type=ReferenceType.Implements,
                        target=_node_text(type_id, source_bytes),
                    ))

        # Class body
        class_body = _find_child_by_type(node, "class_body")
        if class_body:
            for member in class_body.children:
                if member.type in ("{", "}"):
                    continue

                method_unit = self._extract_class_member(
                    member, source_bytes, file_path, language, parent_name=qualified_name
                )
                if method_unit:
                    member_units.append(method_unit)
                    children.append(method_unit.name)

        # Signature
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

    def _extract_class_member(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        """Extract a single class body member (method, property, constructor)."""

        if node.type == "method_definition":
            return self._extract_method(node, source_bytes, file_path, language, parent_name)

        if node.type == "public_field_definition":
            return self._extract_field(node, source_bytes, file_path, language, parent_name)

        # TS-specific abstract members, index signatures, etc. — skip for now
        return None

    def _extract_method(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit:
        references: list[CodeReference] = []

        references.extend(self._extract_decorator_references(node, source_bytes))

        name_node = _find_child_by_type(node, "property_identifier") or _find_child_by_type(
            node, "identifier"
        )
        method_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        # Check for constructor
        if method_name == "constructor":
            pass  # still a Function unit, just named "constructor"

        # Override detection
        is_override = self._is_override_method(node, source_bytes)
        if is_override and parent_name:
            references.append(CodeReference(
                type=ReferenceType.Overrides,
                target=method_name,
                qualifiedTarget=parent_name,
            ))

        references.extend(self._extract_type_annotation_references(node, source_bytes))

        body = _find_child_by_type(node, "statement_block")
        if body:
            references.extend(self._extract_call_references(body, source_bytes))

        qualified_name = f"{parent_name}.{method_name}" if parent_name else method_name

        return CodeUnit(
            type=UnitType.Function,
            name=method_name,
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

    def _extract_field(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        name_node = _find_child_by_type(node, "property_identifier") or _find_child_by_type(
            node, "identifier"
        )
        if not name_node:
            return None

        name = _node_text(name_node, source_bytes)
        references: list[CodeReference] = []

        # Type annotation on field (TS)
        type_ann = _find_child_by_type(node, "type_annotation")
        if type_ann:
            for type_id in _collect_descendants_by_type(type_ann, "type_identifier"):
                references.append(CodeReference(
                    type=ReferenceType.UsesTypes,
                    target=_node_text(type_id, source_bytes),
                ))

        source = _node_text(node, source_bytes)

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=f"{parent_name}.{name}" if parent_name else name,
            language=language,
            sourceText=source,
            signature=source.split("\n")[0].strip().rstrip(";"),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Declaration extraction (top-level const/let/var) ───────────────────

    def _extract_declaration(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit | None:
        # lexical_declaration contains variable_declarator children
        declarator = _find_child_by_type(node, "variable_declarator")
        if not declarator:
            return None

        name_node = _find_child_by_type(declarator, "identifier")
        if not name_node:
            return None

        name = _node_text(name_node, source_bytes)
        references: list[CodeReference] = []

        # Type annotation (TS)
        type_ann = _find_child_by_type(declarator, "type_annotation")
        if type_ann:
            for type_id in _collect_descendants_by_type(type_ann, "type_identifier"):
                references.append(CodeReference(
                    type=ReferenceType.UsesTypes,
                    target=_node_text(type_id, source_bytes),
                ))

        # If the value is an arrow function or function expression, extract calls
        value = _find_first_by_types(
            declarator, ["arrow_function", "function_expression", "function"]
        )
        if value:
            body = _find_child_by_type(value, "statement_block") or _find_child_by_type(
                value, "expression_statement"
            )
            if body:
                references.extend(self._extract_call_references(body, source_bytes))

            # For arrow functions / function expressions assigned to const,
            # treat them as Function units since that's what they semantically are
            return CodeUnit(
                type=UnitType.Function,
                name=name,
                qualifiedName=name,
                language=language,
                sourceText=_node_text(node, source_bytes),
                signature=self._build_arrow_signature(node, declarator, source_bytes),
                references=references,
                filePath=file_path,
                startLine=_node_start_line(node),
                endLine=_node_end_line(node),
            )

        source = _node_text(node, source_bytes)

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=source,
            signature=source.split("\n")[0].strip().rstrip(";"),
            references=references,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── TS-specific: interface, type alias, enum ───────────────────────────

    def _extract_interface(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        name_node = _find_child_by_type(node, "type_identifier")
        name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        references: list[CodeReference] = []

        # extends clause on interface
        extends = _find_child_by_type(node, "extends_type_clause")
        if extends:
            for type_id in _collect_descendants_by_type(extends, "type_identifier"):
                references.append(CodeReference(
                    type=ReferenceType.Extends,
                    target=_node_text(type_id, source_bytes),
                ))

        signature = f"interface {name}"
        if extends:
            extends_text = _node_text(extends, source_bytes)
            signature = f"interface {name} {extends_text}"

        class_unit = CodeUnit(
            type=UnitType.Class,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=signature,
            references=references,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

        # Interfaces don't have executable members, so no child units
        return class_unit, []

    def _extract_type_alias(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit:
        name_node = _find_child_by_type(node, "type_identifier")
        name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        references: list[CodeReference] = []
        # Collect type references in the alias body
        for type_id in _collect_descendants_by_type(node, "type_identifier"):
            type_name = _node_text(type_id, source_bytes)
            if type_name != name:  # skip self-reference
                references.append(CodeReference(
                    type=ReferenceType.UsesTypes,
                    target=type_name,
                ))

        source = _node_text(node, source_bytes)

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=source,
            signature=source.split("\n")[0].strip().rstrip(";"),
            references=references,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    def _extract_enum(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        language: CodeLanguage,
    ) -> CodeUnit:
        name_node = _find_child_by_type(node, "identifier")
        name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"

        return CodeUnit(
            type=UnitType.Class,
            name=name,
            qualifiedName=name,
            language=language,
            sourceText=_node_text(node, source_bytes),
            signature=f"enum {name}",
            references=[],
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Reference extraction helpers ───────────────────────────────────────

    def _extract_decorator_references(
        self, node: Node, source_bytes: bytes
    ) -> list[CodeReference]:
        references: list[CodeReference] = []

        for child in node.children:
            if child.type != "decorator":
                continue

            # Decorator can contain an identifier or call_expression
            id_node = _find_child_by_type(child, "identifier")
            call_node = _find_child_by_type(child, "call_expression")

            if call_node:
                func = _find_child_by_type(call_node, "identifier") or _find_child_by_type(
                    call_node, "member_expression"
                )
                if func:
                    references.append(CodeReference(
                        type=ReferenceType.Annotations,
                        target=_node_text(func, source_bytes),
                    ))
            elif id_node:
                references.append(CodeReference(
                    type=ReferenceType.Annotations,
                    target=_node_text(id_node, source_bytes),
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
            elif func.type == "member_expression":
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

    def _extract_type_annotation_references(
        self, node: Node, source_bytes: bytes
    ) -> list[CodeReference]:
        """Extract type references from type annotations (TS only — no-ops for JS)."""
        references: list[CodeReference] = []
        seen: set[str] = set()

        for type_ann in _collect_descendants_by_type(node, "type_annotation"):
            for type_id in _collect_descendants_by_type(type_ann, "type_identifier"):
                type_name = _node_text(type_id, source_bytes)
                if type_name not in seen:
                    seen.add(type_name)
                    references.append(CodeReference(
                        type=ReferenceType.UsesTypes,
                        target=type_name,
                    ))

        return references

    def _is_override_method(self, node: Node, source_bytes: bytes) -> bool:
        """Check if a method has the override keyword (TS) or @override decorator."""
        for child in node.children:
            if child.type == "override_modifier":
                return True
            if child.type == "decorator":
                id_node = _find_child_by_type(child, "identifier")
                if id_node and _node_text(id_node, source_bytes) == "override":
                    return True
        return False

    # ── Signature builders ─────────────────────────────────────────────────

    def _build_function_signature(self, node: Node, source_bytes: bytes) -> str:
        """Build a concise signature string for a function/method node."""
        source = _node_text(node, source_bytes)
        # Signature is everything before the opening brace
        brace_idx = source.find("{")
        if brace_idx != -1:
            sig = source[:brace_idx].strip()
        else:
            sig = source.split("\n")[0].strip()
        return sig

    def _build_class_signature(self, node: Node, source_bytes: bytes) -> str:
        """Build a signature like 'class Foo extends Bar implements Baz'."""
        source = _node_text(node, source_bytes)
        brace_idx = source.find("{")
        if brace_idx != -1:
            return source[:brace_idx].strip()
        return source.split("\n")[0].strip()

    def _build_arrow_signature(
        self, decl_node: Node, declarator: Node, source_bytes: bytes
    ) -> str:
        """Build a signature for `const foo = (...) => ...`."""
        source = _node_text(decl_node, source_bytes)
        # Grab up to the arrow or opening brace
        for marker in ("=> {", "=>"):
            idx = source.find(marker)
            if idx != -1:
                return source[: idx + len(marker)].strip()
        return source.split("\n")[0].strip()


# ── Tree-sitter node helpers (module-level, stateless) ─────────────────────


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


def _find_first_by_types(node: Node, type_names: list[str]) -> Node | None:
    type_set = set(type_names)
    for child in node.children:
        if child.type in type_set:
            return child
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
    for suffix in (".tsx", ".ts", ".jsx", ".js"):
        if file_path.endswith(suffix):
            return suffix
    return ""