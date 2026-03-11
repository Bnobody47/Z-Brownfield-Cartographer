---
title: "TRP 1 Week 4 — Brownfield Cartographer (Interim)"
date: 2026-03-11
---

## Reconnaissance (manual)

See `RECONNAISSANCE.md` (target: `targets/jaffle_shop`).

## System architecture (interim)

Interim pipeline implemented:

`CLI` → `Orchestrator` → **Surveyor** (structure) → **Hydrologist** (SQL lineage) → `.cartography/` artifacts

Artifacts written per analyzed repo:

- `.cartography/module_graph.json`
- `.cartography/lineage_graph.json`
- `.cartography/run_summary.json`

## What’s working

- **CLI + orchestration**: local path analysis runs end-to-end.
- **Surveyor**:
  - Python import parsing via tree-sitter (best-effort)
  - module graph serialization
  - hub scoring via PageRank (pure Python, no SciPy)
  - SCC detection for circular imports (when present)
- **Hydrologist**:
  - SQL parsing via sqlglot
  - dbt/Jinja best-effort preprocessing for `ref()` / `source()` / `{% ... %}` blocks
  - model-file convention: `models/<name>.sql` produces dataset `<name>`
  - lineage graph serialization

## Proof of execution (artifacts)

Target: `targets/jaffle_shop`

- `targets/jaffle_shop/.cartography/module_graph.json`
- `targets/jaffle_shop/.cartography/lineage_graph.json`

From `targets/jaffle_shop/.cartography/run_summary.json`:

- modules: 8
- datasets: 15
- lineage edges: 27

## Early accuracy observations

- **Lineage**: captures the expected high-level dbt DAG shape (staging → marts) from templated SQL by sanitizing Jinja to parse with sqlglot.
- **Limitations**: this is **not dbt compilation**; it’s a sanitizer. Edge cases will exist for complex macros/materializations.

## Known gaps (planned for final)

- **Git velocity map**: compute 30/90‑day change frequency (requires full git history and robust path mapping).
- **Dead code candidates**: needs repo-wide symbol reference counting (calls/import usage), not just imports.
- **Python/YAML lineage**: pandas/PySpark I/O, Airflow DAG dependency extraction, dbt YAML (`schema.yml`) sources/tests metadata.
- **Semanticist + Archivist + Navigator**: purpose statements, doc drift flags, CODEBASE.md + onboarding brief generation, interactive query mode.

