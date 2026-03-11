from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from src.orchestrator import Orchestrator


app = typer.Typer(add_completion=False, help="The Brownfield Cartographer")
console = Console()


def _run_analyze(repo: str) -> None:
    repo_root = Path(repo).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise typer.BadParameter(f"Not a directory: {repo_root}")

    out = Orchestrator().analyze(repo_root)
    console.print("[bold green]Done.[/bold green]")
    console.print(f"- module graph: {out.module_graph_path}")
    console.print(f"- lineage graph: {out.lineage_graph_path}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    repo: str | None = typer.Argument(None, help="Local repo path (shorthand for `analyze`)"),
) -> None:
    """
    If called as `cartographer <repo>`, treat it as `cartographer analyze <repo>`.
    """
    if ctx.invoked_subcommand is None:
        if repo is None:
            raise typer.BadParameter("Provide a repo path, or run `cartographer analyze <repo>`.")
        _run_analyze(repo)


@app.command("analyze")
def analyze_cmd(repo: str = typer.Argument(..., help="Local repo path (interim)")) -> None:
    _run_analyze(repo)


if __name__ == "__main__":
    app()

