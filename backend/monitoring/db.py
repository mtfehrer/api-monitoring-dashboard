import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://monitor:monitor@localhost:5432/monitoring"
)
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, hide_parameters=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def session() -> AsyncIterator[AsyncSession]:
    async with Session() as db:
        yield db


def utcnow() -> datetime:
    return datetime.now(UTC)
