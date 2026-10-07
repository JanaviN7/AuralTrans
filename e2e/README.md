# End-to-end browser test

Drives the **real** stack in a real browser: upload, background processing (Whisper + pyannote),
live progress, speaker-labelled transcript, synchronized playback, Insights, cited Ask,
abstention, citation seek, reload/history, stale detection, delete. About 30 checks.

It calls your **real language model** (the `LLM_*` settings in `backend/.env`), so it uses a few
thousand tokens per run. Assertions are structural and are checked against the API's own
transcript (every citation resolves, every quote occurs in its utterance, an unsupported
question abstains), never against exact model wording.

## Run

Prerequisites: the README's one-time setup (Postgres up, `alembic upgrade head`, `npm install` in
`web/`, `LLM_*` and `HF_TOKEN` in `backend/.env`) and nothing already listening on ports 8765/5173.

```bash
cd e2e
npm install
npx playwright install chromium      # or set E2E_BROWSER=msedge / chrome to use an installed browser
npm test
```

The script starts the API, the worker (Whisper `tiny` for speed) and Vite itself, and stops them
afterwards. It uploads `fixtures/conversation.wav` (a short synthetic two-voice conversation),
and deletes the recording at the end. Logs and screenshots go to `e2e/out/` (git-ignored).

| Variable | Default | Meaning |
|---|---|---|
| `E2E_BROWSER` | bundled Chromium | installed browser channel, e.g. `msedge`, `chrome` |
| `E2E_SHOTS` | `e2e/out/shots` | where screenshots are written |
| `ASR_MODEL` | `tiny` | Whisper model the worker loads |
| `PYTHON` | `python` | interpreter used for `python -m uv run` |

On Windows run it from PowerShell (ffmpeg must be on `PATH`). Exit code is non-zero if any check fails.
