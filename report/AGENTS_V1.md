# MovieRS agent notes

## Boundaries and entrypoints
- FastAPI backend entrypoint is `api/main.py`; all routers mount under `/api`, `.env` is loaded from the repo root. `/api/health` initializes the recommendation snapshot and reports actual model/catalog readiness. Run the API from repo root.
- Flutter app entrypoint is `mobile_app/lib/main.dart`; the app uses `mobile_app/lib/config/app_config.dart` for the API URL, not `.env`.
- ML/data scripts live under `src/` and are meant to run from the repo root; they manually inject the repo root into `sys.path`.
- `.agent/` is a generic AG Kit toolkit, not MovieRS project config; ignore it unless explicitly asked.
- Keep Python comments/docstrings and Flutter UI copy in Vietnamese to match the codebase.
- Supabase PostgreSQL scaffolding lives in `api/database.py`, `supabase/schema.sql`, and `src/data/init_database.py`. `DATABASE_URL` is optional; root `.env` stays untracked. Existing runtime stores remain JSON/CSV until explicitly migrated. Never treat MCP OAuth or Supabase API keys as PostgreSQL credentials.

## Commands agents usually guess wrong
- Install Python deps: `python -m venv venv` then `pip install -r requirements.txt` (no pyproject/task runner/CI config in this checkout).
- Start API on Windows: `$env:PYTHONIOENCODING="utf-8"; python api/main.py`; docs at `http://localhost:8000/docs`; `API_PORT`/`API_RELOAD` come from `.env`.
- Dashboard: `streamlit run dashboard/app.py` (needs processed CSVs in `data/processed`).
- Flutter: `cd mobile_app`; `flutter pub get`; `flutter analyze`; `flutter test`; `flutter run`.
- Benchmark latency: `python src/pipeline/benchmark.py` requires the API running on `localhost:8000`; add `--e2e` only when you accept writing a temp user + interaction to `interactions_log.csv`.
- Read-only HTTP smoke: `python src/pipeline/verify_runtime.py` starts a temporary localhost API with auto-retrain disabled and verifies input artifacts remain unchanged by SHA-256.
- Database connectivity only: `python src/data/init_database.py --check`; bootstrap tables only after credentials are provided: `python src/data/init_database.py`. These commands load root `.env`; `/api/health/database` never initializes tables.

## Data/model lifecycle
- Current artifacts are built from MovieLens `ml-25m` but `download_movielens.py` defaults to `small`; use `python src/data/download_movielens.py --size 25m` to reproduce the current scale.
- Rebuild order matters: `python src/data/download_movielens.py --size 25m` -> `python src/data/fetch_tmdb.py` -> `python src/data/preprocess.py --max-ratings 2000000 --min-movie-ratings 50` -> `python src/data/split.py` -> `python src/models/train_pipeline.py`.
- `fetch_tmdb.py` needs `TMDB_API_KEY` in root `.env`; it caches to `data/enriched/tmdb_cache.json`, rate-limits 40 requests/10s, and supports `--prioritize-ratings`/`--limit` to spend quota on popular movies first.
- `preprocess.py --movies-only` rebuilds `movies_processed.csv` without resampling ratings; after runtime metadata changes, run `python src/utils/backfill_runtime.py --limit N` then `python src/data/preprocess.py --movies-only`.
- Academic experiment command is `python src/models/train_pipeline.py --seeds 42 43 44 --ranking-users 200`; it derives immutable temporal splits from `ratings_processed.csv`, writes `report/experiments/`, and does not deploy a model. Initial serving-model training and retrain/hot-reload use `python src/pipeline/retrain.py`.
- `api/main.py`, `fetch_tmdb.py`, and `src/data/init_database.py` call `load_dotenv`; direct CLI runs of `train_pipeline.py`/`retrain.py` read OS env vars, not root `.env`, for `SVD_*` and `GATE_TOLERANCE`.
- `data/processed/*.csv`, `data/enriched/*.csv`, `data/enriched/tmdb_cache.json`, `models/*.pkl`, `data/processed/users.json`, and `logs/` are local/generated artifacts; do not rewrite them unless the task is data/model/runtime-state work.
- Retrain uses `merge_interactions.build_runtime_data()`: fixed historical splits are derived from processed data; app feedback (user ID >=200000) joins runtime TRAIN only. Existing validation/test CSVs are not repartitioned by feedback. Academic evaluation never reads runtime TRAIN/logs.
- Model promotion re-evaluates both incumbent and candidate on the exact same current historical validation and records its SHA-256. Missing/nonfinite metrics fail closed; `GATE_TOLERANCE` normally stays `0.0`. Do not relax it to compare stale historical metadata.

