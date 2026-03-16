import psycopg
from app.config.settings import settings
import asyncio

async def cleanup_litellm_tables():
    conn_str = "postgresql://admin:admin@localhost:5432/smartsales"
    async with await psycopg.AsyncConnection.connect(conn_str) as conn:
        async with conn.cursor() as cur:
            # Get all LiteLLM tables
            await cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename ILIKE 'LiteLLM_%';")
            tables = await cur.fetchall()
            
            if not tables:
                print("No LiteLLM tables found.")
                # Also try to drop the prisma migrations table
                await cur.execute("DROP TABLE IF EXISTS \"_prisma_migrations\" CASCADE;")
                print("Dropped _prisma_migrations if existed.")
                return

            print(f"Found {len(tables)} LiteLLM tables. Dropping...")
            for (table_name,) in tables:
                await cur.execute(f"DROP TABLE IF EXISTS \"{table_name}\" CASCADE;")
                print(f"Dropped {table_name}")
            
            await cur.execute("DROP TABLE IF EXISTS \"_prisma_migrations\" CASCADE;")
            print("Dropped _prisma_migrations")

if __name__ == "__main__":
    asyncio.run(cleanup_litellm_tables())
