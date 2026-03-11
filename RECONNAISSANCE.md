# RECONNAISSANCE (Manual, Ground Truth)

Target repo: `targets/jaffle_shop` (dbt project)

## What is this system?

This repository is a **dbt analytics project**: it defines a small transformation DAG that turns raw seed data into staged models and then into curated marts (e.g. customers, orders).

## The Five FDE Day-One Questions (manual answers)

### 1) What is the primary data ingestion path?

- **Ingestion mechanism**: dbt **seeds** (CSV files loaded into the warehouse as tables).
- **Where**: `seeds/` contains the raw inputs; staging models read from `raw_*` relations.

### 2) What are the 3–5 most critical output datasets/endpoints?

In a dbt project, “critical outputs” are typically the **final mart models**.

- **`customers`**: customer-level mart (joins customers + orders + payments)
- **`orders`**: order-level mart (order facts with payment method breakdown)
- **Staging layer** (enabling dependencies):
  - `stg_customers`
  - `stg_orders`
  - `stg_payments`

### 3) What is the blast radius if the most critical module fails?

- **If `customers` fails**: downstream consumers (dashboards/metrics that depend on customer aggregates) break; upstream staging still may build, but the mart layer is incomplete.
- **If staging fails** (`stg_*`): both marts (`customers`, `orders`) are impacted because they depend on staging models.

### 4) Where is the business logic concentrated vs distributed?

- **Concentrated** in `models/`:
  - staging models: renaming + light cleaning (canonicalization)
  - mart models: joins and metric-friendly shapes
- **Distributed** in templating/macros (Jinja) where `ref()` and config blocks drive dependencies and compilation.

### 5) What has changed most frequently in the last 90 days?

This repo was cloned shallow (`--depth 1`) for speed, so a 90‑day git velocity map can’t be computed reliably from local history.

## Where manual exploration was hardest / where I got lost

- **Templated SQL**: the “real” executed SQL differs from the `.sql` files because dbt compiles Jinja (`ref()`, `source()`, `{% ... %}` blocks). Static parsing must either compile dbt or sanitize templates.
- **What is a “table” vs “model”**: dbt models don’t always explicitly `CREATE TABLE … AS` in SQL; the materialization is configured, so lineage must treat model files as producing relations by convention.
- **Config-driven DAG**: some relationships and metadata live in YAML (e.g. `schema.yml`), which isn’t visible from SQL parsing alone.

