You are the implementer for Task 2 of the SQLite migration plan.

Read the decision record at `docs/decisions/adr-sqlite-migration.md` and the plan at `docs/decisions/plan-sqlite-migration.md`.

Your task is:
### 2. User store migration

**Behaviour.** `user_store.py` functions (`register_user`, `authenticate`, `get_user`, `update_user_genres`) read and write the `users` table instead of `users.json`. Function signatures and return types remain identical. The `threading.Lock` is removed.

**Direction.** Replace `_load_users()` / `_save_users()` with SQL queries using `database.get_db()`.
- `register_user` uses `INSERT` with conflict detection on username (case-insensitive).
- `authenticate` uses `SELECT` by username.
- `get_user` uses `SELECT` by user_id.
- `update_user_genres` uses `UPDATE`. Genres stored as JSON string in a TEXT column.
Return types should match the previous dictionary structure so the rest of the app continues working transparently.

**Files.** `api/services/user_store.py`.

**Focused verification.** Start the API, register a user via `POST /api/auth/register`, then `GET /api/users/{id}/profile` returns the registered username. Verify `data/moviers.db` contains the row: `sqlite3 data/moviers.db "SELECT * FROM users"`.

**Acceptance Row:**
Requirement: User registration persists to SQLite
Instrument: `POST /api/auth/register` then `sqlite3 data/moviers.db "SELECT username FROM users"` shows the user
Counterexample: Implementation that writes to both JSON and DB but reads from JSON, so DB row exists but is never queried

**Instructions:**
1. Implement the task.
2. Run the focused verification command and ensure it passes.
3. Commit your changes with a task-scoped commit (e.g. `feat: migrate user store to sqlite`).
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
