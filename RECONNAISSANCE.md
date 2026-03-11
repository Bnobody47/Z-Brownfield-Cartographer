# RECONNAISSANCE (Manual, Ground Truth)

Target repo: `targets/jaffle_shop` (dbt project cloned from `dbt-labs/jaffle_shop`)

## What is this system?

This repository is a **dbt analytics project**: it defines a small transformation DAG that turns raw seed data into staged models and then into curated marts (e.g. customers, orders).

## The Five FDE Day-One Questions (manual answers)

### 1) What is the primary data ingestion path?

- **Ingestion mechanism**: dbt **seeds** (CSV files loaded into the warehouse as tables).
- **Where in the repo**:
  - Raw seed data lives under `seeds/`:
    - `seeds/raw_customers.csv`
    - `seeds/raw_orders.csv`
    - `seeds/raw_payments.csv`
  - These are exposed as warehouse tables (often `raw_customers`, `raw_orders`, `raw_payments`) and then read by staging models:
    - `models/staging/stg_customers.sql` (via `{{ ref('raw_customers') }}`)
    - `models/staging/stg_orders.sql` (via `{{ ref('raw_orders') }}`)
    - `models/staging/stg_payments.sql` (via `{{ ref('raw_payments') }}`)

### 2) What are the 3–5 most critical output datasets/endpoints?

In a dbt project, “critical outputs” are typically the **final mart models**.

- **`customers`** (`models/customers.sql`): customer-level mart (joins customers + orders + payments).
- **`orders`** (`models/orders.sql`): order-level mart (order facts with payment method breakdown).
- **Staging layer** (enabling dependencies):
  - `stg_customers` (`models/staging/stg_customers.sql`)
  - `stg_orders` (`models/staging/stg_orders.sql`)
  - `stg_payments` (`models/staging/stg_payments.sql`)

### 3) What is the blast radius if the most critical module fails?

- **If `customers` fails**:
  - Defined in `models/customers.sql`. Anything depending on the `customers` relation (dashboards, downstream jobs, exports) will fail or see stale data.
  - Upstream staging models in `models/staging/` (`stg_customers`, `stg_orders`, `stg_payments`) can still build, but the mart layer is incomplete.
- **If staging fails** (`stg_*`):
  - `models/customers.sql` consumes `stg_customers`, `stg_orders`, `stg_payments`.
  - `models/orders.sql` consumes `stg_orders`, `stg_payments`.
  - So a failure in any `stg_*` model breaks both `customers` and `orders`, which is visible in the repo as `{{ ref('stg_customers') }}`, `{{ ref('stg_orders') }}`, and `{{ ref('stg_payments') }}` references in those files.

### 4) Where is the business logic concentrated vs distributed?

- **Concentrated** in `models/`:
  - **Staging models** (`models/staging/*.sql`): perform renaming, type casting, basic cleaning (canonicalization) of the seeded raw tables.
  - **Mart models** (`models/customers.sql`, `models/orders.sql`): contain the join logic and business-friendly shapes (e.g., customer-level and order-level views).
- **Distributed** in templating/macros (Jinja):
  - `ref()` calls in `models/*.sql` define dependencies (e.g. `{{ ref('stg_orders') }}` in `models/orders.sql`).
  - Additional configuration logic appears in `dbt_project.yml` and `models/schema.yml` (tests, docs, and materialization settings), which influence how these models are built and validated.

### 5) What has changed most frequently in the last 90 days?

Locally I cloned this repo with `--depth 1` for speed, so I **cannot reliably compute** a 90‑day git velocity map from history on disk.

If I had full history, I would run:

- `git -C targets/jaffle_shop log --since=90.days --name-only --pretty=format:` and aggregate counts by path.

Based on how the repo is structured (and common dbt practice), I would expect the most frequently changed areas to be:

- `models/staging/*.sql` and `models/*.sql` (iterating on business logic and metrics).
- `models/schema.yml` (tests and documentation evolving with business logic).
- Possibly `dbt_project.yml` (changing materializations, schemas, and locations).

## Where manual exploration was hardest / where I got lost

- **Templated SQL**: the “real” executed SQL differs from the `.sql` files because dbt compiles Jinja (`ref()`, `source()`, `{% ... %}` blocks). Static parsing must either compile dbt or sanitize templates.
- **What is a “table” vs “model”**: dbt models don’t always explicitly `CREATE TABLE … AS` in SQL; the materialization is configured, so lineage must treat model files as producing relations by convention.
- **Config-driven DAG**: some relationships and metadata live in YAML (e.g. `schema.yml`), which isn’t visible from SQL parsing alone.

