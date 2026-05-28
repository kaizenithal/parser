"""
Python AST parser using the built-in ast module.

Refactored from the standalone python_ast_parser.py script.
All filesystem access removed — operates entirely on in-memory source text.
"""

import ast

from ..models import (
    CodeParsingResult,
    CodeReference,
    CodeUnit,
    Language,
    ReferenceType,
    UnitType,
)
from .base import BaseParser


class PythonParser(BaseParser):
    def parse(self, source_text: str, file_path: str) -> CodeParsingResult:
        try:
            tree = ast.parse(source_text)
        except SyntaxError as e:
            return CodeParsingResult(
                units=[],
                filePath=file_path,
                language=Language.Python,
                warnings=[f"SyntaxError at line {e.lineno}: {e.msg}"],
            )

        source_lines = source_text.splitlines()
        units: list[CodeUnit] = []
        import_nodes = []
        top_level_children = []

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_nodes.append(node)

            elif isinstance(node, ast.ClassDef):
                class_unit, method_units = self._extract_class(node, source_lines, file_path)
                units.append(class_unit)
                units.extend(method_units)
                top_level_children.append(node.name)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_unit = self._extract_function(node, source_lines, file_path)
                units.append(func_unit)
                top_level_children.append(node.name)

            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                decl = self._extract_declaration(node, source_lines, file_path)
                if decl:
                    units.append(decl)
                    top_level_children.append(decl.name)

        # Import block
        import_block = self._extract_imports(import_nodes, source_lines, file_path)
        if import_block:
            units.insert(0, import_block)

        # Module unit
        module_references = import_block.references if import_block else []
        module_name = file_path.rsplit("/", 1)[-1].removesuffix(".py").removesuffix(".pyi")
        qualified_module = (
            file_path.removesuffix(".py")
            .removesuffix(".pyi")
            .replace("/", ".")
            .replace("\\", ".")
        )

        module_unit = CodeUnit(
            type=UnitType.Module,
            name=module_name,
            qualifiedName=qualified_module,
            language=Language.Python,
            sourceText=source_text,
            references=module_references,
            filePath=file_path,
            startLine=1,
            endLine=len(source_lines),
            children=top_level_children,
        )
        units.insert(0, module_unit)

        return CodeParsingResult(
            units=units,
            filePath=file_path,
            language=Language.Python,
        )

    # ── Extraction helpers ─────────────────────────────────────────────────

    def _extract_signature(self, node: ast.stmt, source_lines: list[str]) -> str | None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = ast.get_source_segment("\n".join(source_lines), node.args)
            returns = ""
            if node.returns:
                return_annotation = ast.get_source_segment(
                    "\n".join(source_lines), node.returns
                )
                if return_annotation:
                    returns = f" -> {return_annotation}"

            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            return f"{prefix} {node.name}({params or ''}){returns}:"

        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(
                ast.get_source_segment("\n".join(source_lines), base) or ""
                for base in node.bases
            )
            if bases:
                return f"class {node.name}({bases}):"
            return f"class {node.name}:"

        return None

    def _extract_source_text(self, node: ast.stmt, source_lines: list[str]) -> str:
        if node.lineno is None or node.end_lineno is None:
            return ""

        start_line = node.lineno - 1

        if hasattr(node, "decorator_list") and node.decorator_list:
            dec_line = node.decorator_list[0].lineno
            if dec_line is not None:
                start_line = dec_line - 1

        return "\n".join(source_lines[start_line : node.end_lineno])

    def _extract_decorator_references(
        self, node: ast.AST, source_lines: list[str]
    ) -> list[CodeReference]:
        references = []
        for decorator in getattr(node, "decorator_list", []):
            if isinstance(decorator, ast.Name):
                target = decorator.id
            elif isinstance(decorator, ast.Attribute):
                target = ast.get_source_segment("\n".join(source_lines), decorator) or ""
            elif isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Name):
                    target = func.id
                elif isinstance(func, ast.Attribute):
                    target = ast.get_source_segment("\n".join(source_lines), func) or ""
                else:
                    continue
            else:
                continue

            references.append(CodeReference(type=ReferenceType.Annotations, target=target))
        return references

    def _extract_call_references(
        self, node: ast.AST, source_lines: list[str]
    ) -> list[CodeReference]:
        references = []
        seen: set[str] = set()

        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            func = child.func
            if isinstance(func, ast.Name):
                target = func.id
            elif isinstance(func, ast.Attribute):
                target = ast.get_source_segment("\n".join(source_lines), func) or ""
            else:
                continue

            if target and target not in seen:
                seen.add(target)
                references.append(CodeReference(type=ReferenceType.Calls, target=target))

        return references

    def _extract_type_references(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]
    ) -> list[CodeReference]:
        references = []

        if node.returns:
            type_str = ast.get_source_segment("\n".join(source_lines), node.returns)
            if type_str:
                references.append(CodeReference(type=ReferenceType.UsesTypes, target=type_str))

        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if arg.arg in ("self", "cls"):
                continue
            if arg.annotation:
                type_str = ast.get_source_segment("\n".join(source_lines), arg.annotation)
                if type_str:
                    references.append(
                        CodeReference(type=ReferenceType.UsesTypes, target=type_str)
                    )

        return references

    def _is_override_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "override":
                return True
            if isinstance(decorator, ast.Attribute) and decorator.attr == "override":
                return True

        if node.name.startswith("__") and node.name.endswith("__") and node.name != "__init__":
            return True

        return False

    # ── Unit extraction ────────────────────────────────────────────────────

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_lines: list[str],
        file_path: str,
        parent_name: str | None = None,
    ) -> CodeUnit:
        references: list[CodeReference] = []
        references.extend(self._extract_decorator_references(node, source_lines))
        references.extend(self._extract_type_references(node, source_lines))
        references.extend(self._extract_call_references(node, source_lines))

        if parent_name and self._is_override_method(node):
            references.append(
                CodeReference(
                    type=ReferenceType.Overrides,
                    target=node.name,
                    qualifiedTarget=parent_name,
                )
            )

        qualified_name = f"{parent_name}.{node.name}" if parent_name else node.name

        start_line = node.lineno
        if node.decorator_list:
            start_line = node.decorator_list[0].lineno

        return CodeUnit(
            type=UnitType.Function,
            name=node.name,
            qualifiedName=qualified_name,
            language=Language.Python,
            sourceText=self._extract_source_text(node, source_lines),
            signature=self._extract_signature(node, source_lines),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=start_line,
            endLine=node.end_lineno,
        )

    def _extract_class(
        self,
        node: ast.ClassDef,
        source_lines: list[str],
        file_path: str,
        parent_name: str | None = None,
    ) -> tuple[CodeUnit, list[CodeUnit]]:
        references: list[CodeReference] = []
        references.extend(self._extract_decorator_references(node, source_lines))

        for base in node.bases:
            base_name = ast.get_source_segment("\n".join(source_lines), base)
            if base_name:
                references.append(CodeReference(type=ReferenceType.Extends, target=base_name))

        class_name = node.name
        qualified_name = f"{parent_name}.{class_name}" if parent_name else class_name
        children = []
        method_units = []

        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                children.append(child.name)
                method_unit = self._extract_function(
                    child, source_lines, file_path, parent_name=qualified_name
                )
                method_units.append(method_unit)

        start_line = node.lineno
        if node.decorator_list:
            start_line = node.decorator_list[0].lineno

        class_unit = CodeUnit(
            type=UnitType.Class,
            name=class_name,
            qualifiedName=qualified_name,
            language=Language.Python,
            sourceText=self._extract_source_text(node, source_lines),
            signature=self._extract_signature(node, source_lines),
            references=references,
            parentName=parent_name,
            filePath=file_path,
            startLine=start_line,
            endLine=node.end_lineno,
            children=children,
        )

        return class_unit, method_units

    def _extract_imports(
        self,
        nodes: list[ast.Import | ast.ImportFrom],
        source_lines: list[str],
        file_path: str,
    ) -> CodeUnit | None:
        if not nodes:
            return None

        references: list[CodeReference] = []

        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    references.append(
                        CodeReference(type=ReferenceType.Imports, target=alias.name)
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    qualified = f"{module}.{alias.name}" if module else alias.name
                    references.append(
                        CodeReference(
                            type=ReferenceType.Imports,
                            target=alias.name,
                            qualifiedTarget=qualified,
                        )
                    )

        block_text = "\n".join(self._extract_source_text(n, source_lines) for n in nodes)

        return CodeUnit(
            type=UnitType.ImportBlock,
            name="imports",
            language=Language.Python,
            sourceText=block_text,
            references=references,
            filePath=file_path,
            startLine=nodes[0].lineno,
            endLine=nodes[-1].end_lineno,
        )

    def _extract_declaration(
        self,
        node: ast.Assign | ast.AnnAssign,
        source_lines: list[str],
        file_path: str,
    ) -> CodeUnit | None:
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                return None
            name = node.target.id
            references: list[CodeReference] = []
            if node.annotation:
                type_str = ast.get_source_segment("\n".join(source_lines), node.annotation)
                if type_str:
                    references.append(
                        CodeReference(type=ReferenceType.UsesTypes, target=type_str)
                    )
        elif isinstance(node, ast.Assign):
            target = node.targets[0]
            if len(node.targets) != 1 or not isinstance(target, ast.Name):
                return None
            name = target.id
            references = []
        else:
            return None

        return CodeUnit(
            type=UnitType.Declaration,
            name=name,
            language=Language.Python,
            sourceText=self._extract_source_text(node, source_lines),
            signature=source_lines[node.lineno - 1].strip(),
            references=references,
            filePath=file_path,
            startLine=node.lineno,
            endLine=node.end_lineno,
        )