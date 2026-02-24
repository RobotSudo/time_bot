import asyncpg
from config import DATABASE_URL

db_pool = None


async def setup_database():
    global db_pool

    if not DATABASE_URL:
        print("❌ DATABASE_URL missing")
        return

    db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                utc_offset FLOAT,
                birthday TEXT,
                last_announced INT,
                midnight_checked TEXT
            )
        """)

    print("✅ Database connected")


def get_db():
    return db_pool
