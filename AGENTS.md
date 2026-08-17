# MovieRS agent notes

## Boundaries and entrypoints
- FastAPI backend entrypoint is `api/main.py`; all routers mount under `/api`, `.env` is loaded from the repo root, and `/api/health` checks `models/model_latest.pkl` relative to the current working directory, so run the API from repo root.
- Flutter app entrypoint is `mobile_app/lib/main.dart`; the app uses `mobile_app/lib/config/app_config.dart` for the API URL, not `.env`.
- ML/data scripts live under `src/` and are meant to run from the repo root; they manually inject the repo root into `sys.path`.
- `.agent/` is a generic AG Kit toolkit, not MovieRS project config; ignore it unless explicitly asked.
- Keep Python comments/docstrings and Flutter UI copy in Vietnamese to match the codebase.

## Commands agents usually guess wrong
- Install Python deps: `python -m venv venv` then `pip install -r requirements.txt` (no pyproject/task runner/CI config in this checkout).
- Start API on Windows: `$env:PYTHONIOENCODING="utf-8"; python api/main.py`; docs at `http://localhost:8000/docs`; `API_PORT`/`API_RELOAD` come from `.env`.
- Dashboard: `streamlit run dashboard/app.py` (needs processed CSVs in `data/processed`).
- Flutter: `cd mobile_app`; `flutter pub get`; `flutter analyze`; `flutter test`; `flutter run`.
- Benchmark latency: `python src/pipeline/benchmark.py` requires the API running on `localhost:8000`; add `--e2e` only when you accept writing a temp user + interaction to `interactions_log.csv`.

## Data/model lifecycle
- Current artifacts are built from MovieLens `ml-25m` but `download_movielens.py` defaults to `small`; use `python src/data/download_movielens.py --size 25m` to reproduce the current scale.
- Rebuild order matters: `python src/data/download_movielens.py --size 25m` -> `python src/data/fetch_tmdb.py` -> `python src/data/preprocess.py --max-ratings 2000000 --min-movie-ratings 50` -> `python src/data/split.py` -> `python src/models/train_pipeline.py`.
- `fetch_tmdb.py` needs `TMDB_API_KEY` in root `.env`; it caches to `data/enriched/tmdb_cache.json`, rate-limits 40 requests/10s, and supports `--prioritize-ratings`/`--limit` to spend quota on popular movies first.
- `preprocess.py --movies-only` rebuilds `movies_processed.csv` without resampling ratings; after runtime metadata changes, run `python src/utils/backfill_runtime.py --limit N` then `python src/data/preprocess.py --movies-only`.
- Initial training command is `python src/models/train_pipeline.py`; retrain/hot-reload command is `python src/pipeline/retrain.py`.
- Only `api/main.py` and `fetch_tmdb.py` call `load_dotenv`; direct CLI runs of `train_pipeline.py`/`retrain.py` read OS env vars, not root `.env`, for `SVD_*` and `GATE_TOLERANCE`.
- `data/processed/*.csv`, `data/enriched/*.csv`, `data/enriched/tmdb_cache.json`, `models/*.pkl`, `data/processed/users.json`, and `logs/` are local/generated artifacts; do not rewrite them unless the task is data/model/runtime-state work.
- Retrain always calls `merge_interactions.py` first: feedback from `data/processed/interactions_log.csv` is deduped and moved into TRAIN, not TEST, so new app users become warm after retrain.
- Model promotion is gated by validation RMSE in `models/model_latest.json`; do not compare RMSE across different dataset/preprocess settings without rebasing the gate (`GATE_TOLERANCE` normally stays `0.0`).

## Runtime state and feedback loop
- `RecommenderService` loads `data/processed/movies_processed.csv` and optionally `models/model_latest.pkl`; missing SVD model falls back to popularity recommendations but missing movies CSV is fatal.
- Recommendations are cached in memory for 5 minutes per user; rating/watch-finished calls invalidate that user's cache, and `POST /api/recommendations/reload` clears all by reinitializing the service.
- Explicit ratings and `/interactions/favorite`/`/interactions/watch` mappings write only to `data/processed/interactions_log.csv`; profile favorites use `data/processed/user_favorites.csv`; `/interactions/*` rejects unregistered users with 404.
- User accounts are file-backed in `data/processed/users.json`; IDs start at `200000` to avoid MovieLens `ml-25m` user-ID collisions, passwords are SHA-256+salt prototype storage.
- Watch progress is stored in `data/processed/watch_progress.csv` with atomic write + lock; 5%-95% appears in Continue Watching, and >=95% writes rating `5.0` plus one-step online SVD update.
- Auto-retrain runs inside the API process by default, polls `interactions_log.csv` every 30s, and is controlled by `AUTO_RETRAIN*` env vars; set `AUTO_RETRAIN=0` when you do not want background training.

## Mobile/API quirks
- After every ngrok restart, sync both root `.env` and `mobile_app/lib/config/app_config.dart` with `python src/utils/update_ngrok.py https://xxxx.ngrok-free.dev`; Flutter ignores `.env`.
- Android emulator local fallback is `http://10.0.2.2:8000`; any non-empty `AppConfig.ngrokUrl` overrides it.
- `player_screen.dart` is a simulated player (Timer, 1s real = 1s movie, heartbeat every 5s); replacing it with `video_player` should preserve the heartbeat/resume contract.
- When editing `watch_store.py`, assign DataFrame updates column-by-column; pandas 2.x can throw on `df.loc[mask] = dict`, and FastAPI responses must cast numpy scalars to native Python types.

## Verification expectations
- There is no wired Python pytest suite; use focused scripts plus API smoke checks for backend/ML changes.
- The only Flutter test is `mobile_app/test/widget_test.dart`, a smoke test expecting Splash -> Login after mocked empty SharedPreferences.
