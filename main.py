import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, UTC
import asyncpg
import os

# =============================
# CONFIG
# =============================
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

BIRTHDAY_ROLE_NAME = "Birthday guy"
BIRTHDAY_CHANNEL_ID = 1468164390460199055

# =============================
# INTENTS
# =============================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
db = None

# =============================
# DATABASE SETUP
# =============================
async def setup_database():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)

    async with db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                utc_offset FLOAT,
                birthday TEXT,
                last_announced INT,
                midnight_checked TEXT
            )
        """)

# =============================
# READY
# =============================
@bot.event
async def on_ready():
    await setup_database()
    await bot.tree.sync()
    if not birthday_loop.is_running():
        birthday_loop.start()
    print(f"✅ Logged in as {bot.user}")

# =============================
# /mytime
# =============================
@bot.tree.command(name="mytime", description="Set your local time")
@app_commands.describe(time_str="Example: 1:27 am or 13:27")
async def mytime(interaction: discord.Interaction, time_str: str):
    try:
        now_utc = datetime.now(UTC)
        time_str = time_str.strip().lower()

        if "am" in time_str or "pm" in time_str:
            local_time = datetime.strptime(time_str, "%I:%M %p")
        else:
            local_time = datetime.strptime(time_str, "%H:%M")

        local_time = local_time.replace(
            year=now_utc.year,
            month=now_utc.month,
            day=now_utc.day,
            tzinfo=UTC
        )

        diff = local_time - now_utc
        offset = round((diff.total_seconds() / 3600) * 2) / 2

        if offset > 14:
            offset -= 24
        if offset < -12:
            offset += 24

        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, offset)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE SET offset = EXCLUDED.offset
            """, interaction.user.id, offset)

        await interaction.response.send_message(
            f"✅ Timezone saved (UTC{offset:+})",
            ephemeral=True
        )

    except:
        await interaction.response.send_message(
            "❌ Invalid format. Example: 1:27 am or 13:27",
            ephemeral=True
        )

# =============================
# /birthday
# =============================
@bot.tree.command(name="birthday", description="Set your birthday (MM-DD)")
@app_commands.describe(date="Example: 05-14")
async def birthday(interaction: discord.Interaction, date: str):
    try:
        month, day = map(int, date.split("-"))
        datetime(2000, month, day)

        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, birthday, last_announced)
                VALUES ($1, $2, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET birthday = EXCLUDED.birthday,
                              last_announced = NULL
            """, interaction.user.id, f"{month:02d}-{day:02d}")

        await interaction.response.send_message(
            f"🎉 Birthday saved as {month:02d}-{day:02d}",
            ephemeral=True
        )

    except:
        await interaction.response.send_message(
            "❌ Invalid format. Use MM-DD",
            ephemeral=True
        )

# =============================
# BIRTHDAY LOOP
# =============================
@tasks.loop(minutes=1)
async def birthday_loop():
    utc_now = datetime.now(UTC)

    async with db.acquire() as conn:
        users = await conn.fetch("SELECT * FROM users")

    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=BIRTHDAY_ROLE_NAME)
        channel = guild.get_channel(BIRTHDAY_CHANNEL_ID)

        for row in users:

            if not row["birthday"] or row["offset"] is None:
                continue

            member = guild.get_member(row["user_id"])
            if not member:
                continue

            local_time = utc_now + timedelta(hours=row["offset"])

            # Only run at user's midnight
            if local_time.hour == 0 and local_time.minute == 0:

                today_key = local_time.strftime("%Y-%m-%d")

                # Prevent duplicate trigger
                if row["midnight_checked"] == today_key:
                    continue

                async with db.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET midnight_checked = $1 WHERE user_id = $2",
                        today_key,
                        row["user_id"]
                    )

                today = local_time.strftime("%m-%d")
                current_year = local_time.year
                birthday_value = row["birthday"]

                # Handle Feb 29
                if birthday_value == "02-29":
                    try:
                        datetime(current_year, 2, 29)
                    except:
                        birthday_value = "02-28"

                if today == birthday_value:

                    # ADD ROLE
                    if role and role not in member.roles:
                        await member.add_roles(role)

                    # ANNOUNCE ONCE PER YEAR
                    if row["last_announced"] != current_year:
                        if channel:
                            await channel.send(
                                f"🎉🎂 HAPPY BIRTHDAY {member.mention}! 🎂🎉"
                            )

                        async with db.acquire() as conn:
                            await conn.execute(
                                "UPDATE users SET last_announced = $1 WHERE user_id = $2",
                                current_year,
                                row["user_id"]
                            )

                else:
                    # REMOVE ROLE AFTER BIRTHDAY
                    if role and role in member.roles:
                        await member.remove_roles(role)

# =============================
# RUN
# =============================
if TOKEN and DATABASE_URL:
    bot.run(TOKEN)
else:
    print("❌ Missing DISCORD_TOKEN or DATABASE_URL")