## Runtime state and feedback loop
- `RecommenderService` loads `data/processed/movies_processed.csv` and optionally `models/model_latest.pkl`; missing SVD model falls back to popularity recommendations but missing movies CSV is fatal.
- Recommendations are cached in memory for 5 minutes per user and exploration mode; preference/feedback writes invalidate that user's cache. `explore=true` enables MMR; default ranking leaves it off based on validation evidence. Reload builds a new snapshot before replacing the previous one.
- Feedback uses `api/services/feedback_store.py`: explicit/legacy_unknown > favorite > watch_complete. Repeated identical writes do not repeat online SGD; implicit proxies cannot overwrite explicit ratings. Rating history includes explicit only; old records without source remain legacy_unknown.
- `POST /users/{id}/favorites` updates both the saved list and favorite feedback. `/interactions/favorite` is a compatibility alias. Removing a favorite withdraws that proxy rather than writing a negative rating. Partial watch does not map to a dislike. Unregistered users and nonexistent movies are rejected for writes.
- User accounts are file-backed in `data/processed/users.json`; IDs start at `200000` to avoid MovieLens `ml-25m` user-ID collisions, passwords are SHA-256+salt prototype storage.
- Watch progress is stored in `data/processed/watch_progress.csv` with atomic write + lock; 5%-95% appears in Continue Watching, and >=95% writes a `watch_complete` proxy of `4.0` if a stronger source is absent. It is not an explicit star rating.
- Auto-retrain runs inside the API process by default, polls `interactions_log.csv` every 30s, and is controlled by `AUTO_RETRAIN*` env vars; set `AUTO_RETRAIN=0` when you do not want background training.

## Mobile/API quirks
- After every ngrok restart, sync both root `.env` and `mobile_app/lib/config/app_config.dart` with `python src/utils/update_ngrok.py https://xxxx.ngrok-free.dev`; Flutter ignores `.env`.
- Android emulator local fallback is `http://10.0.2.2:8000`; web/desktop use `http://127.0.0.1:8000`. `--dart-define=API_URL=...` overrides `AppConfig.ngrokUrl`, which otherwise overrides local fallback. Default ngrokUrl is empty.
- `player_screen.dart` is a simulated player (Timer, 1s real = 1s movie, heartbeat every 5s); replacing it with `video_player` should preserve the heartbeat/resume contract.
- When editing `watch_store.py`, assign DataFrame updates column-by-column; pandas 2.x can throw on `df.loc[mask] = dict`, and FastAPI responses must cast numpy scalars to native Python types.

## Verification expectations
- Run `python -m pytest -q` for focused protocol, feedback/API and retrain regression tests. They use temporary files and must not mutate real accounts/data/models.
- Run `flutter analyze` and `flutter test` from `mobile_app`. The widget suite covers Splash -> Login, recommendation/error states, failed ratings, single-request favorites and player resume/save-failure behavior. `flutter build web` verifies the web target; device playback remains simulated.
- Do not reintroduce hardcoded benchmark tables in the dashboard or infer onboarding preferences from TEST labels. Results and confidence intervals are tied to their recorded dataset/protocol/seed.
