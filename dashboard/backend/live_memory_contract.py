"""Unwired Live memory boundary. No Flask, provider, disk or MemPalace imports.

The authorizer is server-owned and rechecks the browser identity, context,
conversation and current company permission. Backend adapters MUST prefilter
by that scope; this boundary independently verifies every returned revision.
"""
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Protocol


class MemoryDenied(Exception):
    """Invalid request or unavailable authorization; never return exception text."""


@dataclass(frozen=True)
class Scope:
    company_id: int
    session_id: str


@dataclass(frozen=True)
class Ownership:
    company_id: int
    session_id: str | None  # None explicitly means company-shared, not unknown.
    revision: str
    verified: bool = False
    deleted: bool = False


@dataclass(frozen=True)
class Hit:
    document_id: str  # opaque ID, never a source path
    revision: str
    text: str


class ScopedBackend(Protocol):
    def search(self, scope: Scope, query: str, limit: int) -> Iterable[Hit]:
        """Prefilter authorized corpus BEFORE retrieval; never search global legacy."""
        ...


def recall(parameters: Mapping, *, authorize: Callable[[], Scope | None],
           backend: ScopedBackend, ownership: Callable[[str], Ownership | None]) -> dict:
    """Only query comes from the model; identity/context are captured by the server.

    The ownership resolver is authoritative, checks current revisions/tombstones
    and never derives ownership from wing, room or untrusted hit metadata.
    No caching here. Retrieved text remains untrusted reference data.
    """
    if not isinstance(parameters, dict) or set(parameters) != {'query'}:
        raise MemoryDenied()
    query = parameters['query']
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
        raise MemoryDenied()
    scope = authorize()
    if (not isinstance(scope, Scope) or type(scope.company_id) is not int
            or scope.company_id <= 0 or not scope.session_id):
        raise MemoryDenied()
    try:
        # Materialize a bounded number even if a faulty adapter ignores limit.
        hits = []
        for index, hit in enumerate(backend.search(scope, query.strip(), 3)):
            if index == 3:
                break
            owner = ownership(hit.document_id)
            if (owner is None or not owner.verified or owner.deleted
                    or owner.company_id != scope.company_id
                    or owner.session_id not in (None, scope.session_id)
                    or owner.revision != hit.revision):
                continue
            if hit.text.strip():
                hits.append({'reference': hit.document_id, 'revision': hit.revision,
                             'text': hit.text[:600]})
        # Permission revocation or context switch while retrieval was in flight.
        if authorize() != scope:
            raise MemoryDenied()
        return {'status': 'ok' if hits else 'no_authorized_memory',
                'kind': 'untrusted_reference_data', 'memories': hits}
    except MemoryDenied:
        raise
    except Exception:
        # Adapter errors must never become provider context or reveal paths.
        return {'status': 'unavailable', 'kind': 'untrusted_reference_data', 'memories': []}
