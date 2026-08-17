"""Entrypoint — runs the pipeline once. Intended to be invoked on a schedule
(e.g. hourly via a routine) so repeated runs are safe: the Supabase dedup
check skips any email already processed."""

from pipeline import run_once

if __name__ == "__main__":
    run_once()
