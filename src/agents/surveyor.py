from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console

from src.analyzers.tree_sitter_analyzer import ParsedSymbol, TreeSitterAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph
from src.models.graphs import EdgeType
from src.utils import guess_language, iter_files, relpath_posix


console = Console()


@dataclass
class SurveyorResult:
    module_graph: KnowledgeGraph
    warnings: list[str]


class Surveyor:
    def __init__(self) -> None:
        self.ts = TreeSitterAnalyzer()

    def run(self, repo_root: Path) -> SurveyorResult:
        g = KnowledgeGraph.empty()
        warnings: list[str] = []

        files = list(iter_files(repo_root))
        rel_by_path = {p: relpath_posix(p, repo_root) for p in files}

        # index python module candidates for import resolution
        py_files = [p for p in files if p.suffix.lower() == ".py"]
        module_index = self._build_python_module_index(repo_root, py_files)
        public_symbols_by_module: dict[str, list[ParsedSymbol]] = {}

        for p in files:
            rel = rel_by_path[p]
            lang = guess_language(p)
            node_id = f"module:{rel}"
            g.add_node(
                node_id,
                node_type="ModuleNode",
                path=rel,
                language=lang,
                last_modified=datetime.utcfromtimestamp(p.stat().st_mtime).isoformat(),
            )

            if lang == "python":
                try:
                    tree = self.ts.parse_file(p, "python")
                    imports = self.ts.extract_python_imports(tree)
                    symbols = self.ts.extract_python_public_symbols(tree)
                    public_symbols_by_module[rel] = symbols
                    for imp in imports:
                        target_rel = self._resolve_python_import(imp, p, repo_root, module_index)
                        if target_rel:
                            g.add_edge(
                                node_id,
                                f"module:{target_rel}",
                                edge_type=EdgeType.IMPORTS,
                                import_module=imp,
                            )
                except Exception as e:
                    warnings.append(f"python_parse_failed:{rel}:{e!r}")

        # add git velocity if possible (best effort)
        velocity = self._git_velocity_30d(repo_root)
        for rel, v in velocity.items():
            node_id = f"module:{rel}"
            if node_id in g.graph:
                g.graph.nodes[node_id]["change_velocity_30d"] = v

        # pagerank (hub detection)
        pr = g.pagerank()
        for node_id, score in pr.items():
            g.graph.nodes[node_id]["pagerank"] = score

        # SCCs (circular deps)
        sccs = [c for c in g.strongly_connected_components() if len(c) > 1]
        if sccs:
            g.graph.graph["strongly_connected_components"] = sccs

        # dead code candidates: modules with public symbols that no other module imports
        import_targets: set[str] = set()
        for u, v, data in g.edges():
            if data.get("edge_type") == EdgeType.IMPORTS.value:
                import_targets.add(v)

        dead_modules: list[str] = []
        for module_rel, symbols in public_symbols_by_module.items():
            node_id = f"module:{module_rel}"
            if node_id not in import_targets and symbols:
                dead_modules.append(node_id)
                g.graph.nodes[node_id]["is_dead_code_candidate"] = True

        # rank high-velocity, high-pagerank modules for downstream agents
        ranked = []
        for node_id, data in g.nodes():
            if not node_id.startswith("module:"):
                continue
            pr_score = data.get("pagerank", 0.0) or 0.0
            vel = data.get("change_velocity_30d", 0.0) or 0.0
            score = 0.6 * pr_score + 0.4 * vel
            ranked.append((score, node_id))
        ranked.sort(reverse=True)
        g.graph.graph["ranked_critical_modules"] = [
            {"module": nid, "score": score} for score, nid in ranked[:20]
        ]
        g.graph.graph["dead_code_candidates"] = dead_modules

        return SurveyorResult(module_graph=g, warnings=warnings)

    def _build_python_module_index(self, repo_root: Path, py_files: list[Path]) -> dict[str, str]:
        """
        Map import-ish keys to relative file paths.
        Keys include:
          - a.b.c -> a/b/c.py
          - a.b -> a/b/__init__.py (if present)
        """
        out: dict[str, str] = {}
        for p in py_files:
            rel = relpath_posix(p, repo_root)
            parts = p.relative_to(repo_root).with_suffix("").parts
            if parts:
                key = ".".join(parts)
                out[key] = rel
            if p.name == "__init__.py":
                pkg_parts = p.relative_to(repo_root).parent.parts
                if pkg_parts:
                    out[".".join(pkg_parts)] = rel
        return out

    def _resolve_python_import(
        self,
        imp: str,
        from_file: Path,
        repo_root: Path,
        module_index: dict[str, str],
    ) -> Optional[str]:
        imp = imp.strip()
        if not imp:
            return None

        # relative import: "..x.y"
        if imp.startswith("."):
            dots = 0
            for ch in imp:
                if ch == ".":
                    dots += 1
                else:
                    break
            remainder = imp[dots:]
            base = from_file.parent
            for _ in range(max(dots - 1, 0)):
                base = base.parent
            if remainder:
                candidate = base.joinpath(*remainder.split(".")).with_suffix(".py")
            else:
                candidate = base / "__init__.py"
            try:
                rel = relpath_posix(candidate.resolve(), repo_root)
                return rel if candidate.exists() else None
            except Exception:
                return None

        # absolute import
        if imp in module_index:
            return module_index[imp]
        # try progressively shorter (import pkg.sub as x often used)
        parts = imp.split(".")
        for k in range(len(parts), 0, -1):
            key = ".".join(parts[:k])
            if key in module_index:
                return module_index[key]
        return None

    def _git_velocity_30d(self, repo_root: Path) -> dict[str, float]:
        git_dir = repo_root / ".git"
        if not git_dir.exists():
            return {}

        since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        try:
            out = subprocess.check_output(
                ["git", "-C", str(repo_root), "log", f"--since={since}", "--name-only", "--pretty=format:"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return {}

        counts: dict[str, int] = {}
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            counts[line] = counts.get(line, 0) + 1

        if not counts:
            return {}

        max_c = max(counts.values())
        return {k: v / max_c for k, v in counts.items()}

