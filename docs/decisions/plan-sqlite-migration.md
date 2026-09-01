# Plan — Runtime CSV/JSON storage migrates to SQLite

Decision record: `docs/decisions/adr-sqlite-migration.md`

**Baseline:** (to be filled after commit)

## Goal

When this is done, the five runtime data stores (`users.json`,
`interactions_log.csv`, `user_favorites.csv`, `watch_progress.csv`,
`movies_processed.csv` for reads) are backed by tables in
`data/moviers.db`. All API endpoints behave identically from the
client's perspective. The `interactions_log.csv` race condition is
eliminated. A migration script converts existing data.

Out of reach: ML pipeline CSV migration, async DB, ORM, dashboard
migration.

## Allowed scope

```
api/services/database.py          (new — shared DB module)
api/services/user_store.py        (rewrite to use SQLite)
api/services/watch_store.py       (rewrite to use SQLite)
api/routes/interactions.py        (switch to DB writes)
api/routes/users.py               (switch to DB reads/writes for favorites)
api/routes/movies.py              (switch to DB reads for movie catalog)
api/routes/watch.py               (minor — remove CSV path constants)
api/services/recommender.py       (switch catalog + interactions reads to DB)
api/main.py                       (switch auto-retrain row counter to DB)
src/data/migrate_to_sqlite.py     (new — migration script)
src/data/preprocess.py            (add --sync-db step)
src/data/merge_interactions.py    (read interactions from DB)
AGENTS.md                         (document --sync-db requirement)
```

Colocated tests: `mobile_app/test/widget_test.dart` (smoke test — will be run
as a closure gate but is not expected to change). No Python test suite exists.

## Forbidden scope

- `data/raw/*.csv` — immutable raw inputs
- `data/enriched/*.csv`, `data/enriched/tmdb_cache.json` — offline enrichment
- `data/processed/ratings_*.csv` — ML pipeline training/eval data
- `models/` — model artifacts
- `src/models/` — model training code
- `src/pipeline/retrain.py` — retrain script (reads train CSVs, not runtime state)
- `dashboard/` — offline analytics
- `mobile_app/lib/` — Flutter app (wire contract unchanged)
- `api/routes/auth.py`, `api/routes/health.py`, `api/routes/recommendations.py` —
  these call into services that change, but the route files themselves need no
  edits (auth calls `user_store` functions whose signatures are preserved).

## Execution envelope

Protected dirty paths: `AGENTS.md` has uncommitted Dely block changes from
earlier in this session. This plan also modifies `AGENTS.md`, so the
implementation will incorporate that pre-existing change.

Branch: `feature/sqlite-migration` based on `Chien2502/feature-rework`.
Remote: `origin` (`https://github.com/Chien2502/MovieRS.git`).
Pull-request target: `Chien2502/feature-rework`.

Resolved phase pins (from `AGENTS.md` managed block):
- `implement`: agy, default model, default effort
- `review`: agy, default model, default effort

Authority: branch, commit owned paths, run gates, push, open/update PR.
May not merge, force-push, stash, reset, clean, or edit outside owned scope.

## Tasks

### 1. Database module and schema

**Behaviour.** `api/services/database.py` exists. Importing it and calling
`get_db()` returns a `sqlite3.Connection` to `data/moviers.db` with WAL mode
enabled. On first call, all five tables are created if they do not exist.

**Direction.** Single module-level connection with `check_same_thread=False`
(FastAPI runs handlers on a threadpool). `init_db()` called at import time or
explicitly. Each table schema matches the columns documented in the ADR.
`movies` table has `movie_id INTEGER PRIMARY KEY`; `users` table has
`user_id INTEGER PRIMARY KEY`; the other three have composite unique
constraints. Add indexes on frequently queried columns (`interactions.user_id`,
`watch_progress.user_id`, `favorites.user_id`).

**Files.** `api/services/database.py` (new).

**Focused verification.** `python -c "from api.services.database import get_db; c = get_db(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"` prints all five table names.

**Document impact.** None yet — documented after all tasks.

