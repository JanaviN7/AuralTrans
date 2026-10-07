# AuralTrans 2.0

Upload a recording, get a transcript that shows who said what, with word-level timestamps and
synchronized playback. Built from the AuralTrans 2.0 Rebuild Blueprint.

**What works today**

Library, New recording, live Processing, then a workspace with **Transcript** and **Speakers**
tabs, plus exports (SRT, VTT, TXT, Markdown, JSON). Processing runs in a background worker and
resumes from checkpoints after a failure or a crash. **Insights** and **Ask** appear as tabs but
say plainly that they are not built yet: they need the LLM phase of the blueprint.

Also not built: DOCX export, recording in the browser, live mode, authentication.

## Run it (Windows, one-time setup)

You need Docker, Python 3.11, Node 20+, ffmpeg on `PATH`, and a Hugging Face account that has
accepted the terms of `pyannote/speaker-diarization-community-1` (the speaker model is gated).

```powershell
docker compose up -d postgres                      # 1. database

cd backend
copy ..\.env.example .env                          # 2. then put your HF_TOKEN in backend\.env
python -m pip install uv
python -m uv sync --extra speech                   # 3. installs torch, faster-whisper, pyannote (large)
python -m uv run alembic upgrade head              # 4. create the tables

cd ..\web
npm install                                        # 5. web dependencies
```

Then start three processes (three terminals):

```powershell
# A. API (port 8765; 8000 is often taken by other tools)
cd backend; python -m uv run uvicorn auraltrans.api.app:app --port 8765

# B. Worker: does the actual transcription. ASR_MODEL=tiny is quick for trying things out.
cd backend; $env:ASR_MODEL="tiny"; python -m uv run python -m auraltrans.worker

# C. Web app
cd web; npm run dev            # open http://localhost:5173
```

The first run downloads the Whisper and pyannote models. After that: **New recording**, pick an
audio or video file, watch it process, and the transcript opens when it is done.

**Speed on a CPU.** Measured on this project's Windows laptop (no GPU): transcription with Whisper
`small` runs at about 0.3x real time and speaker detection at about 1.9x real time, so a 10 minute
recording takes roughly 20 minutes. Use short clips to try it, or run the worker on a GPU machine
(set `ASR_DEVICE=cuda`, `ASR_COMPUTE_TYPE=float16`).

## Settings (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | local Postgres from `docker-compose.yml` | where recordings and transcripts live |
| `STORAGE_PATH` | `./data` | uploaded audio and per-stage checkpoints |
| `HF_TOKEN` | empty | Hugging Face token (read-only is enough) |
| `ASR_MODEL` | `small` | Whisper size: `tiny`, `small`, `medium`, ... |
| `ASR_DEVICE` / `ASR_COMPUTE_TYPE` | `cpu` / `int8` | use `cuda` / `float16` on a GPU |
| `MAX_UPLOAD_MB` | `500` | upload size limit |

## How it fits together

```
browser ── /api ──> FastAPI (never loads models)
                       │  queue + progress + transcripts
                       ▼
                   PostgreSQL <── worker (models loaded once)
                       │              audio_16k -> asr -> diarize -> align -> analytics
                  local storage       each stage writes a checkpoint; retries skip finished stages
```

- `backend/src/auraltrans/speech/`: the speech core (Whisper, pyannote, word-to-speaker alignment).
- `backend/src/auraltrans/pipeline/`, `worker/`: checkpointed stages and the Postgres-queue worker.
- `backend/src/auraltrans/api/`: REST endpoints and the SSE progress stream.
- `web/`: React + TypeScript. Types are generated from the API schema:
  `cd backend; python -m uv run python -m auraltrans.api.dump_openapi > ../web/openapi.json`, then
  `cd ../web; npm run gen:api`.
- `eval/`: the evaluation harness (WER, DER, cpWER, alignment ablation). See `eval/README.md`.

## Tests

```powershell
cd backend
python -m uv run --extra speech --extra eval pytest      # needs Postgres running; DB tests skip without it
cd ..\web
npm run build                                            # typecheck + production build
```

Database tests use a throwaway database per test, so your data is never touched.
