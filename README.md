# The Brownfield Cartographer

Multi-agent codebase intelligence system for rapidly mapping unfamiliar production data/codebases.

## Install (uv recommended)

```bash
uv venv
uv pip install -e .
```

## Run (interim: Surveyor + Hydrologist)

Analyze a **local** repo/path (writes artifacts into `<repo>/.cartography/`):

```bash
cartographer analyze C:\path\to\repo
```

## Outputs

- `.cartography/module_graph.json`: module import graph + basic metrics
- `.cartography/lineage_graph.json`: dataset lineage graph (currently SQL-focused via `sqlglot`)

## Web graph viewer (React)

Interactive viewer for `.cartography/*.json` graphs (upload the JSON; nothing leaves your machine):

```bash
cd web
npm install
npm run dev
```

## Notes

- Git velocity is best-effort (requires `git` and a real git repo).
- Parsing is best-effort: unparseable files are logged and skipped.
