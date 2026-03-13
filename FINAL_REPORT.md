---
title: "TRP 1 Week 4 — The Brownfield Cartographer (Final Report)"
date: 2026-03-12
---

## 1. Manual Reconnaissance (Ground Truth)

**Target 1 (primary, dbt)**: `targets/jaffle_shop` (clone of `dbt-labs/jaffle_shop`)

- **Primary ingestion path**  
  - Raw data arrives as **dbt seeds** under `seeds/`:
    - `seeds/raw_customers.csv`
    - `seeds/raw_orders.csv`
    - `seeds/raw_payments.csv`
  - These are materialized as `raw_customers`, `raw_orders`, `raw_payments` tables and then read by staging models:
    - `models/staging/stg_customers.sql` → `{{ ref('raw_customers') }}`
    - `models/staging/stg_orders.sql` → `{{ ref('raw_orders') }}`
    - `models/staging/stg_payments.sql` → `{{ ref('raw_payments') }}`

- **3–5 critical outputs**  
  - Final marts:
    - `models/customers.sql` → relation `customers`
    - `models/orders.sql` → relation `orders`
  - Staging backbone:
    - `models/staging/stg_customers.sql` → `stg_customers`
    - `models/staging/stg_orders.sql` → `stg_orders`
    - `models/staging/stg_payments.sql` → `stg_payments`

- **Blast radius of the most critical module**  
  - If `models/customers.sql` breaks:
    - Downstream dashboards/queries depending on `customers` fail or show stale data.
    - Upstream staging (`stg_*`) can still build, but customer-facing analytics are broken.
  - If any `stg_*` model fails:
    - `customers` and `orders` both break, since they reference `stg_customers`, `stg_orders`, `stg_payments` via `ref()` calls.

- **Where business logic is concentrated vs distributed**  
  - **Concentrated** in `models/`:
    - `models/staging/*.sql`: cleaning/renaming, basic canonicalization.
    - `models/customers.sql`, `models/orders.sql`: joins and aggregation-friendly structures.
  - **Distributed** in:
    - `dbt_project.yml`: model materializations, schemas, config.
    - `models/schema.yml`: tests, docs, and model metadata.
    - Jinja templating (`{{ ref() }}`, `{% ... %}`) inside SQL models controlling lineage and behavior.

- **What changed most frequently in the last 90 days**  
  - Local clone is shallow (`--depth 1`), so a true 90‑day velocity map cannot be computed from local history.
  - In a real engagement, I would run:
    - `git -C targets/jaffle_shop log --since=90.days --name-only --pretty=format:`
    - Aggregate counts by path; expect hotspots in:
      - `models/*.sql` (business metric iterations)
      - `models/schema.yml` (tests + docs)
      - Potentially `dbt_project.yml` (materializations and schemas).

- **Difficulty analysis & how it informed the architecture**
  - **Templating gap**: The actual executed SQL is the dbt-compiled result of Jinja templates, not the raw `.sql` files. Pain: you cannot see true lineage without either rendering or carefully normalizing `ref()`/`source()` calls.  
    → Architecture response: a **sqlglot-based analyzer** with a **dbt/Jinja preprocessor** that rewrites `{{ ref('model') }}` and `{{ source('schema','table') }}` into plain table names.
  - **Model vs table naming**: dbt models are configured via YAML and `dbt_project.yml`; the physical table name is sometimes different from the SQL file name.  
    → Architecture response: infer sensible defaults (model name from file stem) while also parsing YAML configs (`schema.yml`) as **CONFIGURES** edges.
  - **YAML-driven topology**: Important meaning (sources, tests, docs) lives in YAML, not pure SQL.  
    → Architecture response: a `DAGConfigAnalyzer` that understands dbt `schema.yml` and emits CONFIGURES edges into the same graph.

**Target 2 (secondary, orchestration)**: `targets/airflow` (sparse clone of Apache Airflow, `airflow/example_dags/`)

