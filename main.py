import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, UTC
import asyncpg
import os
import io
from collections import defaultdict


# =============================
# CONFIG
# =============================
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

BIRTHDAY_ROLE_NAME = "Birthday guy"
BIRTHDAY_CHANNEL_ID = 1468166938386497670
STORAGE_CHANNEL_ID = 1477040555493032006

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

from collections import defaultdict
from datetime import datetime, timedelta, UTC

# Persistent tracker
himeno_trigger_tracker = defaultdict(list)

# =============================
# MESSAGE LISTENER
# =============================
@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # =============================
    # HIMENO REPLY RESPONSE + AUTO TIMEOUT
    # =============================
    if message.reference and message.reference.resolved:
        if message.reference.resolved.author.id == HIMENO_ID:

            embed = discord.Embed(
                description="what did you say?",
                color=discord.Color.red()
            )
            embed.set_image(url=GIF_HIMENO_REPLY)
            await message.channel.send(embed=embed)

            user_id = message.author.id
            now = datetime.now(UTC)

            # Add timestamp
            himeno_trigger_tracker[user_id].append(now)

            # Remove entries older than 5 minutes
            five_minutes_ago = now - timedelta(minutes=5)
            himeno_trigger_tracker[user_id] = [
                t for t in himeno_trigger_tracker[user_id]
                if t > five_minutes_ago
            ]

            # If triggered 3 times within 5 minutes
            if len(himeno_trigger_tracker[user_id]) >= 3:

                try:
                    await message.author.timeout(
                        timedelta(minutes=5),
                        reason="Triggered Himeno 3 times in 5 minutes"
                    )

                    await message.channel.send(
                        f"⛔ {message.author.mention} timed out for 5 minutes."
                    )

                except Exception as e:
                    print("Timeout failed:", e)

                # Reset counter after punishment
                himeno_trigger_tracker[user_id].clear()

        await bot.process_commands(message)
        return

    await bot.process_commands(message)

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
# /mebelike (FULL SAFE VERSION)
# =============================
@bot.tree.command(name="mebelike", description="Set your '@you be like:' GIF")
@app_commands.describe(
    gif="Direct link to your GIF (optional)",
    file="Upload a GIF or image (optional)"
)
async def mebelike(
    interaction: discord.Interaction,
    gif: str = None,
    file: discord.Attachment = None
):

    if not gif and not file:
        await interaction.response.send_message(
            "❌ Provide either a GIF link or upload an image.",
            ephemeral=True
        )
        return

    final_url = None

    # =============================
    # FILE UPLOAD (PERMANENT STORAGE)
    # =============================
    if file:

        allowed_types = [
            "image/gif",
            "image/png",
            "image/jpeg",
            "image/webp"
        ]

        if not file.content_type or file.content_type not in allowed_types:
            await interaction.response.send_message(
                "❌ Only GIF, PNG, JPG, or WEBP allowed.",
                ephemeral=True
            )
            return

        if file.size > 8 * 1024 * 1024:
            await interaction.response.send_message(
                "❌ File too large (max 8MB).",
                ephemeral=True
            )
            return

        # Download file
        file_bytes = await file.read()

        # Upload to permanent storage channel
        storage_channel = bot.get_channel(STORAGE_CHANNEL_ID)

        if not storage_channel:
            await interaction.response.send_message(
                "❌ Storage channel not found.",
                ephemeral=True
            )
            return

        message = await storage_channel.send(
            file=discord.File(
                fp=io.BytesIO(file_bytes),
                filename=file.filename
            )
        )

        # Get permanent CDN URL
        final_url = message.attachments[0].url

    # =============================
    # LINK HANDLING
    # =============================
    elif gif:

        gif = gif.strip()

        if not gif.startswith("http"):
            await interaction.response.send_message(
                "❌ Invalid link.",
                ephemeral=True
            )
            return

        allowed_domains = [
            "media.tenor.com",
            "media.giphy.com",
            "cdn.discordapp.com",
            "media.discordapp.net"
        ]

        if not any(domain in gif for domain in allowed_domains):
            await interaction.response.send_message(
                "⚠️ Use a direct media link (Tenor/Giphy/Discord).",
                ephemeral=True
            )
            return

        final_url = gif

    # =============================
    # SAVE TO DATABASE
    # =============================
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO mebelike (user_id, gif_url, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET
                gif_url = EXCLUDED.gif_url,
                username = EXCLUDED.username
        """,
        interaction.user.id,
        final_url,
        interaction.user.display_name
        )

    await interaction.response.send_message(
        "✅ Your '@you be like:' media has been saved!",
        ephemeral=True
    )

# ================ GOOD NIGHT WISHES ================

GOODNIGHT_GIF = "https://klipy.com/gifs/kittensleep-cute"

gn_last_trigger = None


# =============================
# MESSAGE LISTENER
# =============================
@bot.event
async def on_message(message):

    global gn_last_trigger

    if message.author.bot:
        return

    content = message.content.lower().strip()

    goodnight_triggers = [
        "gn",
        "good night",
        "me go eep",
        "sleep"
    ]

    if any(trigger in content for trigger in goodnight_triggers):

        now = datetime.now(UTC)

        # Global 10 minute cooldown
        if gn_last_trigger and (now - gn_last_trigger) < timedelta(minutes=10):
            return

        gn_last_trigger = now

        embed = discord.Embed(
            description="🌙 Good night!",
            color=discord.Color.dark_blue()
        )
        embed.set_image(url=GOODNIGHT_GIF)

        await message.channel.send(embed=embed)

    await bot.process_commands(message)

# ================ END OF THE CODE ================

# =============================
# RUN
# =============================
if TOKEN and DATABASE_URL:
    bot.run(TOKEN)
else:
    print("❌ Missing DISCORD_TOKEN or DATABASE_URL")
