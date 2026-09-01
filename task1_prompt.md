You are the implementer for Task 1 of the SQLite migration plan.

Read the decision record at `docs/decisions/adr-sqlite-migration.md` and the plan at `docs/decisions/plan-sqlite-migration.md`.

Your task is:
### 1. Database module and schema

**Behaviour.** `api/services/database.py` exists. Importing it and calling `get_db()` returns a `sqlite3.Connection` to `data/moviers.db` with WAL mode enabled. On first call, all five tables are created if they do not exist.

**Direction.** Single module-level connection with `check_same_thread=False` (FastAPI runs handlers on a threadpool). `init_db()` called at import time or explicitly. Each table schema matches the columns documented in the ADR. `movies` table has `movie_id INTEGER PRIMARY KEY`; `users` table has `user_id INTEGER PRIMARY KEY`; the other three have composite unique constraints. Add indexes on frequently queried columns (`interactions.user_id`, `watch_progress.user_id`, `favorites.user_id`).

**Files.** `api/services/database.py` (new).

**Focused verification.** `python -c "from api.services.database import get_db; c = get_db(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"` prints all five table names.

**Acceptance Row:**
Requirement: API starts and serves requests with SQLite backend
Instrument: `curl http://localhost:8000/api/health` returns 200
Counterexample: Implementation that imports database.py but never calls `init_db`, so tables don't exist and first request 500s

**Instructions:**
1. Implement the task.
2. Run the focused verification command and ensure it passes.
3. Commit your changes with a task-scoped commit (e.g. `feat: implement database module and schema`).
4. End your turn with a handoff block exactly like this:
```text
Status: DONE | BLOCKED | NEEDS_REPLAN
Harness: agy, default, default, none
Session: [your conversation id]
Baseline: [SHA before your commit]
Changed paths: [paths]
Contract coverage: [what was covered]
Verification: [the command, output, and outcome]
Deviations from plan: [any deviations]
Unresolved findings: [any findings]
Git state: [current HEAD SHA]
END OF HANDOFF
```