### 2. User store migration

**Behaviour.** `user_store.py` functions (`register_user`, `authenticate`,
`get_user`, `update_user_genres`) read and write the `users` table instead of
`users.json`. Function signatures and return types remain identical. The
`threading.Lock` is removed.

**Direction.** Replace `_load_users()` / `_save_users()` with SQL queries.
`register_user` uses `INSERT` with conflict detection on username (case-
insensitive). `authenticate` uses `SELECT` by username. `get_user` uses
`SELECT` by user_id. `update_user_genres` uses `UPDATE`. Genres stored as
JSON string in a TEXT column.

**Files.** `api/services/user_store.py`.

**Focused verification.** Start the API, register a user via
`POST /api/auth/register`, then `GET /api/users/{id}/profile` returns the
registered username. Verify `data/moviers.db` contains the row:
`sqlite3 data/moviers.db "SELECT * FROM users"`.

**Document impact.** AGENTS.md runtime state section.

### 3. Interactions, favorites, watch progress migration

**Behaviour.** `interactions.py` writes to the `interactions` table (atomic
upsert, no race). `users.py` reads/writes the `favorites` table.
`watch_store.py` reads/writes the `watch_progress` table. All `threading.Lock`
instances are removed. All pandas CSV I/O for these stores is removed.

**Direction.**
- `interactions.py::_write_interaction` → `INSERT OR REPLACE INTO interactions`.
  Remove `pd.read_csv` / `df.to_csv` cycle entirely.
- `users.py` favorites functions → SQL `INSERT OR REPLACE` / `DELETE` /
  `SELECT` on `favorites` table. Remove `_fav_lock`.
- `watch_store.py` → SQL operations on `watch_progress`. Remove `_lock`,
  `_read_all`, `_write_all`. `upsert_progress` uses
  `INSERT OR REPLACE`. `get_progress` uses `SELECT ... WHERE` with index.
  `remove_progress` uses `DELETE`.

**Files.** `api/routes/interactions.py`, `api/routes/users.py`,
`api/services/watch_store.py`.

**Focused verification.** `PUT /api/watch/progress` with a heartbeat payload
succeeds and `SELECT * FROM watch_progress` shows the row. Two concurrent
`POST /api/interactions/rating` requests for different movies both persist
(verifies no race condition — both rows present).

**Document impact.** AGENTS.md runtime state section.

### 4. Movies catalog and recommender migration

**Behaviour.** `movies.py` reads the `movies` table from SQLite instead of
`movies_processed.csv`. `recommender.py` loads the movie catalog from the
`movies` table and reads user interactions from the `interactions` table.
`main.py` counts interaction rows via `SELECT COUNT(*)`.

**Direction.**
- `movies.py::get_movies_df()` → query `movies` table into a DataFrame
  (cached in memory as before).
- `recommender.py::initialize()` → load movies_df from `movies` table.
  `_get_recent_activity` → query `interactions` table.
- `main.py::_count_interaction_rows()` → `SELECT COUNT(*) FROM interactions`.
- `watch.py::_enrich()` → use the movies DataFrame from `movies.py` or DB.

**Files.** `api/routes/movies.py`, `api/services/recommender.py`,
`api/main.py`, `api/routes/watch.py`.

**Focused verification.** `GET /api/movies?limit=5` returns 5 movies with all
metadata fields. `GET /api/recommendations/{user_id}` returns recommendations
(cold-start or warm depending on user state).

**Document impact.** None.

### 5. Migration script, preprocess sync, merge_interactions, and docs

**Behaviour.** `src/data/migrate_to_sqlite.py` reads existing CSV/JSON files
and populates `data/moviers.db`. Idempotent. `preprocess.py` gains a
`--sync-db` flag that bulk-inserts `movies_processed.csv` into the `movies`
table. `merge_interactions.py` reads the `interactions` table instead of
`interactions_log.csv`. AGENTS.md is updated with `--sync-db` documentation.

