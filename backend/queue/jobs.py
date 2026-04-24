"""ARQ job definitions."""

from arq import create_pool
from arq.connections import RedisSettings

from backend.core.config import settings


async def enqueue_process_document(document_id: int) -> None:
    """ Push a process_document job onto the ARQ Redis queue."""

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await pool.enqueue_job("process_document", document_id)
    await pool.aclose() 