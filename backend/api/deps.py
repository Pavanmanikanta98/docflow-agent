from typing import Generator
from backend.core.db import SessionLocal, redis_client

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
    
    


