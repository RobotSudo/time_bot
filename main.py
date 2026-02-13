import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, UTC
import json
import os

# =============================
# CONFIG
# =============================
TOKEN = "MTQ2NzQwNTg0MzA2NTYwMjE0MQ.GN0O3X.CidnFbJPFsHhgdwYhUXjPP9MbrVfncRr02Hnnc"
DATA_FILE = "user_data.json"

BIRTHDAY_ROLE_NAME = "Birthday guy"
BIRTHDAY_CHANNEL_ID = 1468164390460199055

# =============================
# INTENTS
# =============================
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =============================
# LOAD / SAVE
# =============================
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    except:
        user_data = {}
else:
    user_data = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)

# =============================
# READY
# =============================
@bot.event
async def on_ready():
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

        user_id = str(interaction.user.id)
        user_data.setdefault(user_id, {})
        user_data[user_id]["offset"] = offset
        save_data()

        await interaction.response.send_message(
            f"✅ Timezone saved (UTC{offset:+})",
            ephemeral=True
        )

        # 🔥 Re-check birthday in case time change affects it
        await check_member_birthday(interaction.guild, interaction.user)

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

        user_id = str(interaction.user.id)
        user_data.setdefault(user_id, {})
        user_data[user_id]["birthday"] = f"{month:02d}-{day:02d}"

        # Reset announcement flag
        user_data[user_id].pop("last_announced", None)

        save_data()

        await interaction.response.send_message(
            f"🎉 Birthday saved as {month:02d}-{day:02d}",
            ephemeral=True
        )

        # 🔥 Immediately re-check birthday state
        await check_member_birthday(interaction.guild, interaction.user)

    except:
        await interaction.response.send_message(
            "❌ Invalid format. Use MM-DD",
            ephemeral=True
        )

# =============================
# BIRTHDAY CHECK
# =============================
async def check_member_birthday(guild, member):
    role = discord.utils.get(guild.roles, name=BIRTHDAY_ROLE_NAME)
    channel = guild.get_channel(BIRTHDAY_CHANNEL_ID)

    if not role:
        return

    user_id = str(member.id)
    data = user_data.get(user_id)

    if not data or "birthday" not in data or "offset" not in data:
        return

    utc_now = datetime.now(UTC)
    local_time = utc_now + timedelta(hours=data["offset"])

    today = local_time.strftime("%m-%d")
    current_year = local_time.year
    birthday_value = data["birthday"]

    # Handle Feb 29
    if birthday_value == "02-29":
        try:
            datetime(current_year, 2, 29)
        except:
            birthday_value = "02-28"

    try:
        if today == birthday_value:
            # 🎉 Add role
            if role not in member.roles:
                await member.add_roles(role)

            # 🎂 Send announcement once per year
            if data.get("last_announced") != current_year:
                if channel:
                    await channel.send(
                        f"🎉🎂 HAPPY BIRTHDAY {member.mention}! 🎂🎉\n"
                        f"Wishing you an amazing year ahead! 🥳"
                    )
                data["last_announced"] = current_year
                save_data()
        else:
            # 🌙 Remove role if not birthday anymore
            if role in member.roles:
                await member.remove_roles(role)

    except Exception as e:
        print(f"Role error for {member}: {e}")

# =============================
# MIDNIGHT LOOP (Optimized)
# =============================
@tasks.loop(minutes=1)
async def birthday_loop():
    utc_now = datetime.now(UTC)

    for guild in bot.guilds:
        for user_id, data in user_data.items():

            if "birthday" not in data or "offset" not in data:
                continue

            member = guild.get_member(int(user_id))
            if not member:
                continue

            local_time = utc_now + timedelta(hours=data["offset"])

            if local_time.hour == 0 and local_time.minute == 0:

                today_key = local_time.strftime("%Y-%m-%d")

                if data.get("midnight_checked") == today_key:
                    continue

                data["midnight_checked"] = today_key
                save_data()

                await check_member_birthday(guild, member)

# =============================
# RUN
# =============================
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ DISCORD_TOKEN environment variable not set.")
