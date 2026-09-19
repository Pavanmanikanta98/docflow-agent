from typing import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.db import SessionLocal, redis_client
from backend.models.db import Document

# Shorter than this and it is not one of our session ids, which are
# "ses_" plus 16 hex characters (frontend/lib/api.ts).
MIN_SESSION_ID_LENGTH = 8


def get_db()-> Generator:
    """ Yields a database session and  safely closes it
    after the request finishes. """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_redis()-> Generator:
    """ Yields a active redis client. """

    return redis_client


def get_tenant_id(request: Request) -> str:
    """The caller's identity, taken from the X-Session-Id header.

    The demo has no login, so the browser session doubles as the tenant. The
    header is the only source — a caller cannot name a tenant in the query
    string or the upload form and read somebody else's documents.

    The rate limiter reads the same header but falls back to "anonymous"
    (middleware.py); that is deliberate. A missing header there costs the
    caller a shared quota, while here it would hand them someone's documents,
    so this rejects instead of guessing.
    """
    session_id = request.headers.get("x-session-id", "").strip()
    if len(session_id) < MIN_SESSION_ID_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="Missing or malformed X-Session-Id header.",
        )
    return session_id


def get_owned_document(
    document_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Document:
    """The document at this id, but only if it belongs to the caller.

    Every route that reads or changes a single document depends on this rather
    than looking the row up by id, so the ownership check cannot be left out of
    a new route by accident.

    A document owned by somebody else is reported as 404, not 403: a 403 would
    confirm that the id exists.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == tenant_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
