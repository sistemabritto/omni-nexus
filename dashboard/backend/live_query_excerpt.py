"""Bounded excerpts from an already authorized source; no I/O or URL resolution."""
import re


def matching_excerpt(text, terms, *, limit=600):
    text = text or ''
    matches = [re.search(re.escape(term), text, re.IGNORECASE) for term in terms if term]
    position = min((match.start() for match in matches if match), default=0)
    start = max(0, position - min(120, limit // 4))
    return text[start:start + limit]
