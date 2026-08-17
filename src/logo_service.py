"""Best-guess client logo URL, with no network call of our own.

This mirrors the Uncharted Ice automation's logo_service.py, which learned the
hard way (see that project's update_logs / AS_BUILT doc) that self-validating
a guessed domain (via logo.clearbit.com, then Google's favicon endpoint probed
with a HEAD request, then a DuckDuckGo probe) breaks in a network-restricted
sandbox: each probe host either died or 301-redirected to an unpredictable,
un-allowlistable sharded host.

This version makes no outbound call at all: it just builds a Google favicon
URL from the highest-priority guessed domain and returns it unvalidated. That
URL is only ever fetched by Slides' replaceImage, server-side on Google's own
infrastructure when slides_rewriter.py applies it — never by this process —
so it works regardless of this process's network access. The cost is that
this is now a guess, not a confirmed match: the caller should always surface
it to a human for verification rather than treating a returned URL as a
confirmed hit."""

import re

_SUFFIXES = re.compile(
    r"\b(pty|ltd|limited|llc|inc|incorporated|corp|corporation|company|co|group)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

CANDIDATE_TLDS = [".com.au", ".com", ".co"]


def _guess_domains(client_org: str) -> list[str]:
    name = _SUFFIXES.sub("", client_org.lower())
    slug = _NON_ALNUM.sub("", name)
    if not slug:
        return []
    return [f"{slug}{tld}" for tld in CANDIDATE_TLDS]


def find_logo_url(client_org: str) -> dict:
    """Returns {logo_url, domain} for the highest-priority guessed domain, or
    {logo_url: None, domain: None} if client_org has no alphanumeric
    characters to guess from at all. Never raises. The URL is an unverified
    guess, not a confirmed match — callers should flag it for human review
    rather than treating it as ground truth."""
    domains = _guess_domains(client_org)
    if not domains:
        return {"logo_url": None, "domain": None}
    domain = domains[0]
    return {
        "logo_url": f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
        "domain": domain,
    }
