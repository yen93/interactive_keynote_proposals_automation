"""Orchestrates the Interactive Keynote proposal pipeline for every unprocessed
matching email found on a single run."""

import logging
import mimetypes

import config
from src import drive_service, fathom_service, gmail_service, logo_service, ocr_service, slides_rewriter, supabase_service
from src.google_clients import GoogleClients

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")


def _notify_error(gmail, thread_id: str, message_id: str, subject: str, reason: str) -> None:
    try:
        gmail_service.reply_in_thread(gmail, thread_id, message_id, subject, reason)
    except Exception:
        log.exception("Failed to send error notification for message %s", message_id)


def process_email(clients: GoogleClients, supabase, message_id: str, attachment: dict) -> None:
    gmail, drive, slides = clients.gmail, clients.drive, clients.slides

    # The "started" notification is sent before the pipeline runs so its
    # subject can carry the real client name — the OCR step (below) must
    # complete first to know it.
    image_bytes = gmail_service.download_attachment(gmail, message_id, attachment["attachment_id"])
    ocr_fields = ocr_service.extract_fields(image_bytes, attachment["mime_type"])

    client_org = ocr_fields.get("client_org") or "Unknown Client"
    event_date = ocr_fields.get("event_date") or None
    subject = f"Automation: Interactive Keynote Proposal for {client_org}"

    thread = gmail_service.start_notification_thread(
        gmail,
        subject=subject,
        body_text=(
            f"Automated Interactive Keynote proposal creation for {client_org} has been "
            "started. You will be notified through this same email thread once done."
        ),
    )
    thread_id = thread["thread_id"]
    notification_message_id = thread["message_id"]

    try:
        missing = ocr_service.missing_required_fields(ocr_fields)
        if missing:
            reason = f"Could not process this proposal request — unclear/missing: {', '.join(missing)}."
            _notify_error(gmail, thread_id, notification_message_id, subject, reason)
            supabase_service.mark_processed(
                supabase, message_id, status="error", error_message=reason,
                client_org=client_org, event_date=event_date,
            )
            return

        fathom_notes = fathom_service.find_matching_notes(ocr_fields)
        if fathom_notes:
            ocr_fields["fathom_meeting_notes"] = fathom_notes

        template = drive_service.get_master_template(drive)

        folder = drive_service.create_client_folder(drive, client_org)

        notes_ext = mimetypes.guess_extension(attachment["mime_type"]) or ""
        drive_service.upload_file(
            drive, folder["folder_id"], f"{client_org} Demo Call Notes{notes_ext}",
            image_bytes, attachment["mime_type"],
        )

        duplicate = drive_service.duplicate_template(
            drive, template["id"], folder["folder_id"],
            new_name=f"{client_org} Interactive Keynote Proposal",
        )

        logo = logo_service.find_logo_url(client_org)
        rewrite_result = slides_rewriter.rewrite(
            slides, duplicate["file_id"], ocr_fields, logo_url=logo["logo_url"]
        )

        # Match notes: purely informational, always shown when a match was found —
        # distinct from qa_notes below, which flags things a human should verify.
        match_notes = []
        if fathom_notes:
            match_notes.append("a matching Fathom call recording was found and its notes were used as source material for this proposal")
        if logo["logo_url"] and rewrite_result["logo_replaced"]:
            match_notes.append(f"a client logo match was found (guessed from domain '{logo['domain']}') and applied to the deck")

        # Pre-send QA: never blocks sending, just flags what a human should
        # double-check before this goes out to a real client.
        qa_notes = []
        if not logo["logo_url"]:
            qa_notes.append("no client logo could be guessed automatically — add one manually if needed")
        elif not rewrite_result["logo_replaced"]:
            qa_notes.append("a guessed client logo could not be placed on the slides")
        else:
            qa_notes.append(
                f"client logo was auto-guessed from domain '{logo['domain']}' — "
                f"verify it's actually {client_org}'s logo before sending"
            )
        if rewrite_result["overflow_risk_ids"]:
            qa_notes.append(
                f"{len(rewrite_result['overflow_risk_ids'])} slide text box(es) may overflow their layout"
            )

        ready_message = f"The Interactive Keynote proposal for {client_org} is ready: {duplicate['view_url']}"
        if match_notes:
            ready_message += "\n\nFYI — " + "; ".join(match_notes) + "."
        if qa_notes:
            ready_message += (
                "\n\nNote: please double-check this deck before sharing externally — "
                + "; ".join(qa_notes) + "."
            )

        gmail_service.reply_in_thread(gmail, thread_id, notification_message_id, subject, ready_message)
        supabase_service.mark_processed(
            supabase, message_id,
            status="needs_review" if qa_notes else "success",
            proposal_link=duplicate["view_url"],
            error_message="; ".join(qa_notes) if qa_notes else None,
            client_org=client_org,
            event_date=event_date,
            logo_replaced=rewrite_result["logo_replaced"],
        )
        log.info(
            "Processed %s -> %s%s", message_id, duplicate["view_url"],
            " (needs review: " + "; ".join(qa_notes) + ")" if qa_notes else "",
        )

    except Exception as exc:
        log.exception("Pipeline failed for message %s", message_id)
        _notify_error(
            gmail, thread_id, notification_message_id, subject,
            f"Automation hit an unexpected error and could not finish this proposal: {exc}",
        )
        supabase_service.mark_processed(
            supabase, message_id, status="error", error_message=str(exc),
            client_org=client_org, event_date=event_date,
        )


def run_once() -> None:
    clients = GoogleClients()
    supabase = supabase_service.get_client()

    candidates = gmail_service.search_matching_emails(clients.gmail)
    log.info("Found %d matching email(s)", len(candidates))

    for candidate in candidates:
        message_id = candidate["message_id"]

        if supabase_service.is_processed(supabase, message_id):
            continue

        attachment = gmail_service.get_image_attachment(clients.gmail, message_id)
        if not attachment:
            log.info("Skipping %s: no image attachment found", message_id)
            continue

        process_email(clients, supabase, message_id, attachment)
