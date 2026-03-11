from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from src.orchestrator import Orchestrator


app = typer.Typer(add_completion=False, help="The Brownfield Cartographer")
console = Console()


def _resolve_repo(repo: str) -> Path:
    """
    Accept either a local path or a GitHub URL and return a local path.
    For GitHub URLs, clone into ./targets/<owner>__<repo>.
    """
    if repo.startswith("http://") or repo.startswith("https://") or repo.startswith("git@"):
        # crude GitHub URL handling; assumes https://github.com/<owner>/<name>[.git]
        # or git@github.com:<owner>/<name>.git
        from subprocess import CalledProcessError, check_call

        console.print(f"[bold]Cloning GitHub repo[/bold]: {repo}")
        # derive owner__name as folder
        slug = repo.rstrip("/").split("/")[-2:]
        if len(slug) == 2:
            owner, name = slug
        else:
            owner, name = "remote", slug[-1]
        if name.endswith(".git"):
            name = name[:-4]
        target = Path("targets") / f"{owner}__{name}"
        target = target.resolve()
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                check_call(["git", "clone", "--depth", "1", repo, str(target)])
            except CalledProcessError as exc:  # pragma: no cover
                raise typer.BadParameter(f"Failed to clone repo: {repo}") from exc
        return target

    repo_root = Path(repo).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise typer.BadParameter(f"Not a directory: {repo_root}")
    return repo_root


def _run_analyze(repo: str) -> None:
    repo_root = _resolve_repo(repo)
    console.print(f"[bold]Analyzing[/bold] {repo_root}")
    out = Orchestrator().analyze(repo_root)
    console.print("[bold green]Done.[/bold green]")
    console.print(f"- module graph: {out.module_graph_path}")
    console.print(f"- lineage graph: {out.lineage_graph_path}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    repo: Optional[str] = typer.Argument(None, help="Local repo path or GitHub URL (shorthand for `analyze`)"),
) -> None:
    """
    If called as `cartographer <repo>`, treat it as `cartographer analyze <repo>`.
    """
    if ctx.invoked_subcommand is None:
        if repo is None:
            raise typer.BadParameter("Provide a repo path, or run `cartographer analyze <repo>`.")
        _run_analyze(repo)


@app.command("analyze")
def analyze_cmd(repo: str = typer.Argument(..., help="Local repo path or GitHub URL")) -> None:
    _run_analyze(repo)


if __name__ == "__main__":
    app()

