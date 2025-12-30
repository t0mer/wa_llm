"""Database configuration and session management"""

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
import os

# Get database URI from environment
DATABASE_URL = os.getenv("DB_URI")

if not DATABASE_URL:
    raise ValueError("DB_URI environment variable must be set")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False, future=True)


async def init_db():
    """Initialize database (if needed)"""
    # Database tables should already exist from migrations
    pass


async def get_session() -> AsyncSession:
    """Dependency to get database session"""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
