"""Rewrites a duplicated deck's client-specific text via Claude, and swaps
the client logo into any image shape tagged as a logo placeholder."""

import json
import logging

import anthropic

import config

log = logging.getLogger("slides_rewriter")

MODEL = "claude-opus-5"
LOGO_TAG_KEYWORDS = ("logo", "client_logo", "client logo")

REWRITE_TOOL = {
    "name": "rewrite_slide_text",
    "description": "Rewritten text for each editable shape in the Interactive Keynote proposal deck, tailored to the new client.",
    "input_schema": {
        "type": "object",
        "properties": {
            "shapes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "object_id": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["object_id", "new_text"],
                },
            }
        },
        "required": ["shapes"],
    },
}


def _iter_page_elements(presentation: dict):
    for slide in presentation.get("slides", []):
        for element in slide.get("pageElements", []):
            yield element


def shape_text(element: dict) -> str:
    text_elements = element.get("shape", {}).get("text", {}).get("textElements", [])
    return "".join(
        te.get("textRun", {}).get("content", "") for te in text_elements
    ).strip()


def _shape_has_bullets(element: dict) -> bool:
    text_elements = element.get("shape", {}).get("text", {}).get("textElements", [])
    return any("bullet" in te.get("paragraphMarker", {}) for te in text_elements)


def _shape_font_size(element: dict) -> float:
    text_elements = element.get("shape", {}).get("text", {}).get("textElements", [])
    for te in text_elements:
        size = te.get("textRun", {}).get("style", {}).get("fontSize", {}).get("magnitude")
        if size:
            return size
    return None


def extract_text_shapes(presentation: dict) -> list[dict]:
    """Returns [{object_id, text, has_bullets, font_size}, ...] for every
    non-empty text shape. `has_bullets` tracks whether the original template
    paragraph(s) were bullet-formatted, so that formatting can be reapplied
    after the delete/insert rewrite below (which otherwise wipes it).
    `font_size` (may be None) backs the overflow-mitigation font shrink."""
    shapes = []
    for element in _iter_page_elements(presentation):
        if "shape" not in element:
            continue
        text = shape_text(element)
        if text:
            shapes.append({
                "object_id": element["objectId"],
                "text": text,
                "has_bullets": _shape_has_bullets(element),
                "font_size": _shape_font_size(element),
            })
    return shapes


def find_logo_placeholders(presentation: dict) -> list[str]:
    """Returns objectIds of image shapes whose title/description marks them
    as the client-logo placeholder. Depends on the template author having
    tagged the shape's alt text (see inspect_template.py to verify a given
    template actually has one)."""
    logo_ids = []
    for element in _iter_page_elements(presentation):
        if "image" not in element:
            continue
        label = f"{element.get('title', '')} {element.get('description', '')}".lower()
        if any(keyword in label for keyword in LOGO_TAG_KEYWORDS):
            logo_ids.append(element["objectId"])
    return logo_ids


