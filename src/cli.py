from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from src.agents.navigator import Navigator
from src.graph.knowledge_graph import KnowledgeGraph
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
    if out.codebase_md_path:
        console.print(f"- CODEBASE: {out.codebase_md_path}")
    if out.onboarding_brief_path:
        console.print(f"- onboarding brief: {out.onboarding_brief_path}")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Brownfield Cartographer CLI."""
    if ctx.invoked_subcommand is None:
        console.print("Run `cartographer analyze <repo>` or `cartographer query <repo> ...`.")


@app.command("analyze")
def analyze_cmd(repo: str = typer.Argument(..., help="Local repo path or GitHub URL")) -> None:
    _run_analyze(repo)


@app.command("query")
def query_cmd(
    repo: str = typer.Argument(..., help="Local repo path or GitHub URL (must have .cartography outputs)"),
    tool: str = typer.Option(..., help="trace_lineage | blast_radius | explain_module | find_implementation"),
    arg: str = typer.Option(..., help="Dataset name, module path, or concept depending on tool"),
    direction: str = typer.Option("upstream", help="For trace_lineage: upstream|downstream"),
) -> None:
    repo_root = _resolve_repo(repo)
    carto = repo_root / ".cartography"
    module_graph = KnowledgeGraph.read_json(carto / "module_graph.json")
    lineage_graph = KnowledgeGraph.read_json(carto / "lineage_graph.json")
    nav = Navigator()

    if tool == "trace_lineage":
        res = nav.trace_lineage(lineage_graph, dataset=arg, direction=direction)  # type: ignore[arg-type]
    elif tool == "blast_radius":
        # if arg looks like module path, use module graph blast radius; else dataset blast radius is in Hydrologist
        if arg.endswith(".py") or arg.endswith(".sql") or arg.startswith("src/"):
            res = nav.blast_radius_module(module_graph, module_path=arg)
        else:
            impacted = nav.hydrologist.blast_radius(lineage_graph, arg)
            res = nav.trace_lineage(lineage_graph, dataset=arg, direction="downstream")
            res.answer = f"Downstream of `{arg}`: " + (", ".join(impacted) if impacted else "(none)")
    elif tool == "explain_module":
        res = nav.explain_module(module_graph, module_path=arg)
    elif tool == "find_implementation":
        res = nav.find_implementation(module_graph, concept=arg)
    else:
        raise typer.BadParameter(f"Unknown tool: {tool}")

    console.print(res.answer)
    if res.evidence:
        console.print_json(data=res.evidence)


@app.command("analyze_default")
def analyze_default(repo: str = typer.Argument(..., help="Shorthand; same as `analyze`")) -> None:
    """
    Back-compat helper: lets you still do `cartographer analyze_default <repo>`.
    """
    _run_analyze(repo)


if __name__ == "__main__":
    app()

