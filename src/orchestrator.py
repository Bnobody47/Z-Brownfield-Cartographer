from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console

from src.agents.hydrologist import Hydrologist
from src.agents.surveyor import Surveyor
from src.models.graphs import CartographyRunSummary


console = Console()


@dataclass
class OrchestratorOutputs:
    summary: CartographyRunSummary
    module_graph_path: Path
    lineage_graph_path: Path


class Orchestrator:
    def __init__(self) -> None:
        self.surveyor = Surveyor()
        self.hydrologist = Hydrologist()

    def analyze(self, repo_root: Path) -> OrchestratorOutputs:
        carto_dir = repo_root / ".cartography"
        carto_dir.mkdir(parents=True, exist_ok=True)

        summary = CartographyRunSummary(repo_root=str(repo_root))

        console.print(f"[bold]Surveyor[/bold] analyzing structure: {repo_root}")
        survey = self.surveyor.run(repo_root)
        module_graph_path = carto_dir / "module_graph.json"
        survey.module_graph.write_json(module_graph_path)

        console.print(f"[bold]Hydrologist[/bold] analyzing lineage: {repo_root}")
        hydro = self.hydrologist.run(repo_root)
        lineage_graph_path = carto_dir / "lineage_graph.json"
        hydro.lineage_graph.write_json(lineage_graph_path)

        summary.module_count = survey.module_graph.graph.number_of_nodes()
        summary.module_edge_count = survey.module_graph.graph.number_of_edges()
        summary.dataset_count = sum(
            1 for _, a in hydro.lineage_graph.graph.nodes(data=True) if a.get("node_type") == "DatasetNode"
        )
        summary.lineage_edge_count = hydro.lineage_graph.graph.number_of_edges()
        summary.warnings.extend(survey.warnings)
        summary.warnings.extend(hydro.warnings)
        summary.finished_at = datetime.utcnow()

        (carto_dir / "run_summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")

        return OrchestratorOutputs(
            summary=summary,
            module_graph_path=module_graph_path,
            lineage_graph_path=lineage_graph_path,
        )

