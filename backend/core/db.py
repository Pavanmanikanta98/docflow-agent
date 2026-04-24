import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.core.config import settings


# -- postgres Connection --

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

redis_client = redis.from_url(settings.redis_url)


