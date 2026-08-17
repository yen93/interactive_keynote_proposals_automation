---
name: run-interactive-keynote-pipeline
description: Run the Interactive Keynote proposal automation pipeline once, on demand. Scans Gmail for matching Interactive Keynote demo-note emails, OCRs the attachment, duplicates the master "Crossing the Ice" template, rewrites the client-specific text, replaces the logo, and sends the Gmail notification, skipping anything already marked processed in Supabase. Use when the user asks to run/trigger/kick off the Interactive Keynote pipeline manually, process new demo-note emails right now, or test the automation locally.
---

# Run Interactive Keynote pipeline

Executes `pipeline.run_once()` against this local checkout, using the local
`.env` and `project_vars.txt`.

## Steps

1. Confirm `.env` exists in the project root. If it's missing, stop and tell
   the user to run `oauth_setup.py` first (see `.env.example` for the
   required vars) — don't attempt to fabricate credentials.
2. Run the pipeline from the project root:
   ```
   python main.py
   ```
3. Read the log output (`pipeline` logger, INFO level). It reports:
   - how many matching emails were found (`Found %d matching email(s)`)
   - one line per processed message: the proposal link, or `needs review`
     with the reason (e.g. unverified logo guess, slide overflow risk), or
     that it was skipped (already processed / no image attachment).
4. Summarize the run for the user: counts found/processed/skipped, any
   `needs_review` or error outcomes with their reasons, and the Slides links
   produced. Don't just paste the raw log.
5. If a `ModuleNotFoundError` occurs, run `pip install -r requirements.txt`
   and retry once.

## Notes

- Safe to re-run any time: Supabase dedup (`interactive_keynote_proposal_logs`)
  skips any email already marked processed, so running this manually won't
  double-send proposals.
- There is no scheduled cloud routine wired up yet for this project (unlike
  Uncharted Ice's `sales-proposals-automation-hourly`) — this skill is
  currently the only way to run it. See
  `AS_BUILT_interactive_keynote_proposal_automation.txt` for how to set one
  up when ready.