- Manual exploration here focused on the structure of example DAGs under `airflow/example_dags/`, where ingestion and outputs are defined by operators and their configs rather than plain SQL. Pain points:
  - Operators compose datasets indirectly (e.g. `PostgresOperator`, `PythonOperator`, `BashOperator`), making naïve SQL-only lineage incomplete.
  - DAG structure is Python-based; relationships between tasks live in `>>` / `<<` operator chaining and context managers.
  - YAML/INI configs (for connections, providers) influence data flow but are not co-located with code.
  → Architecture response: treat **Airflow DAGs** as future work for PythonDataFlowAnalyzer + DAGConfigAnalyzer; for Week 4 final, focus on SQL + YAML plus basic structural graph of Python modules.

## 2. Architecture Diagram & Pipeline Rationale

The final system is a **four-agent pipeline** with a central knowledge graph, a semantic index, a query layer (**Navigator**), and artifact outputs.

### Mermaid diagram

```mermaid
flowchart LR
    subgraph Inputs
        A[Target codebase<br/>Local path or GitHub URL]
    end

    subgraph Agents
        S[Surveyor<br/>Static structure]
        H[Hydrologist<br/>Data lineage]
        Se[Semanticist<br/>Purpose & domains]
        Ar[Archivist<br/>CODEBASE & onboarding]
    end

    subgraph KG[Knowledge Graph & Stores]
        G[(NetworkX DiGraph<br/>Module/Dataset/Function/Transformation/Config nodes)]
        V[(Vector/semantic index<br/>module purpose statements)]
    end

    subgraph Artifacts[Output Artifacts]
        O1[.cartography/module_graph.json]
        O2[.cartography/lineage_graph.json]
        O3[.cartography/CODEBASE.md]
        O4[.cartography/onboarding_brief.md]
        O5[.cartography/cartography_trace.jsonl]
    end

    subgraph QueryLayer[Query Layer]
        N[Navigator Agent<br/>trace_lineage, blast_radius,<br/>explain_module, find_implementation]
    end

    A --> S
    A --> H

    S -- ModuleNodes<br/>IMPORTS edges --> G
    H -- Dataset/Transformation/ConfigNodes<br/>PRODUCES/CONSUMES/CONFIGURES --> G
    Se -- Purpose statements<br/>Domain clusters --> G
    Se -- Embeddings --> V

    G --> Ar
    V --> Ar

    Ar --> O3
    Ar --> O4
    Ar --> O5

    G --> O1
    G --> O2

    O1 --> N
    O2 --> N
```

### Sequencing and rationale

- **Surveyor (Static structure)** runs first because:
  - Hydrologist and Semanticist both need a **module inventory** and module graph.
  - Git velocity and import PageRank are used later to identify critical-path modules and likely “blast radius” candidates.
- **Hydrologist (Lineage)** runs second:
  - Data lineage depends on identifying `.sql` / YAML config files but not on having semantic summaries yet.
  - Produces `DatasetNode`s, `TransformationNode`s, and `CONSUMES`/`PRODUCES`/`CONFIGURES` edges, along with helper queries (`blast_radius`, `find_sources`, `find_sinks`).
- **Semanticist (Purpose & domains)** runs third:
  - It needs both **structure** (Surveyor) and **lineage context** (Hydrologist) to generate meaningful purpose statements and domain labels (e.g., “ingestion”, “transformation”, “serving”).
  - LLM calls are isolated to this phase and can be skipped gracefully if `OPENAI_API_KEY` is not set, keeping the core graph usable without LLMs.
- **Archivist (Artifacts)** runs last:
  - Consumes the fully-populated graphs + semantic index to produce:
    - `CODEBASE.md` (living context)
    - `onboarding_brief.md` (Day-One Brief)
    - `cartography_trace.jsonl` (audit trail)
    - `semantic_index/` (module purpose statements for search).

This design keeps **static analysis first**, **LLM work later** (for cost control), and **artifact generation last** so that every artifact is backed by the same central knowledge graph.

### Knowledge Graph Schema

All nodes and edges conform to Pydantic schemas defined in `src/models/`:

