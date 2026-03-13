from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from src.graph.knowledge_graph import KnowledgeGraph
from src.llm.openai_client import OpenAIClient
from src.utils import guess_language


console = Console()


@dataclass
class SemanticistResult:
    updated_module_graph: KnowledgeGraph
    warnings: list[str]
    stats: dict[str, Any] = field(default_factory=dict)


class Semanticist:
    """
    Final-phase agent:
    - generates per-module purpose statements (LLM if configured)
    - assigns a coarse domain label (LLM if configured, else heuristic)
    - flags docstring vs implementation drift (best-effort, Python only)
    - optionally synthesizes Day-One Q&A over Surveyor + Hydrologist output
    - tracks an approximate token budget per run
    """

    def __init__(
        self,
        llm: OpenAIClient | None = None,
        max_tokens_per_run: int = 80_000,
    ) -> None:
        self.llm = llm or OpenAIClient()
        # very rough approximation: len(chars) / 4 ≈ tokens
        self.max_tokens_per_run = max_tokens_per_run
        self._tokens_used = 0

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _charge_tokens(self, *chunks: str) -> bool:
        if self.max_tokens_per_run <= 0:
            return False
        est = sum(self._estimate_tokens(c) for c in chunks)
        if self._tokens_used + est > self.max_tokens_per_run:
            return False
        self._tokens_used += est
        return True

    def run(
        self,
        repo_root: Path,
        module_graph: KnowledgeGraph,
        lineage_graph: Optional[KnowledgeGraph] = None,
    ) -> SemanticistResult:
        warnings: list[str] = []

        # Only summarize code files we already represent as module nodes
        for node_id, attrs in list(module_graph.nodes()):
            if attrs.get("node_type") != "ModuleNode":
                continue
            rel = attrs.get("path")
            if not isinstance(rel, str):
                continue
            path = repo_root / rel
            if not path.exists() or not path.is_file():
                continue

            lang = guess_language(path)
            try:
                code = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                warnings.append(f"semanticist_read_failed:{rel}:{e!r}")
                continue

            purpose, domain = self._purpose_and_domain(rel, lang, code)
            module_graph.graph.nodes[node_id]["purpose_statement"] = purpose
            module_graph.graph.nodes[node_id]["domain_cluster"] = domain

            # Python-only docstring drift detection (best-effort)
            if lang == "python":
                doc = self._extract_module_docstring(code)
                if doc and self.llm.enabled() and self._charge_tokens(doc, code[:4000]):
                    drift = self._docstring_drift(rel, doc, code[:4000])
                    if drift:
                        severity = drift.get("severity", "unknown")
                        module_graph.graph.nodes[node_id]["doc_drift_severity"] = severity
                        module_graph.graph.nodes[node_id]["doc_drift_notes"] = drift.get("notes", "")
                        if severity in {"medium", "high"}:
                            warnings.append(f"doc_drift:{rel}:{severity}")

        # Optional Day-One Q&A synthesizer (only if lineage graph and LLM available)
        day_one_answers: dict[str, Any] | None = None
        if lineage_graph is not None and self.llm.enabled():
            try:
                day_one_answers = self._answer_day_one_questions(repo_root, module_graph, lineage_graph)
                module_graph.graph.graph["day_one_answers"] = day_one_answers
            except Exception as e:  # pragma: no cover - defensive
                warnings.append(f"day_one_qa_failed:{e!r}")

        stats = {
            "tokens_used_estimate": self._tokens_used,
            "max_tokens_per_run": self.max_tokens_per_run,
            "day_one_answers_generated": bool(day_one_answers),
        }
        return SemanticistResult(updated_module_graph=module_graph, warnings=warnings, stats=stats)

    def _purpose_and_domain(self, rel: str, lang: str, code: str) -> tuple[str, str]:
        # keep prompts small for cost/latency
        code_snippet = code[:12000]
        if self.llm.enabled() and self._charge_tokens(code_snippet):
            system = (
                "You are a forward-deployed engineer building a codebase map. "
                "Extract PURPOSE, not implementation details. Be concrete and concise."
            )
            user = (
                f"File: {rel}\n"
                f"Language: {lang}\n\n"
                "Return JSON with keys:\n"
                '- "purpose_statement": 2-3 sentences describing what this module does.\n'
                '- "domain": one of ["ingestion","transformation","serving","monitoring","infra","tests","docs","unknown"]\n\n'
                "Code:\n"
                f"{code_snippet}\n"
            )
            try:
                raw = self.llm.chat(system=system, user=user)
                data = json.loads(raw.strip().strip("```").strip())
                purpose = str(data.get("purpose_statement", "")).strip()
                domain = str(data.get("domain", "unknown")).strip()
                if not purpose:
                    purpose = "Purpose could not be inferred."
                if domain not in {
                    "ingestion",
                    "transformation",
                    "serving",
                    "monitoring",
                    "infra",
                    "tests",
                    "docs",
                    "unknown",
                }:
                    domain = "unknown"
                return purpose, domain
            except Exception:
                # fall through to heuristic
                pass

        # heuristic fallback
        lowered = code.lower()
        if "airflow" in lowered or "dag" in lowered:
            domain = "orchestration"
        elif "select" in lowered and "from" in lowered:
            domain = "transformation"
        elif "read_csv" in lowered or "read_parquet" in lowered:
            domain = "ingestion"
        elif "test" in rel.lower():
            domain = "tests"
        else:
            domain = "unknown"
        purpose = f"Module at {rel} (LLM disabled; purpose not yet generated)."
        return purpose, domain

    def _extract_module_docstring(self, code: str) -> str | None:
        """
        Very simple heuristic: first top-level triple-quoted string is treated as module docstring.
        """
        stripped = code.lstrip()
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                end_idx = stripped.find(quote, len(quote))
                if end_idx != -1:
                    return stripped[len(quote) : end_idx].strip()
        return None

    def _docstring_drift(self, rel: str, docstring: str, code_snippet: str) -> dict[str, str] | None:
        """
        Ask the LLM to rate documentation drift between the declared docstring and implementation snippet.
        Returns a dict with severity: none|low|medium|high and free-text notes.
        """
        if not self.llm.enabled():
            return None
        system = (
            "You are reviewing a Python module docstring against its implementation. "
            "Rate how out-of-date or misleading the docstring is compared to the code."
        )
        user = (
            f"File: {rel}\n\n"
            "Return strict JSON with keys:\n"
            '- "severity": one of ["none","low","medium","high"]\n'
            '- "notes": 1-2 sentences explaining the drift (or why there is none)\n\n'
            f"Module docstring:\n{docstring}\n\n"
            "Implementation snippet (may be truncated):\n"
            f"{code_snippet}\n"
        )
        raw = self.llm.chat(system=system, user=user)
        try:
            data = json.loads(raw.strip().strip("```").strip())
        except Exception:
            return None
        severity = str(data.get("severity", "unknown")).strip().lower()
        if severity not in {"none", "low", "medium", "high"}:
            severity = "unknown"
        notes = str(data.get("notes", "")).strip()
        return {"severity": severity, "notes": notes}

    def _answer_day_one_questions(
        self,
        repo_root: Path,
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
    ) -> dict[str, Any]:
        """
        Synthesize answers to the five FDE Day-One questions using Surveyor + Hydrologist outputs.
        """
        # lightweight structural context for the LLM
        g = lineage_graph.graph
        datasets = [n for n, a in g.nodes(data=True) if a.get("node_type") == "DatasetNode"]
        sources = [n for n in datasets if g.in_degree(n) == 0]
        sinks = [n for n in datasets if g.out_degree(n) == 0]

        ranked = module_graph.graph.graph.get("ranked_critical_modules") or []
        hubs = [item["module"] for item in ranked[:5]] if ranked else []

        # keep context compact
        sources_preview = ", ".join(sorted(sources)[:10])
        sinks_preview = ", ".join(sorted(sinks)[:10])
        hubs_preview = ", ".join(hubs[:5])

        system = (
            "You are a forward-deployed engineer synthesizing a Day-One Brief for a data platform. "
            "Use the provided structural context to answer the five FDE Day-One questions."
        )
        user = (
            f"Repo root: {repo_root}\n\n"
            "Context (summarized):\n"
            f"- Source datasets (in-degree=0): {sources_preview or '(none)'}\n"
            f"- Sink datasets (out-degree=0): {sinks_preview or '(none)'}\n"
            f"- Critical modules (PageRank/velocity hubs): {hubs_preview or '(none)'}\n\n"
            "Return strict JSON with keys q1..q5, each an object with:\n"
            '- "answer": short text\n'
            '- "evidence": list of strings like \"file:line-or-node-id\" if available\n\n"
            "Questions:\n"
            "1) What is the primary data ingestion path?\n"
            "2) What are the 3–5 most critical output datasets/endpoints?\n"
            "3) What is the blast radius if the most critical module fails?\n"
            "4) Where is the business logic concentrated vs. distributed?\n"
            "5) What has changed most frequently in the last 90 days?\n"
        )
        if not self._charge_tokens(user):
            raise RuntimeError("Token budget exceeded before Day-One Q&A")
        raw = self.llm.chat(system=system, user=user)
        data = json.loads(raw.strip().strip("```").strip())
        return data


