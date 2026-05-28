"""
Kotlin parser using tree-sitter via tree-sitter-language-pack.

Ported from the standalone kotlin_ast_parser.py script.
All filesystem access removed — operates entirely on in-memory source text.

The language pack's Kotlin grammar uses `type_identifier` for class/object names
and `simple_identifier` for function/variable names, rather than exposing named
fields. This differs from the standalone tree-sitter-kotlin package.
"""

from tree_sitter_language_pack import get_language, get_parser as get_ts_parser

from ..models import (
    CodeParsingResult,
    CodeReference,
    CodeUnit,
    Language as CodeLanguage,
    ReferenceType,
    UnitType,
)
from .base import BaseParser

KT_LANGUAGE = get_language("kotlin")


def _get_name(node, source_bytes: bytes) -> str | None:
    """Extract the name from a node, trying type_identifier then simple_identifier."""
    name_node = _find_child_by_type(node, "type_identifier")
    if name_node:
        return _node_text(name_node, source_bytes)
    name_node = _find_child_by_type(node, "simple_identifier")
    if name_node:
        return _node_text(name_node, source_bytes)
    return None


class KotlinParser(BaseParser):
    def __init__(self):
        self._parser = get_ts_parser("kotlin")

    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        source_bytes = source_text.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        units: list[CodeUnit] = []
        top_level_children: list[str] = []

        # Package name
        package_node = _find_child_by_type(root, "package_header")
        package_name = None
        if package_node:
            identifier = _find_child_by_type(package_node, "identifier")
            if identifier:
                package_name = _node_text(identifier, source_bytes)

        # Imports
        import_unit, import_references = self._extract_imports(root, source_bytes, file_path)
        if import_unit:
            units.append(import_unit)

        # Walk top-level declarations
        for child in root.children:
            if child.type == "class_declaration":
                class_unit, member_units = self._extract_class(child, source_bytes, file_path)
                units.append(class_unit)
                units.extend(member_units)
                top_level_children.append(class_unit.name)

            elif child.type == "object_declaration":
                obj_unit, member_units = self._extract_object(child, source_bytes, file_path)
                units.append(obj_unit)
                units.extend(member_units)
                top_level_children.append(obj_unit.name)

            elif child.type == "function_declaration":
                func_unit = self._extract_function(child, source_bytes, file_path)
                units.append(func_unit)
                top_level_children.append(func_unit.name)

            elif child.type == "property_declaration":
                prop_unit = self._extract_property(child, source_bytes, file_path)
                if prop_unit:
                    units.append(prop_unit)
                    top_level_children.append(prop_unit.name)

        # Module unit
        module_name = file_path.rsplit("/", 1)[-1].removesuffix(".kt").removesuffix(".kts")
        qualified_module = f"{package_name}.{module_name}" if package_name else module_name

        units.insert(0, CodeUnit(
            type=UnitType.Module,
            name=module_name,
            qualifiedName=qualified_module,
            language=CodeLanguage.Kotlin,
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
            language=CodeLanguage.Kotlin,
        )

    # ── Annotation extraction ──────────────────────────────────────────────

    def _extract_annotations(self, node, source_bytes: bytes) -> list[CodeReference]:
        references = []
        modifiers = _find_child_by_type(node, "modifiers")
        if modifiers is None:
            return references

        for child in modifiers.children:
            if child.type == "annotation":
                # Try user_type first, then constructor_invocation, then raw text
                user_type = _find_child_by_type(child, "user_type")
                if user_type:
                    target = _node_text(user_type, source_bytes)
                else:
                    constructor_inv = _find_child_by_type(child, "constructor_invocation")
                    if constructor_inv:
                        ut = _find_child_by_type(constructor_inv, "user_type")
                        target = _node_text(ut, source_bytes) if ut else _node_text(constructor_inv, source_bytes)
                    else:
                        target = _node_text(child, source_bytes).lstrip("@")
                target = target.split("(")[0].strip()
                if target:
                    references.append(
                        CodeReference(type=ReferenceType.Annotations, target=target)
                    )

        return references

    # ── Import extraction ──────────────────────────────────────────────────

    def _extract_imports(
        self, root_node, source_bytes: bytes, file_path: str
    ) -> tuple[CodeUnit | None, list[CodeReference]]:
        import_list_node = _find_child_by_type(root_node, "import_list")
        if not import_list_node:
            return None, []

        references: list[CodeReference] = []
        all_import_headers = _find_children_by_type(import_list_node, "import_header")

        for import_header in all_import_headers:
            identifier = _find_child_by_type(import_header, "identifier")
            if identifier:
                full_path = _node_text(identifier, source_bytes)
                short_name = full_path.rsplit(".", 1)[-1]
                references.append(CodeReference(
                    type=ReferenceType.Imports,
                    target=short_name,
                    qualifiedTarget=full_path,
                ))

        if not all_import_headers:
            return None, []

        import_text = "\n".join(
            _node_text(h, source_bytes) for h in all_import_headers
        )

        import_unit = CodeUnit(
            type=UnitType.ImportBlock,
            name="imports",
            language=CodeLanguage.Kotlin,
            sourceText=import_text,
            references=references,
            filePath=file_path,
            startLine=_node_start_line(all_import_headers[0]),
            endLine=_node_end_line(all_import_headers[-1]),
        )

        return import_unit, references

    # ── Function extraction ────────────────────────────────────────────────

    def _extract_function(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> CodeUnit:
        references: list[CodeReference] = []
        references.extend(self._extract_annotations(node, source_bytes))

        # Function name — uses simple_identifier in language pack grammar
        func_name = _get_name(node, source_bytes) or "<anonymous>"

        # Return type — look for user_type that is a direct child (not inside params)
        return_type = None
        for child in node.children:
            if child.type == "user_type" and child != _find_child_by_type(node, "function_value_parameters"):
                return_type = child
                break

        if return_type:
            references.append(
                CodeReference(
                    type=ReferenceType.UsesTypes,
                    target=_node_text(return_type, source_bytes),
                )
            )

        # Parameter types
        params_node = _find_child_by_type(node, "function_value_parameters")
        if params_node:
            for param in _find_children_by_type(params_node, "parameter"):
                type_node = _find_child_by_type(param, "user_type")
                if type_node:
                    references.append(
                        CodeReference(
                            type=ReferenceType.UsesTypes,
                            target=_node_text(type_node, source_bytes),
                        )
                    )

        # Override detection
        modifiers = _find_child_by_type(node, "modifiers")
        has_override = False
        has_suspend = False
        if modifiers:
            mod_text = _node_text(modifiers, source_bytes)
            has_override = "override" in mod_text
            has_suspend = "suspend" in mod_text

        if has_override and parent_name:
            references.append(CodeReference(
                type=ReferenceType.Overrides,
                target=func_name,
                qualifiedTarget=parent_name,
            ))

        # Call references from body
        body = _find_child_by_type(node, "function_body")
        if body:
            calls: set[str] = set()
            for call_node in _collect_descendants_by_type(body, "call_expression"):
                call_text = _node_text(call_node, source_bytes).split("(")[0].strip()
                if call_text:
                    calls.add(call_text)
            for call in calls:
                references.append(CodeReference(type=ReferenceType.Calls, target=call))

        qualified_name = f"{parent_name}.{func_name}" if parent_name else func_name

        # Build signature
        suspend_prefix = "suspend " if has_suspend else ""
        param_text = _node_text(params_node, source_bytes) if params_node else "()"
        return_suffix = (
            f": {_node_text(return_type, source_bytes)}" if return_type else ""
        )
        signature = f"{suspend_prefix}fun {func_name}{param_text}{return_suffix}"

        return CodeUnit(
            type=UnitType.Function,
            name=func_name,
            qualifiedName=qualified_name,
            language=CodeLanguage.Kotlin,
            sourceText=_node_text(node, source_bytes),
            signature=signature,
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )

    # ── Class / Object extraction ──────────────────────────────────────────

    def _extract_class(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        references: list[CodeReference] = []
        children: list[str] = []
        child_units: list[CodeUnit] = []

        references.extend(self._extract_annotations(node, source_bytes))

        # Class name — uses type_identifier in language pack grammar
        class_name = _get_name(node, source_bytes) or "<anonymous>"
        qualified_name = f"{parent_name}.{class_name}" if parent_name else class_name

        # Superclasses / interfaces from delegation_specifier children
        for specifier in _find_children_by_type(node, "delegation_specifier"):
            # delegation_specifier may contain user_type or constructor_invocation
            user_type = _find_child_by_type(specifier, "user_type")
            if user_type:
                references.append(
                    CodeReference(type=ReferenceType.Extends, target=_node_text(user_type, source_bytes))
                )
            else:
                constructor_inv = _find_child_by_type(specifier, "constructor_invocation")
                if constructor_inv:
                    ut = _find_child_by_type(constructor_inv, "user_type")
                    if ut:
                        references.append(
                            CodeReference(type=ReferenceType.Extends, target=_node_text(ut, source_bytes))
                        )

        # Determine class keyword for signature
        modifiers = _find_child_by_type(node, "modifiers")
        mod_text = _node_text(modifiers, source_bytes) if modifiers else ""

        keyword = "class"
        if node.type == "object_declaration":
            keyword = "object"
        elif "data" in mod_text:
            keyword = "data class"
        elif "sealed" in mod_text:
            keyword = "sealed class"
        elif "enum" in mod_text:
            keyword = "enum class"
        # Check for interface keyword in children
        for child in node.children:
            if child.type == "interface":
                keyword = "interface"
                break

        # Walk class body
        class_body = _find_child_by_type(node, "class_body")
        if class_body:
            for member in class_body.children:
                if member.type == "function_declaration":
                    func_unit = self._extract_function(
                        member, source_bytes, file_path, parent_name=qualified_name
                    )
                    child_units.append(func_unit)
                    children.append(func_unit.name)

                elif member.type == "companion_object":
                    comp_unit, comp_children = self._extract_object(
                        member, source_bytes, file_path, parent_name=qualified_name
                    )
                    child_units.append(comp_unit)
                    child_units.extend(comp_children)
                    children.append(comp_unit.name)

                elif member.type in ("class_declaration", "object_declaration"):
                    nested_unit, nested_children = self._extract_class(
                        member, source_bytes, file_path, parent_name=qualified_name
                    )
                    child_units.append(nested_unit)
                    child_units.extend(nested_children)
                    children.append(nested_unit.name)

        # Build signature
        delegation_specifiers = _find_children_by_type(node, "delegation_specifier")
        supertypes = ""
        if delegation_specifiers:
            supertypes = " : " + ", ".join(
                _node_text(ds, source_bytes) for ds in delegation_specifiers
            )
        signature = f"{keyword} {class_name}{supertypes}"

        class_unit = CodeUnit(
            type=UnitType.Class,
            name=class_name,
            qualifiedName=qualified_name,
            language=CodeLanguage.Kotlin,
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

    def _extract_object(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        references: list[CodeReference] = []
        children: list[str] = []
        child_units: list[CodeUnit] = []

        references.extend(self._extract_annotations(node, source_bytes))

        # Object name — type_identifier; companion objects may not have one
        name = _get_name(node, source_bytes) or "Companion"
        qualified_name = f"{parent_name}.{name}" if parent_name else name

        class_body = _find_child_by_type(node, "class_body")
        if class_body:
            for member in class_body.children:
                if member.type == "function_declaration":
                    func_unit = self._extract_function(
                        member, source_bytes, file_path, parent_name=qualified_name
                    )
                    child_units.append(func_unit)
                    children.append(func_unit.name)

                elif member.type == "property_declaration":
                    prop_unit = self._extract_property(
                        member, source_bytes, file_path, parent_name=qualified_name
                    )
                    if prop_unit:
                        child_units.append(prop_unit)
                        children.append(prop_unit.name)

        keyword = "companion object" if node.type == "companion_object" else "object"
        signature = f"{keyword} {name}" if name != "Companion" else "companion object"

        obj_unit = CodeUnit(
            type=UnitType.Class,
            name=name,
            qualifiedName=qualified_name,
            language=CodeLanguage.Kotlin,
            sourceText=_node_text(node, source_bytes),
            signature=signature,
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
            children=children,
        )

        return obj_unit, child_units

    # ── Property extraction ────────────────────────────────────────────────

    def _extract_property(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        parent_name: str | None = None,
    ) -> CodeUnit | None:
        references: list[CodeReference] = []
        references.extend(self._extract_annotations(node, source_bytes))

        var_decl = _find_child_by_type(node, "variable_declaration")
        name = None
        if var_decl:
            # variable_declaration uses simple_identifier for the name
            name = _get_name(var_decl, source_bytes)

            type_node = _find_child_by_type(var_decl, "user_type")
            if type_node:
                references.append(
                    CodeReference(
                        type=ReferenceType.UsesTypes,
                        target=_node_text(type_node, source_bytes),
                    )
                )

        if not name:
            return None

        # Override detection
        modifiers = _find_child_by_type(node, "modifiers")
        if modifiers and "override" in _node_text(modifiers, source_bytes):
            if parent_name:
                references.append(CodeReference(
                    type=ReferenceType.Overrides,
                    target=name,
                    qualifiedTarget=parent_name,
                ))

        source = _node_text(node, source_bytes)
        signature = source.split("\n")[0].strip()

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            qualifiedName=f"{parent_name}.{name}" if parent_name else name,
            language=CodeLanguage.Kotlin,
            sourceText=source,
            signature=signature,
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=_node_start_line(node),
            endLine=_node_end_line(node),
        )


# ── Tree-sitter node helpers (module-level, stateless) ─────────────────────


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8")


def _node_start_line(node) -> int:
    return node.start_point[0] + 1


def _node_end_line(node) -> int:
    return node.end_point[0] + 1


def _find_children_by_type(node, type_name: str) -> list:
    return [child for child in node.children if child.type == type_name]


def _find_child_by_type(node, type_name: str):
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_child_by_field(node, field_name: str):
    return node.child_by_field_name(field_name)


def _collect_descendants_by_type(node, type_name: str) -> list:
    results = []

    def walk(n):
        if n.type == type_name:
            results.append(n)
        for child in n.children:
            walk(child)

    walk(node)
    return results