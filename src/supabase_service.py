"""Dedup/audit tracking against the interactive_keynote_proposal_logs Supabase
table (same project as Uncharted Ice's proposal_demo_notes_email_logs, table
aivitcomiywiysrfwqxt / "MAGTestProject").

Actual columns (see db/001_create_interactive_keynote_proposal_logs.sql):
    id             uuid primary key default gen_random_uuid()
    created_at     timestamptz default now()
    message_id     text unique  -- Gmail message id
    is_processed   boolean default false
    status         text        -- 'success' | 'error' | 'needs_review'
    error_message  text, nullable
    proposal_link  text, nullable
    processed_at   timestamptz, nullable
    client_org     text, nullable
    event_date     text, nullable
    logo_replaced  boolean default false
"""

from datetime import datetime, timezone
from typing import Optional

from supabase import Client, create_client

import config


def get_client() -> Client:
    config.require("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


def is_processed(client: Client, message_id: str) -> bool:
    resp = (
        client.table(config.SUPABASE_LOG_TABLE)
        .select("message_id")
        .eq("message_id", message_id)
        .eq("is_processed", True)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def mark_processed(
    client: Client,
    message_id: str,
    status: str,
    error_message: Optional[str] = None,
    proposal_link: Optional[str] = None,
    client_org: Optional[str] = None,
    event_date: Optional[str] = None,
    logo_replaced: bool = False,
) -> None:
    """Marks the email as processed regardless of success/error outcome so a
    bad email is never retried forever. `status` distinguishes the outcome."""
    client.table(config.SUPABASE_LOG_TABLE).upsert(
        {
            "message_id": message_id,
            "is_processed": True,
            "status": status,
            "error_message": error_message,
            "proposal_link": proposal_link,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "client_org": client_org,
            "event_date": event_date,
            "logo_replaced": logo_replaced,
        },
        on_conflict="message_id",
    ).execute()
