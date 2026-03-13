from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass
class PythonIOEvent:
    transformation_type: str  # "python"
    source_file: str
    line_range: Tuple[int, int]
    sources: List[str]
    targets: List[str]


class PythonDataFlowAnalyzer:
    """
    Very lightweight static dataflow analyzer for Python.

    Detects best-effort:
    - pandas.read_* and DataFrame.to_* calls
    - spark.read.* and DataFrame.write.* calls
    - SQLAlchemy session.execute/engine.execute with literal SQL (table names left in SQL)
    """

    def analyze_file(self, path: Path) -> list[PythonIOEvent]:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return []

        events: list[PythonIOEvent] = []
        rel = path.as_posix()

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                func = node.func
                name = ""
                if isinstance(func, ast.Attribute):
                    # obj.method()
                    if isinstance(func.value, ast.Name):
                        obj = func.value.id
                        name = f"{obj}.{func.attr}"
                    else:
                        name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id

                lname = name.lower()
                sources: list[str] = []
                targets: list[str] = []

                # pandas read_*
                if lname.startswith("pd.read_") or lname.startswith("pandas.read_"):
                    for arg in node.args[:1]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            sources.append(arg.value)

                # DataFrame.to_*
                if ".to_" in lname:
                    for arg in node.args[:1]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            targets.append(arg.value)

                # spark.read.*
                if lname.startswith("spark.read"):
                    for arg in node.args[:1]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            sources.append(arg.value)

                # df.write.*
                if lname.endswith(".write") or ".write." in lname:
                    for arg in node.args[:1]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            targets.append(arg.value)

                # SQLAlchemy execute with literal SQL
                if lname.endswith(".execute"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                        node.args[0].value, str
                    ):
                        sql = node.args[0].value.lower()
                        # very rough table extraction: look for "from <name>"
                        tokens = sql.replace("\n", " ").split()
                        for i, tok in enumerate(tokens):
                            if tok == "from" and i + 1 < len(tokens):
                                sources.append(tokens[i + 1])

                if sources or targets:
                    start = node.lineno
                    end = getattr(node, "end_lineno", node.lineno)
                    events.append(
                        PythonIOEvent(
                            transformation_type="python",
                            source_file=rel,
                            line_range=(start, end),
                            sources=sources,
                            targets=targets,
                        )
                    )

                self.generic_visit(node)

        Visitor().visit(tree)
        return events