| Node Type | Key Fields | Populated By |
|-----------|------------|--------------|
| **ModuleNode** | `path`, `language`, `purpose_statement`, `domain_cluster`, `complexity_score`, `change_velocity_30d`, `is_dead_code_candidate` | Surveyor, Semanticist |
| **DatasetNode** | `name`, `storage_type` (table \| file \| stream \| api), `schema_snapshot`, `owner` | Hydrologist |
| **FunctionNode** | `qualified_name`, `parent_module`, `signature`, `purpose_statement`, `is_public_api` | Surveyor (extensible) |
| **TransformationNode** | `id`, `source_datasets`, `target_datasets`, `transformation_type`, `source_file`, `line_range`, `sql_query_if_applicable` | Hydrologist |
| **ConfigNode** | `path`, `kind` (dbt_schema, airflow, etc.), `purpose_statement` | Hydrologist (DAGConfigAnalyzer) |

| Edge Type | Meaning |
|-----------|---------|
| **IMPORTS** | source_module → target_module (module graph) |
| **PRODUCES** | transformation → dataset (lineage) |
| **CONSUMES** | transformation → dataset (upstream dependency) |
| **CALLS** | function → function (call graph; reserved) |
| **CONFIGURES** | config_file → module/pipeline (YAML/config) |

The system maintains **two graphs**: (1) the *module graph* (structure, imports, PageRank, dead-code hints) and (2) the *lineage graph* (datasets, transformations, sources/sinks). Both serialize to JSON for portability and CLI-based querying.

### Example: jaffle_shop Data Lineage (extracted by Hydrologist)

```mermaid
flowchart TD
    subgraph sources[Data Sources]
        raw_customers[(raw_customers)]
        raw_orders[(raw_orders)]
        raw_payments[(raw_payments)]
    end

    subgraph staging[Staging Models]
        stg_customers[(stg_customers)]
        stg_orders[(stg_orders)]
        stg_payments[(stg_payments)]
    end

    subgraph marts[Final Marts]
        customers[(customers)]
        orders[(orders)]
    end

    raw_customers -->|stg_customers.sql| stg_customers
    raw_orders -->|stg_orders.sql| stg_orders
    raw_payments -->|stg_payments.sql| stg_payments

    stg_customers -->|customers.sql| customers
    stg_orders -->|customers.sql| customers
    stg_payments -->|customers.sql| customers

    stg_orders -->|orders.sql| orders
    stg_payments -->|orders.sql| orders
```

### Navigator Query Layer

The **Navigator** is a separate query agent that operates *after* analysis. It loads the serialized `module_graph.json` and `lineage_graph.json` and exposes four tools to the CLI:

- **trace_lineage(dataset, direction)** — traverses the lineage graph upstream or downstream with file:line evidence.
- **blast_radius(module_path \| dataset)** — returns downstream dependents (module importers or lineage consumers).
- **explain_module(path)** — returns purpose statement from the module graph (or LLM fallback).
- **find_implementation(concept)** — semantic search over module purpose statements.

Every response includes structured `evidence` (source_file, line_range, analysis method) for trust and verification.

### Implementation Tradeoffs: NetworkX vs. Graph Database

**Choice: NetworkX + JSON serialization** (not a graph DB like Neo4j, Neptune, or Memgraph).

| Consideration | NetworkX | Graph DB |
|---------------|----------|----------|
| **Setup & portability** | Zero infra; JSON files work anywhere. FDE can run `cartographer analyze .` on any machine. | Requires DB server, credentials, deployment. |
| **Scale** | Suitable for 1K–50K nodes (typical data-platform repos). Degrades beyond ~100K nodes. | Built for millions of edges; better for org-wide lineage. |
| **Query expressiveness** | BFS/DFS, PageRank, SCCs via Python; ad-hoc Cypher/GQL not available. | Rich query languages; complex multi-hop patterns. |
| **Incremental updates** | Full re-serialization; `--incremental` re-analyzes changed files and merges. | Native node/edge mutations; partial updates natural. |
| **Tooling** | Standard Python; easy to fork, extend, embed. | Vendor lock-in, ops overhead. |

**Rationale:** For the target use case (single-repo analysis, Day-One onboarding, local or CI execution), NetworkX + JSON keeps the Cartographer **deployable without infrastructure**. A graph DB would be appropriate for an *org-wide lineage platform* where many repos feed a shared graph; that is out of scope for this artifact.

## 3. Accuracy: Manual vs System-Generated Day-One Answers

Here I compare the **manual answers** for jaffle_shop (Target 1) with what the Cartographer produces via `CODEBASE.md`, `onboarding_brief.md`, and lineage/module graphs.