**Direction.**
- `migrate_to_sqlite.py`: For each of the five stores, read the existing
  file, insert rows with `INSERT OR IGNORE`. Print counts.
- `preprocess.py`: After writing `movies_processed.csv`, if `--sync-db` is
  passed, import `database.get_db` and replace the `movies` table contents.
- `merge_interactions.py`: Replace `pd.read_csv(INTERACTIONS_LOG_CSV)` with
  `pd.read_sql("SELECT * FROM interactions", get_db())`.
- AGENTS.md: Add `--sync-db` to rebuild order, note that `data/moviers.db` is
  a generated artifact.

**Files.** `src/data/migrate_to_sqlite.py` (new), `src/data/preprocess.py`,
`src/data/merge_interactions.py`, `AGENTS.md`.

**Focused verification.** With existing CSV data present, run
`python src/data/migrate_to_sqlite.py` and verify
`sqlite3 data/moviers.db "SELECT COUNT(*) FROM users"` matches the JSON entry
count. Run `python src/data/merge_interactions.py` and verify it completes
without error.

**Document impact.** AGENTS.md data/model lifecycle and runtime state sections.

## Acceptance

| Requirement | Instrument | Counterexample | Observed red |
| --- | --- | --- | --- |
| API starts and serves requests with SQLite backend | `curl http://localhost:8000/api/health` returns 200 | Implementation that imports database.py but never calls `init_db`, so tables don't exist and first request 500s | |
| User registration persists to SQLite | `POST /api/auth/register` then `sqlite3 data/moviers.db "SELECT username FROM users"` shows the user | Implementation that writes to both JSON and DB but reads from JSON, so DB row exists but is never queried | |
| Interaction write is atomic (no race) | Two concurrent `POST /api/interactions/rating` for different movies; `SELECT COUNT(*) FROM interactions WHERE user_id=X` returns 2 | Implementation that still uses pandas read-modify-write with `INSERT OR REPLACE` as a second write, losing the first | |
| Watch progress heartbeat persists | `PUT /api/watch/progress` then `SELECT * FROM watch_progress` shows correct ratio | Implementation that computes ratio but writes position=0 due to column name mismatch | |
| Movie catalog served from DB | `GET /api/movies/1` returns movie data after `migrate_to_sqlite.py` but before API restart | Implementation that caches at module import and never queries DB, serving empty results until movies_processed.csv is read | |
| Migration script is idempotent | Run `migrate_to_sqlite.py` twice; `SELECT COUNT(*) FROM users` equals the JSON entry count (not doubled) | Implementation that uses INSERT without OR IGNORE, causing duplicate rows or unique constraint errors | |
| `merge_interactions.py` reads from DB | Run merge after writing an interaction via API; output shows the new interaction count | Implementation that still reads CSV, missing DB-only interactions | |
| Existing API response schemas unchanged | Compare `GET /api/users/{id}/profile` response keys before and after migration | Implementation that returns raw DB tuples instead of dicts, changing JSON keys | |

**Cannot be observed:** Flutter app end-to-end behavior (no Android emulator
in the gate environment). Manual testing on device required separately.

## Stop conditions

- `sqlite3` module missing or broken on the target Python (extremely unlikely
  for CPython but would be `BLOCKED`).
- `data/processed/` directory permissions prevent creating `moviers.db`.
- Existing CSV data is corrupt and cannot be parsed for migration.
- `preprocess.py` changes break the ML pipeline rebuild order (would be
  `NEEDS_REPLAN` to isolate the sync step).

## Closure gates

```
# From repo root:
$env:PYTHONIOENCODING="utf-8"; python -c "from api.services.database import get_db; c = get_db(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"
$env:PYTHONIOENCODING="utf-8"; python src/data/migrate_to_sqlite.py
$env:PYTHONIOENCODING="utf-8"; python -c "import sqlite3; c = sqlite3.connect('data/moviers.db'); print('users:', c.execute('SELECT COUNT(*) FROM users').fetchone()[0]); print('movies:', c.execute('SELECT COUNT(*) FROM movies').fetchone()[0])"
```
