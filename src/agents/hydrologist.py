from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.analyzers.dag_config_parser import DAGConfigAnalyzer
from src.analyzers.sql_lineage import SQLLineageAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph
from src.models.graphs import EdgeType
from src.utils import iter_files, relpath_posix


@dataclass
class HydrologistResult:
    lineage_graph: KnowledgeGraph
    warnings: list[str]


class Hydrologist:
    """
    Interim Hydrologist:
    - parses .sql files with sqlglot
    - extracts source/target table dependencies
    - builds a lineage graph with Dataset + Transformation nodes
    """

    def __init__(self, dialect: str | None = None) -> None:
        self.sql = SQLLineageAnalyzer(dialect=dialect)
        self.config = DAGConfigAnalyzer()

    def run(self, repo_root: Path) -> HydrologistResult:
        g = KnowledgeGraph.empty()
        warnings: list[str] = []

        for p in iter_files(repo_root):
            suffix = p.suffix.lower()
            rel = relpath_posix(p, repo_root)

            # SQL lineage
            if suffix == ".sql":
                try:
                    statements = self.sql.analyze_file(p)
                except Exception as e:
                    warnings.append(f"sql_parse_failed:{rel}:{e!r}")
                    continue

                for stmt in statements:
                    t_id = f"transformation:{self.sql.transformation_id(rel, stmt)}"
                    g.add_node(
                        t_id,
                        node_type="TransformationNode",
                        transformation_type="sql",
                        source_file=rel,
                        statement_index=stmt.statement_index,
                        line_range=stmt.line_range,
                    )

                    sources = sorted(stmt.sources)
                    targets = sorted(stmt.targets)

                    # dbt model convention: models/*.sql produces a dataset named after the file stem
                    if not targets and ("/models/" in f"/{rel}" or rel.startswith("models/")):
                        model_name = Path(rel).stem
                        targets = [model_name]

                    # If no explicit target is known, keep a synthetic output per statement
                    if not targets:
                        targets = [f"query::{rel}#{stmt.statement_index}"]

                    for ds in sources:
                        d_id = f"dataset:{ds}"
                        if d_id not in g.graph:
                            g.add_node(
                                d_id,
                                node_type="DatasetNode",
                                name=ds,
                                storage_type="table",
                            )
                        g.add_edge(t_id, d_id, edge_type=EdgeType.CONSUMES)

                    for ds in targets:
                        d_id = f"dataset:{ds}"
                        if d_id not in g.graph:
                            g.add_node(
                                d_id,
                                node_type="DatasetNode",
                                name=ds,
                                storage_type="table" if not ds.startswith("query::") else "file",
                            )
                        g.add_edge(t_id, d_id, edge_type=EdgeType.PRODUCES)

            # YAML / config lineage (CONFIGURES edges)
            if suffix in {".yml", ".yaml"}:
                parsed = self.config.analyze_yaml(p)
                if not parsed:
                    continue
                cfg_id = f"config:{rel}"
                g.add_node(cfg_id, node_type="ConfigNode", path=rel, kind=parsed.kind)

                data = parsed.data
                if parsed.kind == "dbt_schema":
                    # Link config file to models/sources it describes
                    for model in data.get("models", []) or []:
                        name = model.get("name")
                        if not isinstance(name, str):
                            continue
                        target = f"dataset:{name}"
                        if target not in g.graph:
                            g.add_node(
                                target,
                                node_type="DatasetNode",
                                name=name,
                                storage_type="table",
                            )
                        g.add_edge(cfg_id, target, edge_type=EdgeType.CONFIGURES)

        return HydrologistResult(lineage_graph=g, warnings=warnings)

    def blast_radius(self, lineage_graph: KnowledgeGraph, dataset_name: str) -> list[str]:
        """
        Return downstream datasets impacted by a change in `dataset_name`.
        """
        start = f"dataset:{dataset_name}"
        if start not in lineage_graph.graph:
            return []

        # Traverse: dataset <-CONSUMES- transformation -PRODUCES-> dataset
        impacted: set[str] = set()
        queue: list[str] = [start]
        seen: set[str] = set(queue)
        g = lineage_graph.graph

        while queue:
            cur = queue.pop(0)
            for t in g.predecessors(cur):
                if g.edges[t, cur].get("edge_type") != "CONSUMES":
                    continue
                for ds in g.successors(t):
                    if g.edges[t, ds].get("edge_type") != "PRODUCES":
                        continue
                    if ds.startswith("dataset:") and ds not in seen:
                        seen.add(ds)
                        impacted.add(ds)
                        queue.append(ds)

        return sorted(n.split("dataset:", 1)[1] for n in impacted)

    def find_sources(self, lineage_graph: KnowledgeGraph) -> list[str]:
        """
        Entry-point datasets: in-degree == 0 (no producers), out-degree > 0.
        """
        g = lineage_graph.graph
        sources: list[str] = []
        for node, attrs in g.nodes(data=True):
            if not node.startswith("dataset:"):
                continue
            indeg = sum(1 for _ in g.predecessors(node))
            outdeg = sum(1 for _ in g.successors(node))
            if indeg == 0 and outdeg > 0:
                sources.append(node.split("dataset:", 1)[1])
        return sorted(sources)

    def find_sinks(self, lineage_graph: KnowledgeGraph) -> list[str]:
        """
        Exit-point datasets: out-degree == 0 (no consumers), in-degree > 0.
        """
        g = lineage_graph.graph
        sinks: list[str] = []
        for node, attrs in g.nodes(data=True):
            if not node.startswith("dataset:"):
                continue
            indeg = sum(1 for _ in g.predecessors(node))
            outdeg = sum(1 for _ in g.successors(node))
            if outdeg == 0 and indeg > 0:
                sinks.append(node.split("dataset:", 1)[1])
        return sorted(sinks)