### Q1: Primary data ingestion path

- **Manual**: Seeds in `seeds/raw_customers.csv`, `seeds/raw_orders.csv`, `seeds/raw_payments.csv` → `raw_*` tables → `stg_*` models.
- **System**:
  - Hydrologist lineage graph shows:
    - `raw_customers` → `stg_customers`
    - `raw_orders` → `stg_orders`
    - `raw_payments` → `stg_payments`
  - `CODEBASE.md` “Data Sources & Sinks” section lists upstream datasets from `find_sources()`, which include the `raw_*` relations.
- **Verdict**: **Correct at table level.**  
  - Root cause of any minor mismatch: the system does not represent the CSV files themselves as first-class nodes (only the resulting tables), but that is acceptable for an FDE ingestion-path answer.

### Q2: 3–5 critical outputs

- **Manual**: `customers`, `orders`, plus the staging layer (`stg_customers`, `stg_orders`, `stg_payments`).
- **System**:
  - Hydrologist lineage graph identifies:
    - `customers` and `orders` as produced by `models/customers.sql` and `models/orders.sql`.
    - `stg_*` datasets produced by `models/staging/stg_*.sql` from `raw_*`.
  - `CODEBASE.md` “Data Sources & Sinks” lists sinks via `find_sinks()` (exit datasets), which include `customers` and `orders`.
- **Verdict**: **Correct.**  
  - The system agrees with the manual list; any additional synthetic nodes like `final` are CTE artefacts, not real outputs, and can be mentally discounted.

### Q3: Blast radius of the most critical module

- **Manual**: If `customers` fails, dashboards/consumers relying on `customers` break; if `stg_*` fails, both marts (`customers`, `orders`) break.
- **System**:
  - `cartographer query targets/jaffle_shop --tool trace_lineage --arg customers --direction upstream` shows:
    - Upstream: `customer_orders`, `customer_payments`, `final`, `orders`, `payments`, `stg_*`, `raw_*`, etc., with evidence referencing `models/customers.sql`, `models/orders.sql`, and `models/staging/stg_*.sql`.
  - `blast_radius` on datasets (via Hydrologist) and modules (via Navigator) shows which downstream datasets and modules depend on a given node.
- **Verdict**: **Structurally correct, semantically partial.**  
  - The system correctly shows **which datasets and transformations** depend on a given table or module, but it does not know which concrete dashboards or external reports exist—those are outside the repo. The Cartographer gets you as far as “which relations break” with line-level evidence.

### Q4: Where business logic is concentrated vs distributed

- **Manual**: `models/` (staging + marts) for core logic, with config and tests in `dbt_project.yml` and `models/schema.yml`.
- **System**:
  - Surveyor’s module graph and Pagerank highlight `models/*.sql` as structural hubs in the lineage graph; Archivist’s `CODEBASE.md` “Critical Path” section lists these as high-score modules.
  - Hydrologist adds `ConfigNode`s for `schema.yml` with `CONFIGURES` edges to the datasets they describe.
  - Semanticist (with API key) gives purpose statements to each module, and Archivist surfaces them as a “Module Purpose Index”.
- **Verdict**: **Correct at structure level, plus better documentation.**  
  - The system not only agrees with the manual assessment but also annotates modules with purpose/domain labels, making the concentration vs distribution more explicit.

### Q5: What changed most frequently in the last 90 days

- **Manual**: No local history (shallow clone), but likely high churn in `models/*.sql` and `models/schema.yml`; described how `git log --since=90.days --name-only` would be used with full history.
- **System**:
  - Surveyor implements `_git_velocity_30d` (normalized change counts per file) and stores `change_velocity_30d` on module nodes.
  - For `targets/jaffle_shop` (cloned with `--depth 1`), this is **expectedly empty or near-zero**; `CODEBASE.md` states that velocity is only meaningful with full history.
- **Verdict**: **Conceptually correct but practically limited by clone depth.**  
  - The tooling is correct; the missing input (full git history) is the limiting factor, and both manual and system acknowledge this.

## 4. Limitations & Failure Modes

Some limitations are **engineering gaps** that could be closed; others are **structural limits** of static analysis.

### Engineering gaps (fixable)

