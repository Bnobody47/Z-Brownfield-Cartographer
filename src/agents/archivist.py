from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from src.agents.hydrologist import Hydrologist
from src.graph.knowledge_graph import KnowledgeGraph


console = Console()


@dataclass
class ArchivistOutputs:
    codebase_md_path: Path
    onboarding_brief_path: Path
    trace_path: Path
    semantic_index_dir: Path


class Archivist:
    """
    Generates living artifacts from graphs (minimal final implementation).
    """

    def __init__(self) -> None:
        self.hydrologist = Hydrologist()

    def run(
        self,
        repo_root: Path,
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
        run_meta: dict[str, Any],
    ) -> ArchivistOutputs:
        carto_dir = repo_root / ".cartography"
        carto_dir.mkdir(parents=True, exist_ok=True)

        trace_path = carto_dir / "cartography_trace.jsonl"
        semantic_index_dir = carto_dir / "semantic_index"
        semantic_index_dir.mkdir(parents=True, exist_ok=True)

        codebase_md_path = carto_dir / "CODEBASE.md"
        onboarding_brief_path = carto_dir / "onboarding_brief.md"

        self._append_trace(trace_path, {"event": "archivist_start", **run_meta})

        codebase_md_path.write_text(
            self._render_codebase_md(repo_root, module_graph, lineage_graph),
            encoding="utf-8",
        )
        onboarding_brief_path.write_text(
            self._render_onboarding_brief(repo_root, module_graph, lineage_graph),
            encoding="utf-8",
        )

        # semantic index: one JSONL per module node with purpose/domain
        idx_path = semantic_index_dir / "module_index.jsonl"
        with idx_path.open("w", encoding="utf-8") as f:
            for node_id, attrs in module_graph.nodes():
                if attrs.get("node_type") != "ModuleNode":
                    continue
                f.write(json.dumps({"id": node_id, **attrs}, ensure_ascii=False) + "\n")

        self._append_trace(
            trace_path,
            {
                "event": "archivist_done",
                "written": {
                    "CODEBASE.md": str(codebase_md_path),
                    "onboarding_brief.md": str(onboarding_brief_path),
                    "semantic_index": str(semantic_index_dir),
                },
                "ts": datetime.utcnow().isoformat(),
            },
        )

        return ArchivistOutputs(
            codebase_md_path=codebase_md_path,
            onboarding_brief_path=onboarding_brief_path,
            trace_path=trace_path,
            semantic_index_dir=semantic_index_dir,
        )

    def _append_trace(self, path: Path, obj: dict[str, Any]) -> None:
        obj = dict(obj)
        obj.setdefault("ts", datetime.utcnow().isoformat())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def _render_codebase_md(
        self, repo_root: Path, module_graph: KnowledgeGraph, lineage_graph: KnowledgeGraph
    ) -> str:
        pr = []
        ranked = module_graph.graph.graph.get("ranked_critical_modules") or []
        for item in ranked[:5]:
            pr.append(f"- {item['module']} (score={item['score']:.6f})")
        pr_section = "\n".join(pr) if pr else "- (no ranking available)"

        sources = self.hydrologist.find_sources(lineage_graph)
        sinks = self.hydrologist.find_sinks(lineage_graph)

        debt = []
        sccs = module_graph.graph.graph.get("strongly_connected_components") or []
        if sccs:
            debt.append(f"- Circular dependencies detected: {len(sccs)} SCC(s)")
        dead = module_graph.graph.graph.get("dead_code_candidates") or []
        if dead:
            debt.append(f"- Dead code candidates (public symbols but no importers): {len(dead)} module(s)")
        debt_section = "\n".join(debt) if debt else "- None detected (best-effort)."

        # purpose index
        purpose_lines = []
        for node_id, attrs in module_graph.nodes():
            if attrs.get("node_type") != "ModuleNode":
                continue
            path = attrs.get("path")
            purpose = attrs.get("purpose_statement") or ""
            domain = attrs.get("domain_cluster") or "unknown"
            if isinstance(path, str):
                purpose_lines.append(f"- `{path}` [{domain}]: {purpose}")
        purpose_section = "\n".join(sorted(purpose_lines)) if purpose_lines else "- (not generated)"

        return f"""# CODEBASE.md (Living Context)

## Architecture Overview
This repo was analyzed by the Brownfield Cartographer. The current model includes a module import graph (Surveyor) and a data lineage graph (Hydrologist). Semantic purpose statements may be present if an LLM key was configured.

## Critical Path (top hubs)
{pr_section}

## Data Sources & Sinks (lineage graph)
- **Sources** (in-degree=0): {", ".join(sources) if sources else "(none detected)"}
- **Sinks** (out-degree=0): {", ".join(sinks) if sinks else "(none detected)"}

## Known Debt / Risk Signals
{debt_section}

## Module Purpose Index
{purpose_section}
"""

    def _render_onboarding_brief(
        self, repo_root: Path, module_graph: KnowledgeGraph, lineage_graph: KnowledgeGraph
    ) -> str:
        # Prefer LLM-synthesized Day-One answers if Semanticist provided them
        day_one = module_graph.graph.graph.get("day_one_answers") or {}
        if isinstance(day_one, dict) and all(k in day_one for k in ("q1", "q2", "q3", "q4", "q5")):
            def _fmt(q: dict[str, Any]) -> tuple[str, str]:
                ans = str(q.get("answer", "")).strip() or "(no answer)"
                ev_list = q.get("evidence") or []
                if isinstance(ev_list, list):
                    ev = ", ".join(str(e) for e in ev_list[:8])
                else:
                    ev = str(ev_list)
                return ans, ev or "(no explicit evidence)"

            q1_a, q1_e = _fmt(day_one.get("q1", {}))
            q2_a, q2_e = _fmt(day_one.get("q2", {}))
            q3_a, q3_e = _fmt(day_one.get("q3", {}))
            q4_a, q4_e = _fmt(day_one.get("q4", {}))
            q5_a, q5_e = _fmt(day_one.get("q5", {}))

            return f"""# FDE Day-One Brief

## 1) What is the primary ingestion path?
{q1_a}

**Evidence:** {q1_e}

## 2) What are the 3–5 most critical outputs?
{q2_a}

**Evidence:** {q2_e}

## 3) What is the blast radius if a critical module fails?
{q3_a}

**Evidence:** {q3_e}

## 4) Where is business logic concentrated vs distributed?
{q4_a}

**Evidence:** {q4_e}

## 5) What changed most frequently recently?
{q5_a}

**Evidence:** {q5_e}
"""

        # Fallback: structural best-effort answers
        sources = self.hydrologist.find_sources(lineage_graph)
        sinks = self.hydrologist.find_sinks(lineage_graph)

        ranked = module_graph.graph.graph.get("ranked_critical_modules") or []
        hubs = [item["module"] for item in ranked[:5]] if ranked else []

        return f"""# FDE Day-One Brief

## 1) What is the primary ingestion path?
- Entry datasets (best-effort): {", ".join(sources) if sources else "(unknown)"}.

## 2) What are the 3–5 most critical outputs?
- Exit datasets (best-effort): {", ".join(sinks[:5]) if sinks else "(unknown)"}.

## 3) What is the blast radius if a critical module fails?
- Structural hubs (best-effort from PageRank/velocity): {", ".join(hubs) if hubs else "(unknown)"}.

## 4) Where is business logic concentrated vs distributed?
- See `CODEBASE.md` module purpose index (LLM-backed if configured) plus critical path hubs.

## 5) What changed most frequently recently?
- See module node attribute `change_velocity_30d` (only meaningful when full git history is available locally).
"""

