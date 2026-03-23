from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()


def _build_url() -> str:
    """
    Normalise the DATABASE_URL to use the asyncpg driver.
    Zeabur PostgreSQL exposes:  postgres://user:pass@host:5432/db
    SQLAlchemy needs:           postgresql+asyncpg://user:pass@host:5432/db
    """
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url or "postgresql+asyncpg://localhost/lazydog"


DATABASE_URL = _build_url()

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        from backend.models import Job, AgentLog, Post  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