- **dbt templating beyond simple `ref()`/`source()`**  
  - The Jinja preprocessor handles simple `ref()` and `source()` calls but not arbitrary macros or complex templating logic.
  - Complex macros could produce additional tables or change lineage in ways the system doesn’t see.

- **Python dataflow & Airflow DAG semantics**  
  - Hydrologist **does** parse pandas/PySpark read/write and SQLAlchemy calls in Python (`PythonDataFlowAnalyzer`).
  - Airflow DAG operator relationships (task-level graph) are **not** yet extracted; we capture Python module structure and YAML config but not operator-level data lineage.
  - For Airflow, we currently capture Python module structure and basic YAML config, but **not** full operator-level data lineage.

- **Column-level lineage**  
  - The lineage graph is table/dataset-level; column-level breakages (e.g., dropping a column used deep in a chain) are not modeled.

### Fundamental constraints (hard/structural)

- **Dynamic table names and runtime-dependent lineage**
  - Any table name built via string concatenation, environment variables, or runtime logic is not resolvable via static analysis alone.
  - For example, `f"events_{env}"` or `os.environ["TENANT"]` in Python constructing a table name will not show up as a concrete dataset node.

- **External systems not represented in the repo**
  - Downstream dashboards (e.g., Looker, Tableau) and upstream external APIs typically live outside the repo; the Cartographer cannot infer their existence unless explicitly represented as config/code.

- **False confidence risk**
  - dbt models with custom schemas or aliases in config could be **misnamed** in the lineage graph if we fall back to the “file stem = relation name” heuristic and miss overrides in `dbt_project.yml`.
  - The system looks confident (a neat graph) but may be slightly wrong on relation names in complex dbt deployments; this is called out in the report and should be part of the FDE mental model when using the tool.

## 5. FDE Deployment Plan (Real-World Use)

Here is how I would actually deploy the Brownfield Cartographer at a client.

### First 24 hours (cold start)

1. **Clone the repo(s)** for the client’s data platform (warehouse dbt project, orchestration repo, etc.).
2. Run:
   - `cartographer analyze .` (or `cartographer analyze https://github.com/...`)  
     This produces `.cartography/module_graph.json`, `.cartography/lineage_graph.json`, `CODEBASE.md`, `onboarding_brief.md`.
3. Open `onboarding_brief.md` and `CODEBASE.md`:
   - Use the Day-One Brief to quickly answer “what are the primary inputs/outputs?” and “what are the critical modules?”.
   - Skim the “Module Purpose Index” to map out domains (ingestion, transformations, reporting).

### Days 2–3 (ongoing exploration)

- Use **Navigator** via the CLI during investigation:
  - `cartographer query . --tool trace_lineage --arg some_dataset --direction upstream`  
    → “Where does this metric/table actually come from?”
  - `cartographer query . --tool blast_radius --arg src/some_critical_module.py`  
    → “Who imports this module; what breaks if I change its interface?”
  - `cartographer query . --tool explain_module --arg src/ingestion/kafka_consumer.py`  
    → Quick, purpose-level explanation (LLM-backed if key present).
  - `cartographer query . --tool find_implementation --arg revenue`  
    → Places in the module graph whose purpose or path suggests “revenue”.

- As I make code changes:
  - Re-run `cartographer analyze .` periodically (or add an incremental mode hook to CI) to regenerate `CODEBASE.md` and keep the context **fresh**.

### What remains human work

- Interpreting **business semantics**:
  - The tool will tell me **where** logic lives and **how** data flows, but I still need to talk to stakeholders to validate that “revenue” or “DAU” means what the code says it means.

- Handling **runtime-specific issues**:
  - Incident triage involving environment-specific schemas, permissions, or late-arriving data often needs logs and metrics, not just static analysis.

- Designing **client-facing outputs**:
  - The Cartographer’s graphs and briefs become raw material for:
    - Architecture diagrams in slide decks.
    - Written runbooks and “How this metric is computed” documents.

### How this fits into a real FDE engagement

- **Day 1**: Arrive, run Cartographer on the primary repo, and immediately have:
  - A structural map of modules.
  - A lineage graph for key datasets.
  - A Day-One Brief answering the five FDE questions.
