You are the implementer for Task 3 of the SQLite migration plan.

Read the decision record at `docs/decisions/adr-sqlite-migration.md` and the plan at `docs/decisions/plan-sqlite-migration.md`.

Your task is:
### 3. Interactions, favorites, watch progress migration

**Behaviour.** `interactions.py` writes to the `interactions` table (atomic upsert, no race). `users.py` reads/writes the `favorites` table. `watch_store.py` reads/writes the `watch_progress` table. All `threading.Lock` instances are removed. All pandas CSV I/O for these stores is removed.

**Direction.**
- `api/routes/interactions.py::_write_interaction` → use `database.get_db()`, execute `INSERT OR REPLACE INTO interactions`. Remove `pd.read_csv` / `df.to_csv` cycle completely.
- `api/routes/users.py` favorites functions (`_load_favorites`, `set_favorite` -> `_save_favorites` might be removed since we can just UPSERT) → use SQL `INSERT OR REPLACE` / `DELETE` / `SELECT` on `favorites` table. Remove `_fav_lock` and file writes.
- `api/services/watch_store.py` → use SQL operations on `watch_progress`. Remove `_lock`, `_read_all`, `_write_all`. `upsert_progress` uses `INSERT OR REPLACE`. `get_progress` uses `SELECT ... WHERE` with index. `remove_progress` uses `DELETE`.
Keep function signatures consistent to not break caller code.

**Files.** `api/routes/interactions.py`, `api/routes/users.py`, `api/services/watch_store.py`.

**Focused verification.** `PUT /api/watch/progress` with a heartbeat payload succeeds and `SELECT * FROM watch_progress` shows the row. Two concurrent `POST /api/interactions/rating` requests for different movies both persist (verifies no race condition — both rows present).

**Acceptance Rows:**
- Requirement: Interaction write is atomic (no race). Instrument: Two concurrent `POST /api/interactions/rating` for different movies; `SELECT COUNT(*) FROM interactions WHERE user_id=X` returns 2.
- Requirement: Watch progress heartbeat persists. Instrument: `PUT /api/watch/progress` then `SELECT * FROM watch_progress` shows correct ratio.

**Instructions:**
1. Implement the task.
2. Run the focused verification checks and ensure they pass.
3. Commit your changes with a task-scoped commit (e.g. `feat: migrate interactions, favorites, and watch progress to sqlite`).
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
