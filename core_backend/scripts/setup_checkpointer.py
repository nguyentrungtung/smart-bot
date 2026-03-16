import asyncio
import os
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.config.settings import settings

async def setup_checkpointer():
    dsn = settings.DATABASE_URL.replace("+psycopg", "")
    print(f"Connecting to: {dsn}")
    async with AsyncConnectionPool(dsn, max_size=5) as pool:
        async with pool.connection() as conn:
            await conn.set_autocommit(True)
            checkpointer = AsyncPostgresSaver(conn)
            try:
                await checkpointer.setup()
                print("Successfully setup checkpointer!")
            except Exception as e:
                print(f"Failed setup: {e}")

if __name__ == "__main__":
    asyncio.run(setup_checkpointer())
