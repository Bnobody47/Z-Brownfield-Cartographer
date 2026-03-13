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
    tool: str | None = None


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
            return QueryResult(answer=f"Dataset not found: {dataset}", evidence=[], tool="trace_lineage")

        g = lineage_graph.graph
        out: list[str] = []
        evidence: list[dict[str, Any]] = []

        if direction == "downstream":
            # use blast_radius plus evidence
            impacted = self.hydrologist.blast_radius(lineage_graph, dataset)[:limit]
            for ds in impacted:
                out.append(ds)
            answer = f"Downstream of `{dataset}`: " + (", ".join(out) if out else "(none)")
            return QueryResult(
                answer=answer,
                evidence=[{"dataset": dataset, "impacted": impacted, "analysis": "static_lineage"}],
                tool="trace_lineage",
            )

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
        # tag each evidence item with analysis metadata
        for ev in evidence:
            ev.setdefault("analysis", "static_lineage")
            if isinstance(ev.get("source_file"), str):
                ev.setdefault("source", ev["source_file"])
        answer = f"Upstream of `{dataset}` (best-effort): " + (", ".join(upstream) if upstream else "(none)")
        return QueryResult(answer=answer, evidence=evidence, tool="trace_lineage")

    def blast_radius_module(self, module_graph: KnowledgeGraph, module_path: str, limit: int = 100) -> QueryResult:
        start = f"module:{module_path}"
        g = module_graph.graph
        if start not in g:
            return QueryResult(answer=f"Module not found: {module_path}", evidence=[], tool="blast_radius_module")

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
        return QueryResult(
            answer=answer,
            evidence=[
                {
                    "module": module_path,
                    "downstream_importers": impacted_paths,
                    "analysis": "static_import_graph",
                }
            ],
            tool="blast_radius_module",
        )

    def explain_module(self, module_graph: KnowledgeGraph, module_path: str) -> QueryResult:
        node = f"module:{module_path}"
        if node not in module_graph.graph:
            return QueryResult(answer=f"Module not found: {module_path}", evidence=[], tool="explain_module")
        attrs = module_graph.graph.nodes[node]
        purpose = attrs.get("purpose_statement") or "(no purpose_statement; run analyze with OPENAI_API_KEY)"
        domain = attrs.get("domain_cluster") or "unknown"
        # crude heuristic: if purpose comes from LLM run, it will not contain the fallback phrase
        analysis = "llm_semanticist"
        if "LLM disabled; purpose not yet generated" in str(purpose):
            analysis = "heuristic_semanticist"
        answer = f"`{module_path}` [{domain}]: {purpose}"
        return QueryResult(
            answer=answer,
            evidence=[{"module": module_path, "attrs": dict(attrs), "analysis": analysis}],
            tool="explain_module",
        )

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
        return QueryResult(
            answer=answer,
            evidence=[{"concept": concept, "hits": hits, "analysis": "semantic_search"}],
            tool="find_implementation",
        )

    def route_nl_query(
        self,
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
        question: str,
    ) -> QueryResult:
        """
        Very small LangGraph-style router: inspects a natural language question and
        dispatches to the most likely tool, returning that tool's QueryResult.
        """
        q = question.lower()
        # lineage-style questions
        if "upstream" in q or "source" in q or "comes from" in q:
            # naive dataset guess: last backticked token or last word
            target = question.split("`")[-2] if "`" in question else q.split()[-1]
            return self.trace_lineage(lineage_graph, dataset=target, direction="upstream")
        if "downstream" in q or "impact" in q or "blast radius" in q:
            if ".py" in q or ".sql" in q:
                # treat as module path
                for token in q.split():
                    if token.endswith(".py") or token.endswith(".sql"):
                        return self.blast_radius_module(module_graph, module_path=token)
            # otherwise, assume dataset
            target = question.split("`")[-2] if "`" in question else q.split()[-1]
            return self.trace_lineage(lineage_graph, dataset=target, direction="downstream")
        if "what does" in q or "explain" in q:
            for token in q.split():
                if token.endswith(".py") or token.endswith(".sql"):
                    return self.explain_module(module_graph, module_path=token)
        # default: semantic search over module purposes
        return self.find_implementation(module_graph, concept=question)


