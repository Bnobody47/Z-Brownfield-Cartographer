from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from src.agents.hydrologist import Hydrologist
from src.graph.knowledge_graph import KnowledgeGraph


@dataclass
class QueryResult:
    answer: str
    evidence: list[dict[str, Any]]


class Navigator:
    """
    Query interface over the generated knowledge graphs.
    Minimal final implementation: structured queries + evidence objects.
    """

    def __init__(self) -> None:
        self.hydrologist = Hydrologist()

    def trace_lineage(
        self,
        lineage_graph: KnowledgeGraph,
        dataset: str,
        direction: Literal["upstream", "downstream"],
        limit: int = 50,
    ) -> QueryResult:
        start = f"dataset:{dataset}"
        if start not in lineage_graph.graph:
            return QueryResult(answer=f"Dataset not found: {dataset}", evidence=[])

        g = lineage_graph.graph
        out: list[str] = []
        evidence: list[dict[str, Any]] = []

        if direction == "downstream":
            # use blast_radius plus evidence
            impacted = self.hydrologist.blast_radius(lineage_graph, dataset)[:limit]
            for ds in impacted:
                out.append(ds)
            answer = f"Downstream of `{dataset}`: " + (", ".join(out) if out else "(none)")
            return QueryResult(answer=answer, evidence=[])

        # upstream: traverse dataset -> predecessor transformations via PRODUCES and then their CONSUMES inputs
        visited_ds = {start}
        queue = [start]
        while queue and len(evidence) < limit:
            cur = queue.pop(0)
            for t in g.predecessors(cur):
                if g.edges[t, cur].get("edge_type") != "PRODUCES":
                    continue
                t_attrs = g.nodes[t]
                src_file = t_attrs.get("source_file")
                line_range = t_attrs.get("line_range")
                # collect consumed datasets
                for ds in g.successors(t):
                    if g.edges[t, ds].get("edge_type") != "CONSUMES":
                        continue
                    if ds not in visited_ds:
                        visited_ds.add(ds)
                        queue.append(ds)
                    evidence.append(
                        {
                            "transformation": t,
                            "source_file": src_file,
                            "line_range": line_range,
                            "consumes": ds,
                            "produces": cur,
                        }
                    )
                    if len(evidence) >= limit:
                        break

        upstream = sorted({e["consumes"].split("dataset:", 1)[1] for e in evidence if str(e["consumes"]).startswith("dataset:")})
        answer = f"Upstream of `{dataset}` (best-effort): " + (", ".join(upstream) if upstream else "(none)")
        return QueryResult(answer=answer, evidence=evidence)

    def blast_radius_module(self, module_graph: KnowledgeGraph, module_path: str, limit: int = 100) -> QueryResult:
        start = f"module:{module_path}"
        g = module_graph.graph
        if start not in g:
            return QueryResult(answer=f"Module not found: {module_path}", evidence=[])

        # downstream importers: traverse reverse IMPORTS edges
        impacted: set[str] = set()
        queue = [start]
        seen = set(queue)
        while queue and len(impacted) < limit:
            cur = queue.pop(0)
            for pred in g.predecessors(cur):
                if g.edges[pred, cur].get("edge_type") != "IMPORTS":
                    continue
                if pred not in seen:
                    seen.add(pred)
                    impacted.add(pred)
                    queue.append(pred)

        impacted_paths = [n.split("module:", 1)[1] for n in sorted(impacted)]
        answer = f"Downstream importers of `{module_path}`: " + (", ".join(impacted_paths) if impacted_paths else "(none)")
        return QueryResult(answer=answer, evidence=[{"module": module_path, "downstream_importers": impacted_paths}])

    def explain_module(self, module_graph: KnowledgeGraph, module_path: str) -> QueryResult:
        node = f"module:{module_path}"
        if node not in module_graph.graph:
            return QueryResult(answer=f"Module not found: {module_path}", evidence=[])
        attrs = module_graph.graph.nodes[node]
        purpose = attrs.get("purpose_statement") or "(no purpose_statement; run analyze with OPENAI_API_KEY)"
        domain = attrs.get("domain_cluster") or "unknown"
        answer = f"`{module_path}` [{domain}]: {purpose}"
        return QueryResult(answer=answer, evidence=[{"module": module_path, "attrs": dict(attrs)}])

    def find_implementation(self, module_graph: KnowledgeGraph, concept: str, limit: int = 10) -> QueryResult:
        concept_l = concept.lower().strip()
        scored: list[tuple[int, str]] = []
        for node_id, attrs in module_graph.nodes():
            if attrs.get("node_type") != "ModuleNode":
                continue
            purpose = str(attrs.get("purpose_statement") or "").lower()
            path = str(attrs.get("path") or "")
            score = 0
            if concept_l and concept_l in purpose:
                score += 3
            if concept_l and concept_l in path.lower():
                score += 2
            if score:
                scored.append((score, node_id))
        scored.sort(reverse=True)
        hits = [nid.split("module:", 1)[1] for _, nid in scored[:limit]]
        answer = f"Likely locations for `{concept}`: " + (", ".join(hits) if hits else "(none found; need Semanticist purpose statements)")
        return QueryResult(answer=answer, evidence=[{"concept": concept, "hits": hits}])

