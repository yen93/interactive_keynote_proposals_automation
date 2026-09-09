# CLAUDE.md — Interactive Keynote Proposal Automation

Guidance for a future Claude session working in this repo. Keep it grounded;
update it when architecture, commands, or gotchas actually change.

## What this is
A Gmail-triggered Python pipeline that generates a customized Google Slides
proposal for James Castrission's "Crossing the Ice" Interactive Keynote from
emailed demo-call notes. Entry point: `main.py` -> `pipeline.run_once()`.
Reruns are safe/idempotent (Supabase dedup).

## Run / test
- Install: `pip install -r requirements.txt`
- Run once: `python main.py` (searches Gmail via `GMAIL_TRIGGER_QUERY`, processes
  each unprocessed match; may find nothing — that's fine).
- One-time Google auth: `python oauth_setup.py` (mints the refresh token into
  `.env`). Needed when `GOOGLE_REFRESH_TOKEN` expires (see gotchas).
- Test the OCR path in isolation without the full pipeline: call
  `src.ocr_service.extract_fields(<bytes>, "application/pdf")` on
  `test_demo_notes_for_interactive_keynote.pdf` and inspect the returned dict.

## LLM provider — OpenAI only
All three LLM call sites use the **OpenAI API, model `gpt-4o`**, via
`chat.completions` with **forced function calling** (`tool_choice` pins one
function; result read from
`response.choices[0].message.tool_calls[0].function.arguments` + `json.loads`):
- `src/ocr_service.py` — vision OCR (`extract_keynote_demo_notes`). Images go in
  as a base64 `image_url`; PDFs as a base64 `{"type":"file", ...}` part.
- `src/slides_rewriter.py` — slide-text rewrite (`rewrite_slide_text`).
- `src/fathom_service.py` — Fathom meeting match (`match_meeting`).

The project was migrated off Anthropic (`claude-opus-5`) on 2026-09-09. **Do not
reintroduce the `anthropic` SDK or `ANTHROPIC_API_KEY`** — the requirement is
that this pipeline never uses the Anthropic API. `requirements.txt` pins
`openai>=1.40.0`.

The API key loads via `config.OPENAI_API_KEY`, which reads `OPENAI_API_KEY` from
the environment (`.env`) and, if empty, falls back to reading
`openai_api_key.txt` at the repo root. Both files are gitignored — never commit
either.

## Deployment: the cloud routine is the real target
This runs as a **Claude Code cloud routine**
(`interactive-keynote-proposals-automation-hourly`, `trig_01KSh5tdtUWA1BXND9eNgR4R`),
not a local cron job. On each run it **clones the GitHub repo fresh (default
branch `main`)**, writes its own `.env` from credentials **embedded in the
routine's stored prompt**, pip installs, and runs `python main.py`. Therefore:
- A code change only reaches live runs after it is **committed and pushed to
  `main`** on `yen93/interactive_keynote_proposals_automation`.
- Credential/key changes must ALSO be made in the **routine's embedded prompt**
  (edit via `RemoteTrigger action:update` or the routine's page /
  `/schedule` skill) — editing repo `.env` alone does nothing for cloud runs.
- The sandbox **egress allowlist** for the routine's environment
  (`env_01DYHNjMesGeuq9ABo7W6m6f`) must include `api.openai.com`, or cloud runs
  fail with a 403 (already added as of 2026-09-09).

Current routine state: `enabled=true` but **no cron set** (`cron_expression`
empty), so it does not auto-fire despite the "-hourly" name; it runs only when
triggered manually. Leave enable/schedule state alone unless asked to change it.

## Gotchas
- `GOOGLE_REFRESH_TOKEN` (unverified/testing-mode OAuth client) can expire after
  ~7 days. Failures citing a revoked/expired token are fixed by re-running
  `oauth_setup.py` and updating the routine's stored `.env` token — not a code
  bug. This Google credential is shared with the sibling Uncharted Ice routine.
- `mark_processed` sets `is_processed=true` even on error, so failed emails do
  NOT auto-retry — clear the Supabase row to reprocess.
- Logo URLs from `logo_service.py` are unverified domain guesses; the logo swap
  is deliberately a separate, non-fatal Slides `batchUpdate` (all-or-nothing),
  so a bad logo never rolls back the text rewrite. Results are flagged for human
  review (`status="needs_review"`).
- The routine's own auth token (an `sk-ant-oat01-...` hint) is the Claude Code
  orchestrator's login, not the pipeline's LLM key — unrelated to provider choice.
- Never modify anything outside this project folder; the sibling
  `keynote_proposal_maker` is reference-only.

## Secrets
Live secrets live in `.env` and `openai_api_key.txt` (both gitignored). Also
gitignored: `.google_token.json`, `*client_secret*.json`, and the real client
demo-notes PDF. Never commit secrets or write them into tracked files
(chat-history exports, as_built.txt, etc. must use `[REDACTED_*]`).