def _build_rewrite_requests(shapes: list[dict], ocr_fields: dict) -> list[dict]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        tools=[REWRITE_TOOL],
        tool_choice={"type": "tool", "name": "rewrite_slide_text"},
        messages=[
            {
                "role": "user",
                "content": (
                    "This is the master Interactive Keynote proposal deck for James "
                    "Castrission's 'Crossing the Ice' keynote — a real, previously-used "
                    "proposal, not a blank template. It still carries exactly one "
                    "leftover mention of whichever client it was last used for (their "
                    "organisation name, inside the speaker-bio paragraph on slide 2). "
                    "The client's logo image and the audience-size/duration info box are "
                    "handled separately outside this text rewrite — ignore them.\n\n"
                    "YOUR ONLY JOB: find the shape(s) that mention a client/organisation "
                    "name (a leftover reference to whoever this deck was last sent to, "
                    "e.g. an org name inside a sentence like '...at your next X event') "
                    "and replace that name with the new client's organisation name from "
                    "the demo notes below. Make only the minimal wording change needed "
                    "for that sentence to still read naturally — do not rephrase, "
                    "shorten, lengthen, or restructure the sentence or paragraph beyond "
                    "swapping the name itself.\n\n"
                    "CRITICAL — every other shape must be returned COMPLETELY UNCHANGED, "
                    "character-for-character identical to its original text: the "
                    "speaker's bio and credentials, the cover title/tagline, the "
                    "'Crossing the Ice' expedition story, the Learning Outcomes list, "
                    "the client testimonials (Medical Meetings / Salesforce / Uniting), "
                    "the Conference Gifts paragraph, the DESIGN/DELIVERY inclusions, the "
                    "investment/pricing figure, and the contact/sign-off block are all "
                    "static offering content that must never be altered, shortened, "
                    "reworded, or have facts invented — this deck's design, images, and "
                    "structure stay exactly as they are; only the one client-name "
                    "mention changes. Do not invent a different price, do not add "
                    "sentences about the event date/venue/audience (there is no slot for "
                    "them in this deck's editable text), and do not touch the cover "
                    "slide's title even though it doesn't name a client.\n\n"
                    "Return every shape passed to you, including the unchanged ones, "
                    "with new_text set to their original text verbatim if no client-name "
                    "mention is present.\n\n"
                    f"Demo notes:\n{json.dumps(ocr_fields, indent=2)}\n\n"
                    f"Template shapes:\n{json.dumps(shapes, indent=2)}"
                ),
            }
        ],
    )

    rewritten = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "rewrite_slide_text":
            rewritten = block.input["shapes"]
    if rewritten is None:
        raise RuntimeError("Claude did not return the expected rewrite_slide_text tool call")

    shapes_by_id = {s["object_id"]: s for s in shapes}
    requests = []
    rewritten_lengths = {}
    for shape in rewritten:
        object_id = shape["object_id"]
        new_text = shape["new_text"]
        original = shapes_by_id.get(object_id, {})
        requests.append({"deleteText": {"objectId": object_id, "textRange": {"type": "ALL"}}})
        if new_text:
            requests.append({"insertText": {"objectId": object_id, "insertionIndex": 0, "text": new_text}})
            if original.get("has_bullets"):
                requests.append({
                    "createParagraphBullets": {
                        "objectId": object_id,
                        "textRange": {"type": "ALL"},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                })
            shrink_request = _build_shrink_request(object_id, original, new_text)
            if shrink_request:
                requests.append(shrink_request)
        rewritten_lengths[object_id] = len(new_text)
    return requests, rewritten_lengths


SHRINK_TRIGGER_RATIO = 1.15
MIN_FONT_SCALE = 0.7


def _build_shrink_request(object_id: str, original: dict, new_text: str) -> dict:
    """The Slides API doesn't support enabling autofit/shrink-to-fit via
    batchUpdate ("Autofit types other than NONE are not supported") — the
    only real lever is directly reducing font size when rewritten text runs
    meaningfully longer than what the shape's box was designed to hold."""
    original_len = len(original.get("text", ""))
    font_size = original.get("font_size")
    if not original_len or not font_size or len(new_text) <= original_len * SHRINK_TRIGGER_RATIO:
        return None
    scale = max(original_len / len(new_text), MIN_FONT_SCALE)
    return {
        "updateTextStyle": {
            "objectId": object_id,
            "textRange": {"type": "ALL"},
            "style": {"fontSize": {"magnitude": round(font_size * scale, 1), "unit": "PT"}},
            "fields": "fontSize",
        }
    }


def _build_logo_requests(logo_ids: list[str], logo_url: str) -> list[dict]:
    return [
        {
            "replaceImage": {
                "imageObjectId": object_id,
                "imageReplaceMethod": "CENTER_INSIDE",
                "url": logo_url,
            }
        }
        for object_id in logo_ids
    ]


FLAG_RATIO = 1.5


def rewrite(slides, file_id: str, ocr_fields: dict, logo_url: str = None) -> dict:
    """Rewrites text (shrinking font size on shapes whose new text runs
    notably longer than the original, since the Slides API has no working
    autofit) and swaps the logo. Returns {text_shapes_updated, logo_replaced,
    overflow_risk_ids} for the pre-send QA check in pipeline.py —
    overflow_risk_ids flags shapes so much longer than the original that a
    font shrink alone may not be enough.

    The text rewrite and the logo swap are deliberately sent as two separate
    batchUpdate calls, not one. logo_url is only ever a guessed, unverified
    domain (see logo_service.py) — the Slides API only discovers it's
    unusable when it tries to fetch it, and batchUpdate is all-or-nothing,
    so a bad logo URL bundled into the same call would silently roll back
    every text rewrite too, leaving the deck duplicated but unedited. The
    logo call is isolated and non-fatal so a bad guess only costs the logo,
    never the text."""
    presentation = slides.presentations().get(presentationId=file_id).execute()

    text_shapes = extract_text_shapes(presentation)
    if text_shapes:
        text_requests, rewritten_lengths = _build_rewrite_requests(text_shapes, ocr_fields)
    else:
        text_requests, rewritten_lengths = [], {}

    if text_requests:
        slides.presentations().batchUpdate(
            presentationId=file_id, body={"requests": text_requests}
        ).execute()

    logo_replaced = False
    if logo_url:
        logo_ids = find_logo_placeholders(presentation)
        if logo_ids:
            try:
                slides.presentations().batchUpdate(
                    presentationId=file_id,
                    body={"requests": _build_logo_requests(logo_ids, logo_url)},
                ).execute()
                logo_replaced = True
            except Exception:
                log.exception(
                    "Guessed logo URL %s could not be applied to %s; leaving placeholder",
                    logo_url, file_id,
                )

    overflow_risk_ids = [
        shape["object_id"] for shape in text_shapes
        if rewritten_lengths.get(shape["object_id"], 0) > len(shape["text"]) * FLAG_RATIO
    ]

    return {
        "text_shapes_updated": len(text_shapes),
        "logo_replaced": logo_replaced,
        "overflow_risk_ids": overflow_risk_ids,
    }
