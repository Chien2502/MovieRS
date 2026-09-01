# Runtime data storage migrates from CSV/JSON files to SQLite

## Context

The MovieRS API currently uses flat files for all runtime state:

- **`users.json`** — User accounts and authentication (SHA-256+salt). Protected by
  `threading.Lock` on writes but reads are unsynchronized; uses direct
  `write_text` without atomic rename.
- **`interactions_log.csv`** — Live feedback buffer (ratings, favorites, watch
  signals). **No locking at all** — concurrent POST requests race on
  read-modify-write via `pd.read_csv` → mutate → `df.to_csv`.
- **`user_favorites.csv`** — Favorite bookmarks. Lock protects writes; reads are
  unsynchronized; entire file rewritten on every toggle.
- **`watch_progress.csv`** — Playback heartbeats (~5 s interval). Lock + atomic
  rename protects writes; reads unsynchronized but atomic rename mitigates torn
  reads. Entire DataFrame read/written on every heartbeat.
- **`movies_processed.csv`** — Movie catalog (read-only at runtime, written by
  offline pipeline). Loaded into memory as pandas DataFrame on startup; multiple
  modules each call `pd.read_csv` independently.

Every write to `interactions_log.csv` (the busiest runtime file) loads the
entire file into a DataFrame, mutates one row, and rewrites the whole file —
O(n) per interaction with no concurrency guard. At current scale (~2 M ratings
in the processed set, plus live interactions) this is a correctness and
performance problem.

## Decision

Replace the five runtime data stores listed above with tables in a single
SQLite database at `data/moviers.db`. Introduce a shared database module
(`api/services/database.py`) that owns the connection, schema creation, and
provides a `get_db()` accessor.

The migration covers **only runtime API state**. Offline ML pipeline artifacts
(`ratings_processed.csv`, `ratings_train.csv`, `ratings_val.csv`,
`ratings_test.csv`, `movies_enriched.csv`, raw data, model files, `item_sim.npz`)
remain as files — they are consumed by pandas/Surprise in batch and do not
benefit from SQLite's transaction semantics.

### Tables

| Table | Replaces | Primary key |
| --- | --- | --- |
| `users` | `users.json` | `user_id INTEGER` |
| `interactions` | `interactions_log.csv` | `(user_id, movie_id)` UNIQUE |
| `favorites` | `user_favorites.csv` | `(user_id, movie_id)` UNIQUE |
| `watch_progress` | `watch_progress.csv` | `(user_id, movie_id)` UNIQUE |
| `movies` | `movies_processed.csv` (runtime reads) | `movie_id INTEGER` |

### Key behaviors

1. **Atomic writes**: SQLite transactions replace file-level locking.
   `interactions` table uses `INSERT OR REPLACE` — no read-modify-write cycle.
2. **Concurrent reads**: SQLite WAL mode allows concurrent readers without
   blocking writers. Removes the unsynchronized-read problem.
3. **O(1) point lookups**: Indexed columns replace full-DataFrame scans for
   user/movie lookups.
4. **`movies` table is populated by the offline pipeline** (`preprocess.py`)
   and read by the API. The API never writes to it. `preprocess.py` gains a
   `--sync-db` step that bulk-inserts from `movies_processed.csv` into
   `data/moviers.db`.
5. **`interactions` table exports to CSV** for the ML pipeline:
   `merge_interactions.py` reads the `interactions` table instead of
   `interactions_log.csv`. A helper `database.export_interactions_csv()` is
   provided for backward compatibility with any script that expects the CSV.
6. **Migration script**: `src/data/migrate_to_sqlite.py` imports existing
   CSV/JSON data into the new database. Idempotent (uses `INSERT OR IGNORE`).
7. **`threading.Lock` removal**: All module-level locks in `user_store.py`,
   `watch_store.py`, and `users.py` are removed — SQLite serializes writes
   internally.
8. **Auto-retrain monitor**: `_count_interaction_rows()` in `main.py` switches
   from CSV line-counting to `SELECT COUNT(*) FROM interactions`.
9. **`recommender.py`**: Reads `movies` table and `interactions` table instead
   of loading CSVs. Movie catalog cached in memory as before (DataFrame built
   from DB query at initialization).

### Wire contract

All REST API request/response schemas remain identical. The Flutter app is
unaffected.

## Alternatives considered

- **PostgreSQL / MariaDB**: Rejected — adds an external service dependency to a
  prototype that must run on a single Windows laptop. SQLite is zero-config and
  ships with Python.
- **Migrate ML pipeline CSVs too**: Rejected — Surprise's `Dataset.load_from_df`
  expects a pandas DataFrame; reading from SQLite and immediately converting to
  DataFrame adds complexity with no correctness or performance gain for batch
  training. The pipeline runs offline and infrequently.
- **Keep CSVs, add file locks**: Addresses the race condition but not the O(n)
  rewrite cost per interaction. Does not provide indexed lookups.

## Consequences

- **Improved**: Concurrent write safety (especially `interactions`), point-query
  latency, disk I/O (no full-file rewrites).
- **Not improved**: ML training speed (still pandas/Surprise on DataFrames),
  model serving latency (still in-memory SVD).
- **Worse**: Debugging requires a SQLite client instead of a text editor;
  mitigated by providing the export helper and keeping `sqlite3` CLI available.
- **Risk**: `preprocess.py --sync-db` must be called after rebuilding
  `movies_processed.csv` to keep the DB in sync. If forgotten, API serves stale
  movie metadata until next sync. Documented in AGENTS.md.

## Non-goals

- ORM (SQLAlchemy, Tortoise). Direct `sqlite3` module is sufficient for the
  five tables and keeps dependencies minimal.
- Async SQLite (aiosqlite). The current API is sync-on-threadpool; adding async
  DB is a separate change.
- Schema migrations framework (Alembic). The schema is small and stable; manual
  `CREATE TABLE IF NOT EXISTS` suffices.
- Dashboard migration. `dashboard/app.py` continues reading CSVs — it is an
  offline analytics tool, not runtime state.

## Deferred

- **Async DB access**: Triggered when profiling shows threadpool contention is a
  bottleneck.
- **Full pipeline migration**: Triggered when the dataset exceeds pandas memory
  limits and SQLite becomes the primary query engine.
