"""
Dart parser using tree-sitter via tree-sitter-language-pack.

Ported from the standalone dart_ast_parser.py script.
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


class DartParser(BaseParser):
    def __init__(self):
        self._parser = get_ts_parser("dart")

    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        source_bytes = source_text.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        units: list[CodeUnit] = []
        top_level_children: list[str] = []

        import_unit, import_references = self._extract_imports(root, source_bytes, file_path)
        if import_unit:
            units.append(import_unit)

        for child in root.children:
            if child.type == "class_definition":
                class_unit, member_units = self._extract_class(child, source_bytes, file_path)
                units.append(class_unit)
                units.extend(member_units)
                top_level_children.append(class_unit.name)

        module_name = file_path.rsplit("/", 1)[-1].removesuffix(".dart")

        units.insert(0, CodeUnit(
            type=UnitType.Module,
            name=module_name,
            qualifiedName=module_name,
            language=CodeLanguage.Dart,
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
            language=CodeLanguage.Dart,
        )

    # ── Import extraction ──────────────────────────────────────────────────

    def _extract_imports(
        self, root_node: Node, source_bytes: bytes, file_path: str
    ) -> tuple[CodeUnit | None, list[CodeReference]]:
        import_nodes = []
        references: list[CodeReference] = []

        for child in root_node.children:
            if child.type != "import_or_export":
                continue

            import_nodes.append(child)

            library_import = _find_child_by_type(child, "library_import")
            if not library_import:
                continue

            import_spec = _find_child_by_type(library_import, "import_specification")
            if not import_spec:
                continue

            config_uri = _find_child_by_type(import_spec, "configurable_uri")
            if not config_uri:
                continue

            uri_text = _node_text(config_uri, source_bytes).strip("'\"")
            short_name = uri_text.rsplit("/", 1)[-1].removesuffix(".dart")

            references.append(CodeReference(
                type=ReferenceType.Imports,
                target=short_name,
                qualifiedTarget=uri_text,
            ))

        if not import_nodes:
            return None, []

        import_text = "\n".join(_node_text(n, source_bytes) for n in import_nodes)

        import_unit = CodeUnit(
            type=UnitType.ImportBlock,
            name="imports",
            language=CodeLanguage.Dart,
            sourceText=import_text,
            references=references,
            filePath=file_path,
            startLine=_node_start_line(import_nodes[0]),
            endLine=_node_end_line(import_nodes[-1]),
        )

        return import_unit, references

    # ── Class body member grouping ─────────────────────────────────────────

    def _group_class_members(self, class_body_node: Node) -> list["_GroupedMember"]:
        members = []
        pending_annotations: list[Node] = []

        for child in class_body_node.children:
            if child.type in ("{", "}"):
                continue

            if child.type == "annotation":
                pending_annotations.append(child)

            elif child.type == "method_signature":
                member = _GroupedMember(
                    annotations=pending_annotations.copy(),
                    signature_node=child,
                )
                members.append(member)
                pending_annotations = []

            elif child.type == "function_body":
                if (
                    members
                    and members[-1].body_node is None
                    and members[-1].signature_node is not None
                ):
                    members[-1].body_node = child

            elif child.type == "declaration":
                member = _GroupedMember(
                    annotations=pending_annotations.copy(),
                    declaration_node=child,
                )
                members.append(member)
                pending_annotations = []

            elif child.type == ";":
                continue

            else:
                member = _GroupedMember(
                    annotations=pending_annotations.copy(),
                    declaration_node=child,
                )
                members.append(member)
                pending_annotations = []

        return members

    # ── Method extraction ──────────────────────────────────────────────────

    def _extract_method(
        self,
        member: "_GroupedMember",
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        if member.signature_node is None:
            return None

        references: list[CodeReference] = []

        has_override = False
        for ann in member.annotations:
            ann_id = _find_child_by_type(ann, "identifier")
            if ann_id:
                ann_name = _node_text(ann_id, source_bytes)
                references.append(
                    CodeReference(type=ReferenceType.Annotations, target=ann_name)
                )
                if ann_name == "override":
                    has_override = True

        sig_node = member.signature_node
        func_name = "<anonymous>"

        func_sig = _find_child_by_type(sig_node, "function_signature")
        getter_sig = _find_child_by_type(sig_node, "getter_signature")

        if func_sig:
            name_node = _find_child_by_type(func_sig, "identifier")
            if name_node:
                func_name = _node_text(name_node, source_bytes)

            type_node = _find_child_by_type(func_sig, "type_identifier")
            if type_node:
                references.append(
                    CodeReference(
                        type=ReferenceType.UsesTypes,
                        target=_node_text(type_node, source_bytes),
                    )
                )

            params = _find_child_by_type(func_sig, "formal_parameter_list")
            if params:
                for type_id in _collect_descendants_by_type(params, "type_identifier"):
                    references.append(
                        CodeReference(
                            type=ReferenceType.UsesTypes,
                            target=_node_text(type_id, source_bytes),
                        )
                    )

        elif getter_sig:
            name_node = _find_child_by_type(getter_sig, "identifier")
            if name_node:
                func_name = _node_text(name_node, source_bytes)

            type_node = _find_child_by_type(getter_sig, "type_identifier")
            if type_node:
                references.append(
                    CodeReference(
                        type=ReferenceType.UsesTypes,
                        target=_node_text(type_node, source_bytes),
                    )
                )

        if has_override and parent_name:
            references.append(CodeReference(
                type=ReferenceType.Overrides,
                target=func_name,
                qualifiedTarget=parent_name,
            ))

        if member.body_node:
            calls: set[str] = set()
            for sel_node in _collect_descendants_by_type(member.body_node, "selector"):
                sel_text = _node_text(sel_node, source_bytes).lstrip(".")
                call_name = sel_text.split("(")[0].strip()
                if call_name and not call_name.startswith("."):
                    calls.add(call_name)
            for call in calls:
                references.append(CodeReference(type=ReferenceType.Calls, target=call))

        start_node = member.annotations[0] if member.annotations else sig_node
        end_node = member.body_node if member.body_node else sig_node

        source_text = source_bytes[start_node.start_byte : end_node.end_byte].decode(
            "utf-8"
        )
        sig_text = _node_text(sig_node, source_bytes).strip()
        qualified_name = f"{parent_name}.{func_name}" if parent_name else func_name

        return CodeUnit(
            type=UnitType.Function,
            name=func_name,
            qualifiedName=qualified_name,
            language=CodeLanguage.Dart,
            sourceText=source_text,
            signature=sig_text,
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(start_node),
            endLine=_node_end_line(end_node),
        )

    # ── Declaration extraction ─────────────────────────────────────────────

    def _extract_declaration(
        self,
        member: "_GroupedMember",
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        if member.declaration_node is None:
            return None

        decl = member.declaration_node
        references: list[CodeReference] = []

        for ann in member.annotations:
            ann_id = _find_child_by_type(ann, "identifier")
            if ann_id:
                references.append(CodeReference(
                    type=ReferenceType.Annotations,
                    target=_node_text(ann_id, source_bytes),
                ))

        constructor_sig = _find_child_by_type(decl, "constant_constructor_signature")
        if constructor_sig:
            return self._extract_constructor(
                constructor_sig, member.annotations, source_bytes, file_path, parent_name
            )

        init_list = _find_child_by_type(decl, "initialized_identifier_list")
        if not init_list:
            return None

        id_node = _find_child_by_type(init_list, "initialized_identifier")
        if id_node:
            name_node = _find_child_by_type(id_node, "identifier")
            name = _node_text(name_node, source_bytes) if name_node else None
        else:
            name_node = _find_child_by_type(init_list, "identifier")
            name = _node_text(name_node, source_bytes) if name_node else None

        if not name:
            return None

        type_node = _find_child_by_type(decl, "type_identifier")
        if type_node:
            references.append(
                CodeReference(
                    type=ReferenceType.UsesTypes,
                    target=_node_text(type_node, source_bytes),
                )
            )

        source = _node_text(decl, source_bytes)

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=f"{parent_name}.{name}" if parent_name else name,
            language=CodeLanguage.Dart,
            sourceText=source,
            signature=source.split("\n")[0].strip().rstrip(";"),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(decl),
            endLine=_node_end_line(decl),
        )

    def _extract_constructor(
        self,
        constructor_node: Node,
        annotations: list[Node],
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> CodeUnit:
        references: list[CodeReference] = []

        for ann in annotations:
            ann_id = _find_child_by_type(ann, "identifier")
            if ann_id:
                references.append(CodeReference(
                    type=ReferenceType.Annotations,
                    target=_node_text(ann_id, source_bytes),
                ))

        name_node = _find_child_by_type(constructor_node, "identifier")
        name = (
            _node_text(name_node, source_bytes)
            if name_node
            else parent_name or "<constructor>"
        )

        params = _find_child_by_type(constructor_node, "formal_parameter_list")
        if params:
            for type_id in _collect_descendants_by_type(params, "type_identifier"):
                references.append(
                    CodeReference(
                        type=ReferenceType.UsesTypes,
                        target=_node_text(type_id, source_bytes),
                    )
                )

        source = _node_text(constructor_node, source_bytes)
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        return CodeUnit(
            type=UnitType.Function,
            name=name,
            qualifiedName=qualified_name,
            language=CodeLanguage.Dart,
            sourceText=source,
            signature=source.split("{")[0].split("=>")[0].strip().rstrip(";"),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(constructor_node),
            endLine=_node_end_line(constructor_node),
        )

    # ── Class extraction ───────────────────────────────────────────────────

    def _extract_class(
        self,
        node: Node,
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        references: list[CodeReference] = []
        children: list[str] = []
        child_units: list[CodeUnit] = []

        name_node = _find_child_by_type(node, "identifier")
        class_name = _node_text(name_node, source_bytes) if name_node else "<anonymous>"
        qualified_name = f"{parent_name}.{class_name}" if parent_name else class_name

        # Superclass
        superclass = _find_child_by_type(node, "superclass")
        type_args = None
        if superclass:
            type_node = _find_child_by_type(superclass, "type_identifier")
            if type_node:
                references.append(
                    CodeReference(
                        type=ReferenceType.Extends,
                        target=_node_text(type_node, source_bytes),
                    )
                )

            type_args = _find_child_by_type(superclass, "type_arguments")
            if type_args:
                for type_id in _find_children_by_type(type_args, "type_identifier"):
                    references.append(
                        CodeReference(
                            type=ReferenceType.UsesTypes,
                            target=_node_text(type_id, source_bytes),
                        )
                    )

        # Interfaces
        interfaces = _find_child_by_type(node, "interfaces")
        if interfaces:
            for type_id in _collect_descendants_by_type(interfaces, "type_identifier"):
                references.append(
                    CodeReference(
                        type=ReferenceType.Implements,
                        target=_node_text(type_id, source_bytes),
                    )
                )

        # Mixins
        mixins = _find_child_by_type(node, "mixins")
        if mixins:
            for type_id in _collect_descendants_by_type(mixins, "type_identifier"):
                references.append(
                    CodeReference(
                        type=ReferenceType.Extends,
                        target=_node_text(type_id, source_bytes),
                    )
                )

        # Signature
        keyword = "class"
        supertype_text = ""
        if superclass:
            super_type = _find_child_by_type(superclass, "type_identifier")
            if super_type:
                supertype_text = f" extends {_node_text(super_type, source_bytes)}"
                if type_args:
                    supertype_text = (
                        f" extends {_node_text(super_type, source_bytes)}"
                        f"{_node_text(type_args, source_bytes)}"
                    )
        signature = f"{keyword} {class_name}{supertype_text}"

        # Class body
        class_body = _find_child_by_type(node, "class_body")
        if class_body:
            grouped_members = self._group_class_members(class_body)

            for member in grouped_members:
                if member.signature_node is not None:
                    method_unit = self._extract_method(
                        member, source_bytes, file_path, parent_name=qualified_name
                    )
                    if method_unit:
                        child_units.append(method_unit)
                        children.append(method_unit.name)

                elif member.declaration_node is not None:
                    constructor_sig = _find_child_by_type(
                        member.declaration_node, "constant_constructor_signature"
                    )
                    if constructor_sig:
                        ctor_unit = self._extract_constructor(
                            constructor_sig,
                            member.annotations,
                            source_bytes,
                            file_path,
                            parent_name=qualified_name,
                        )
                        child_units.append(ctor_unit)
                        children.append(ctor_unit.name)

        class_unit = CodeUnit(
            type=UnitType.Class,
            name=class_name,
            qualifiedName=qualified_name,
            language=CodeLanguage.Dart,
            sourceText=_node_text(node, source_bytes),
            signature=signature,
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
            children=children,
        )

        return class_unit, child_units


# ── Helper dataclass for member grouping ───────────────────────────────────


class _GroupedMember:
    __slots__ = ("annotations", "signature_node", "body_node", "declaration_node")

    def __init__(
        self,
        annotations: list[Node] | None = None,
        signature_node: Node | None = None,
        body_node: Node | None = None,
        declaration_node: Node | None = None,
    ):
        self.annotations = annotations or []
        self.signature_node = signature_node
        self.body_node = body_node
        self.declaration_node = declaration_node


# ── Tree-sitter node helpers (module-level, stateless) ─────────────────────


def _node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8")


def _node_start_line(node: Node) -> int:
    return node.start_point[0] + 1


def _node_end_line(node: Node) -> int:
    return node.end_point[0] + 1


def _find_children_by_type(node: Node, type_name: str) -> list[Node]:
    return [child for child in node.children if child.type == type_name]


def _find_child_by_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
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