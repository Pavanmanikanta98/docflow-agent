"""ARQ job definitions."""

from arq import create_pool
from arq.connections import RedisSettings

from backend.core.config import settings


async def enqueue_process_document(document_id: int) -> None:
    """ Push a process_document job onto the ARQ Redis queue."""

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await pool.enqueue_job("process_document", document_id)
    await pool.aclose()


async def enqueue_process_document_chunk(document_id: int, chunk_index: int) -> None:
    """ADR 006 — push one chunk of a chunked document onto the queue.

    Each chunk is its own job, enqueued only after the previous one
    finishes, so it always lands at the back of the shared queue — a small
    document queued behind a big one's chunks gets its turn in between
    (round-robin fairness), rather than the big document holding a single
    job slot for its whole, possibly very long, processing time.
    """

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await pool.enqueue_job("process_document_chunk", document_id, chunk_index)
    await pool.aclose()
