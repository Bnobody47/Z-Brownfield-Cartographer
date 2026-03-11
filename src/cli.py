from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from src.orchestrator import Orchestrator


app = typer.Typer(add_completion=False, help="The Brownfield Cartographer")
console = Console()


@app.command()
def analyze(repo: str = typer.Argument(..., help="Local repo path (interim)")) -> None:
    repo_root = Path(repo).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise typer.BadParameter(f"Not a directory: {repo_root}")

    out = Orchestrator().analyze(repo_root)
    console.print("[bold green]Done.[/bold green]")
    console.print(f"- module graph: {out.module_graph_path}")
    console.print(f"- lineage graph: {out.lineage_graph_path}")


if __name__ == "__main__":
    app()

