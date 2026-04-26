"""Q8 compliant — gateway file may import SQLModel + AsyncSession.

Pretend-path: backend/src/storage/gateway.py
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

async def fetch(session: AsyncSession) -> None:
    await session.execute(select(SQLModel))
