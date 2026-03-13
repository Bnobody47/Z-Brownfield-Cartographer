from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from src.graph.knowledge_graph import KnowledgeGraph
from src.llm.openai_client import OpenAIClient
from src.utils import guess_language, iter_files, relpath_posix


console = Console()


@dataclass
class SemanticistResult:
    updated_module_graph: KnowledgeGraph
    warnings: list[str]


class Semanticist:
    """
    Final-phase agent (minimal implementation):
    - generates per-module purpose statements (LLM if configured)
    - assigns a coarse domain label (LLM if configured, else heuristic)
    - flags doc drift is deferred (requires docstring extraction + comparison)
    """

    def __init__(self, llm: OpenAIClient | None = None) -> None:
        self.llm = llm or OpenAIClient()

    def run(self, repo_root: Path, module_graph: KnowledgeGraph) -> SemanticistResult:
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

        return SemanticistResult(updated_module_graph=module_graph, warnings=warnings)

    def _purpose_and_domain(self, rel: str, lang: str, code: str) -> tuple[str, str]:
        # keep prompts small for cost/latency
        code_snippet = code[:12000]
        if self.llm.enabled():
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

