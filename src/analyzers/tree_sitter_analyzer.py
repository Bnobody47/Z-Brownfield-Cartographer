from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter import Node
from tree_sitter_languages import get_parser


@dataclass
class ParsedSymbol:
    name: str
    kind: str  # "function" | "class"
    signature: str | None
    start_line: int
    end_line: int


class TreeSitterAnalyzer:
    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}

    def parser_for_language(self, language: str):
        if language not in self._parsers:
            self._parsers[language] = get_parser(language)
        return self._parsers[language]

    def parse_file(self, path: Path, language: str):
        parser = self.parser_for_language(language)
        code = path.read_bytes()
        return parser.parse(code)

    def extract_python_imports(self, tree) -> list[str]:
        """
        Return raw import module strings like:
          - "os"
          - "pkg.subpkg"
          - ".local_module" (relative, unresolved)
        """
        imports: list[str] = []
        root = tree.root_node
        for node in root.children:
            if node.type == "import_statement":
                # import a, b.c
                # children include: 'import' + dotted_name / aliased_import
                imports.extend(self._extract_import_statement_modules(node))
            elif node.type == "import_from_statement":
                # from x.y import z
                mod = self._extract_from_module(node)
                if mod:
                    imports.append(mod)
        return imports

    def _node_text(self, node: Node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _extract_import_statement_modules(self, node: Node) -> list[str]:
        # best-effort traversal without queries (keeps dependencies light)
        out: list[str] = []
        for child in node.children:
            if child.type in ("dotted_name", "identifier"):
                out.append(child.text.decode("utf-8", errors="replace"))
            elif child.type == "aliased_import":
                # first child tends to be dotted_name
                for gc in child.children:
                    if gc.type in ("dotted_name", "identifier"):
                        out.append(gc.text.decode("utf-8", errors="replace"))
                        break
        return out

    def _extract_from_module(self, node: Node) -> str | None:
        # "from" (relative_import | dotted_name) "import" ...
        for child in node.children:
            if child.type in ("dotted_name", "relative_import"):
                return child.text.decode("utf-8", errors="replace")
        return None

    def extract_python_public_symbols(self, tree) -> list[ParsedSymbol]:
        root = tree.root_node
        out: list[ParsedSymbol] = []
        for node in root.children:
            if node.type == "function_definition":
                sym = self._parse_python_function(node)
                if sym and not sym.name.startswith("_"):
                    out.append(sym)
            elif node.type == "class_definition":
                sym = self._parse_python_class(node)
                if sym and not sym.name.startswith("_"):
                    out.append(sym)
        return out

    def _parse_python_function(self, node: Node) -> ParsedSymbol | None:
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        params_node = next((c for c in node.children if c.type == "parameters"), None)
        if not name_node:
            return None
        name = name_node.text.decode("utf-8", errors="replace")
        signature = None
        if params_node:
            signature = f"{name}{params_node.text.decode('utf-8', errors='replace')}"
        return ParsedSymbol(
            name=name,
            kind="function",
            signature=signature,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        )

    def _parse_python_class(self, node: Node) -> ParsedSymbol | None:
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        if not name_node:
            return None
        name = name_node.text.decode("utf-8", errors="replace")
        # base classes are in "argument_list" after identifier; keep simple
        return ParsedSymbol(
            name=name,
            kind="class",
            signature=f"class {name}",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        )

