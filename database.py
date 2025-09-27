import os
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
pool: asyncpg.pool.Pool | None = None

# Connexion à PostgreSQL avec pool
async def connect():
    global pool
    print("Connexion à PostgreSQL...", flush=True)
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    print("Connecté à PostgreSQL.", flush=True)

# Création des tables
async def create_tables():
    async with pool.acquire() as conn:
        query = """
        CREATE TABLE IF NOT EXISTS birthdays (
            guild_id BIGINT NOT NULL,
            member_id BIGINT NOT NULL,
            birthday_date DATE NOT NULL,
            PRIMARY KEY (guild_id, member_id)
        );

        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id BIGINT PRIMARY KEY,
            role_id BIGINT,
            channel_id BIGINT,
            birthday_message TEXT
        );
        """
        await conn.execute(query)
        print("Tables créées.", flush=True)

# Ajouter ou mettre à jour un anniversaire
async def add_birthday(guild_id, member_id, birthday_date):
    query = """
    INSERT INTO birthdays (guild_id, member_id, birthday_date)
    VALUES ($1, $2, $3)
    ON CONFLICT (guild_id, member_id) DO UPDATE SET birthday_date = EXCLUDED.birthday_date
    """
    async with pool.acquire() as conn:
        await conn.execute(query, guild_id, member_id, birthday_date)

# Récupérer les paramètres d'un serveur
async def get_guild_settings(guild_id):
    query = "SELECT role_id, channel_id, birthday_message FROM guild_settings WHERE guild_id = $1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, guild_id)
    return dict(row) if row else None

# Mettre à jour les paramètres d'un serveur
async def update_guild_settings(guild_id, role_id, channel_id, message):
    query = """
    INSERT INTO guild_settings (guild_id, role_id, channel_id, birthday_message)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (guild_id) DO UPDATE 
    SET role_id = EXCLUDED.role_id,
        channel_id = EXCLUDED.channel_id,
        birthday_message = EXCLUDED.birthday_message
    """
    async with pool.acquire() as conn:
        await conn.execute(
            query,
            int(guild_id) if guild_id else None,
            int(role_id) if role_id else None,
            int(channel_id) if channel_id else None,
            message
        )

# Récupérer les anniversaires d'une date spécifique
async def get_birthdays_on_date(some_date):
    query = """
    SELECT guild_id, member_id
    FROM birthdays
    WHERE EXTRACT(MONTH FROM birthday_date) = $1
    AND EXTRACT(DAY FROM birthday_date) = $2;
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, some_date.month, some_date.day)
    return [{"guild_id": r["guild_id"], "member_id": r["member_id"]} for r in rows]


async def get_all_guild_birthdays(guild_id):
    query = "SELECT member_id, birthday_date FROM birthdays WHERE guild_id = $1"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, guild_id)
    # On retourne un dict {member_id: birthday_date}
    return {str(r["member_id"]): str(r["birthday_date"]) for r in rows}
