# AuralTrans 2.0

Upload a recording, get a transcript that shows who said what, with word-level timestamps and
synchronized playback. Built from the AuralTrans 2.0 Rebuild Blueprint.

**What works today**

Library, New recording, live Processing, then a workspace with **Transcript**, **Insights**,
**Speakers** and **Ask** tabs, plus exports (SRT, VTT, TXT, Markdown, JSON). Processing runs in a
background worker and resumes from checkpoints after a failure or a crash.

**Insights** (summary, key points, decisions, action items, open questions, chapters) and **Ask**
(questions about one recording) need a language model. Without one configured, those two tabs say
so and everything else still works. See "Language model" below.

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
python -m uv run alembic upgrade head              # 4. create / update the tables

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

## Language model (Insights and Ask)

Any OpenAI-compatible chat endpoint works. Set these in `backend/.env` and restart the API:

```
LLM_BASE_URL=https://api.groq.com/openai/v1      # or http://localhost:11434/v1 for Ollama
LLM_API_KEY=...                                  # not needed for Ollama
LLM_MODEL=openai/gpt-oss-120b                    # a model id your provider serves
```

The Hugging Face router needs paid credits, so it is not a free option. Groq's free tier or a local
Ollama model are.

**Model choice (Groq, checked 8 Oct 2026 against the models a free key can list).** Use
`openai/gpt-oss-120b`: 131k context, and Groq documents strict schema-constrained decoding for the
gpt-oss models (the app sends the JSON schema and falls back to plain JSON mode if a server rejects it).
`openai/gpt-oss-20b` is the faster, weaker alternative. Reasoning effort defaults to `low`
(`LLM_REASONING_EFFORT`) to stay fast and inside rate limits.

**Free-tier limits.** The free tier allows 8,000 tokens per minute on these models, whatever their
context window. The defaults (`LLM_CHUNK_CHARS=12000`, `LLM_CONTEXT_CHARS=20000`) are sized for that,
which means Ask works on recordings up to roughly 25 minutes, and a question about a recording that
size waits about 40 seconds for the rate limit to reset before the next one. Raise both values on a
paid plan or a local model. Insights are generated on demand from the Insights tab (the speech pipeline is
not involved), and Ask is called per question.

**How answers are kept grounded.** The model sees the transcript as `[u12 03:21 Speaker 2] text`
lines and must cite lines by id. The model's JSON is then checked by code, not trusted:

- Output must match the schema; one repair attempt with the errors fed back, then a visible failure.
- Cited ids that do not exist are removed. A statement left with no evidence is dropped.
- A statement whose wording or numbers are not found in its cited lines is shown with a
  "Check source" badge. Chapters must reference real lines and are ordered and de-overlapped.
- **Ask** needs a verbatim quote with each citation, and the quote must appear in the cited line.
  If the model declines, cites nothing valid, or the answer does not match its citations, the app
  answers "I can't find that in this recording" and says why. Abstentions are stored too.
- Insights are flagged stale if transcript text is edited afterwards; every model call is logged
  in `llm_calls`.

These checks are lexical (word and number overlap), not full entailment, so they catch invented
ids, invented numbers and unrelated citations, but a plausible paraphrase of the wrong line can
pass. Ask puts the whole transcript in the prompt (no retrieval yet), so recordings longer than
`LLM_CONTEXT_CHARS` are refused with a clear message.
Each question is answered independently; there is no follow-up memory.

## Settings (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | local Postgres from `docker-compose.yml` | where recordings and transcripts live |
| `STORAGE_PATH` | `./data` | uploaded audio and per-stage checkpoints |
| `HF_TOKEN` | empty | Hugging Face token (read-only is enough) |
| `ASR_MODEL` | `small` | Whisper size: `tiny`, `small`, `medium`, ... |
| `ASR_DEVICE` / `ASR_COMPUTE_TYPE` | `cpu` / `int8` | use `cuda` / `float16` on a GPU |
| `MAX_UPLOAD_MB` | `500` | upload size limit |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | empty | language model for Insights and Ask (off when unset) |
| `LLM_CHUNK_CHARS` / `LLM_CONTEXT_CHARS` | `12000` / `20000` | Insights chunk size / Ask transcript size limit (free-tier sized) |
| `LLM_STRICT_SCHEMA` / `LLM_REASONING_EFFORT` | `auto` / `low` | schema-constrained decoding (`auto`, `on`, `off`); reasoning effort for gpt-oss models |

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
- `backend/src/auraltrans/{llm,insights,ask}/`: model client, insight generation plus validation, grounded Q&A.
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
