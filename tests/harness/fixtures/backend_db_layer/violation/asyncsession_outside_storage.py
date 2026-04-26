"""Q8 violation — AsyncSession leaked beyond storage/."""
from sqlalchemy.ext.asyncio import AsyncSession

async def use(session: AsyncSession) -> None:
    pass