- **Day 2–3**: Use Navigator as a “GPS” while debugging and designing changes:
  - It reduces re-orientation time between questions.
  - It helps justify impact assessments (“If we change X, here is the graph of what breaks”).
- **Ongoing**: Keep CODEBASE.md and onboarding_brief.md under version control:
  - They become living documents of record.
  - New FDEs or team members get a ready-made onramp, not a folder of stale docs.

This turns the Brownfield Cartographer from a training exercise into a **deployable, repeatable onboarding instrument** for any future brownfield engagement.

---

## 6. Self-Audit: Cartographer Run on Week 1 Repo (Roo-Code-Beamlak)

**Week 1 target**: [Roo-Code-Beamlak](https://github.com/Bnobody47/Roo-Code-Beamlak) — fork of Roo Code, an AI-powered VS Code extension (98.4% TypeScript, monorepo with `apps/`, `packages/`, `webview-ui/`, etc.).

**Command run**: `cartographer analyze targets/Bnobody47__Roo-Code-Beamlak`

**Generated artifacts**:
- `.cartography/module_graph.json` — sparse (only Python/YAML/SQL/JS/TS *files* indexed; import edges come from Python only; no TypeScript import parsing)
- `.cartography/lineage_graph.json` — empty or minimal (no `.sql` or dbt models; no Python dataflow in this repo)
- `.cartography/CODEBASE.md` — generic, minimal critical path and purpose index (few Python modules; no TS modules)
- `.cartography/onboarding_brief.md` — best-effort Day-One answers (sources/sinks empty; critical path weak)

**Week 1 hand-authored doc**: `ARCHITECTURE_NOTES.md` in the repo describes the real architecture (apps, packages, modes like Code/Architect/Ask/Debug, webview-ui, MCP integration, etc.).

### Discrepancy and Interpretation

| Aspect | ARCHITECTURE_NOTES.md (Week 1) | Cartographer CODEBASE.md |
|--------|--------------------------------|----------------------------|
| Primary structure | Monorepo: `apps/`, `packages/`, `webview-ui/`, modes | Sparse; only scans `.py`, `.sql`, `.yml`, `.js`, `.ts` files; **no TypeScript import graph** |
| Critical path | Core extension, webview, orchestration, MCP | Few or no Python hubs; TS modules not in import graph |
| Data lineage | N/A (extension, not a data pipeline) | Empty (expected; no SQL/dbt) |

**What this means**:
- **Not a bug**: The Cartographer is scoped for **data science and data engineering** codebases (Python + SQL + YAML). Roo-Code-Beamlak is a TypeScript-first VS Code extension — outside that scope.
- **Gap in the tool**: We do not parse TypeScript/JavaScript imports via tree-sitter or build a TS module graph. Adding `tree-sitter` grammars for TS/JS and a TS import extractor would make the Cartographer useful on polyglot repos like this.
- **Takeaway**: The self-audit confirms the Cartographer performs well on **dbt/jaffle_shop** and **Airflow** (Python + SQL + YAML) but produces minimal output on TypeScript-heavy repos until TS support is added.

---

## 7. Final Deliverables Checklist

| Deliverable | Status |
|-------------|--------|
| `src/cli.py` (analyze + query) | Done |
| `src/orchestrator.py` (Surveyor → Hydrologist → Semanticist → Archivist) | Done |
| `src/models/` (Pydantic schemas) | Done |
| `src/analyzers/tree_sitter_analyzer.py` | Done (Python + SQL/YAML helpers) |
| `src/analyzers/sql_lineage.py` | Done (sqlglot + dbt Jinja) |
| `src/analyzers/dag_config_parser.py` | Done |
| `src/analyzers/python_data_flow.py` | Done (pandas/spark/SQLAlchemy) |
| `src/agents/surveyor.py` | Done |
| `src/agents/hydrologist.py` | Done (SQL + YAML + Python lineage) |
| `src/agents/semanticist.py` | Done |
| `src/agents/archivist.py` | Done |
| `src/agents/navigator.py` | Done (4 tools) |
| Incremental mode (`--incremental`) | Done |
| Cartography artifacts (jaffle_shop, airflow) | Done |
| Self-audit (Week 1 Roo-Code-Beamlak) | Done (Section 6) |

