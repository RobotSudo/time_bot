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
BIRTHDAY_CHANNEL_ID = 1468166938386497670

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

        # USERS TABLE (timezone + birthday)
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

        # MEBELIKE TABLE (tag gifs)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mebelike (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                gif_url TEXT NOT NULL
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
        utc_offset = round((diff.total_seconds() / 3600) * 2) / 2

        if utc_offset > 14:
            utc_offset -= 24
        if utc_offset < -12:
            utc_offset += 24

        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, utc_offset)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id)
                DO UPDATE SET 
                    utc_offset = EXCLUDED.utc_offset,
                    username = EXCLUDED.username
            """, interaction.user.id, interaction.user.name, utc_offset)

        await interaction.response.send_message(
            f"✅ Timezone saved (UTC{utc_offset:+})"
        )

    except:
        await interaction.response.send_message(
            "❌ Invalid format. Example: 1:27 pm or 13:27"
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
                INSERT INTO users (user_id, username, birthday, last_announced)
                VALUES ($1, $2, $3, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET 
                    birthday = EXCLUDED.birthday,
                    username = EXCLUDED.username,
                    last_announced = NULL
            """, interaction.user.id, interaction.user.name, f"{month:02d}-{day:02d}")

        await interaction.response.send_message(
            f"🎉 Birthday saved as {month:02d}-{day:02d}"
        )

    except:
        await interaction.response.send_message(
            "❌ Invalid format. Use MM-DD"
        )

# =============================
# /time
# =============================
@bot.tree.command(name="time", description="Check someone's local time")
@app_commands.describe(member="Select a member")
async def time(interaction: discord.Interaction, member: discord.Member):

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT utc_offset, username FROM users WHERE user_id = $1",
            member.id
        )

    if not row or row["utc_offset"] is None:
        await interaction.response.send_message(
            f"❌ {member.display_name} has not set their timezone."
        )
        return

    utc_now = datetime.now(UTC)
    local_time = utc_now + timedelta(hours=row["utc_offset"])

    formatted_time = local_time.strftime("%I:%M %p")
    formatted_date = local_time.strftime("%B %d, %Y")

    display_name = row["username"] if row["username"] else member.display_name

    await interaction.response.send_message(
        f"🕒 **{display_name}'s Local Time**\n"
        f"📅 {formatted_date}\n"
        f"⏰ {formatted_time} (UTC{row['utc_offset']:+})"
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

            if not row["birthday"] or row["utc_offset"] is None:
                continue

            member = guild.get_member(row["user_id"])
            if not member:
                continue

            local_time = utc_now + timedelta(hours=row["utc_offset"])

            if local_time.hour == 0 and local_time.minute == 0:

                today_key = local_time.strftime("%Y-%m-%d")

                if row["midnight_checked"] == today_key:
                    continue

                # Update username daily
                async with db.acquire() as conn:
                    await conn.execute("""
                        UPDATE users 
                        SET midnight_checked = $1,
                            username = $2
                        WHERE user_id = $3
                    """, today_key, member.name, row["user_id"])

                today = local_time.strftime("%m-%d")
                current_year = local_time.year
                birthday_value = row["birthday"]

                if birthday_value == "02-29":
                    try:
                        datetime(current_year, 2, 29)
                    except:
                        birthday_value = "02-28"

                if today == birthday_value:

                    if role and role not in member.roles:
                        await member.add_roles(role)

                    if row["last_announced"] != current_year:
                        if channel:
                            await channel.send(
                                f"🎉🎂 HAPPY BIRTHDAY {member.mention}! 🎂🎉"
                            )

                        async with db.acquire() as conn:
                            await conn.execute("""
                                UPDATE users 
                                SET last_announced = $1 
                                WHERE user_id = $2
                            """, current_year, row["user_id"])
                else:
                    if role and role in member.roles:
                        await member.remove_roles(role)
                        
# ================ MENTION LISTENER BREAK ================

SUDO_ID = 1288247401752166453
HIMENO_ID = 1467405843065602141
GIF_SUDO_TAG = "https://media.giphy.com/media/n7TMv8jwpKRA5HdVt2/giphy.gif"
GIF_HIMENO_REPLY = "https://media.discordapp.net/stickers/1323198799191080960.webp?size=160&quality=lossless"

# =============================
# MESSAGE LISTENER
# =============================
@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # =============================
    # HIMENO REPLY RESPONSE
    # =============================
    if message.reference and message.reference.resolved:
        if message.reference.resolved.author.id == HIMENO_ID:
            embed = discord.Embed(
                description="what did you say?",
                color=discord.Color.red()
            )
            embed.set_image(url=GIF_HIMENO_REPLY)
            await message.channel.send(embed=embed)

        await bot.process_commands(message)
        return

    # =============================
    # CUSTOM MEBELIKE SYSTEM
    # =============================
    if message.mentions:

        for mentioned_user in message.mentions:

            async with db.acquire() as conn:
                record = await conn.fetchrow("""
                    SELECT gif_url FROM mebelike
                    WHERE user_id = $1
                """, mentioned_user.id)

            if record:
                embed = discord.Embed(
                    description=f"{mentioned_user.display_name} be like:",
                    color=discord.Color.red()
                )
                embed.set_image(url=record["gif_url"])
                await message.channel.send(embed=embed)

    await bot.process_commands(message)


# =============================
# /mebelike (Supports link OR upload)
# =============================
@bot.tree.command(name="mebelike", description="Set your '@you be like:' GIF")
@app_commands.describe(
    gif="Direct link to your GIF (optional)",
    image="Upload a GIF or image (optional)"
)
async def mebelike(
    interaction: discord.Interaction,
    gif: str = None,
    image: discord.Attachment = None
):

    # Must provide at least one
    if not gif and not image:
        await interaction.response.send_message(
            "❌ Provide either a GIF link or upload an image.",
            ephemeral=True
        )
        return

    final_url = None

    # =============================
    # If user uploaded file
    # =============================
    if image:

        # Validate file type
        if not image.content_type.startswith("image"):
            await interaction.response.send_message(
                "❌ File must be an image or GIF.",
                ephemeral=True
            )
            return

        final_url = image.url

    # =============================
    # If user provided link
    # =============================
    elif gif:
        if not gif.startswith("http"):
            await interaction.response.send_message(
                "❌ Please provide a valid direct GIF link.",
                ephemeral=True
            )
            return

        final_url = gif

    # =============================
    # Save to database
    # =============================
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO mebelike (user_id, username, gif_url)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET 
                gif_url = EXCLUDED.gif_url,
                username = EXCLUDED.username
        """,
        interaction.user.id,
        interaction.user.name,   # <-- This updates username
        final_url
    )





# ================ END OF THE CODE ================

# =============================
# RUN
# =============================
if TOKEN and DATABASE_URL:
    bot.run(TOKEN)
else:
    print("❌ Missing DISCORD_TOKEN or DATABASE_URL")
