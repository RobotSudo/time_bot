import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, UTC

import database
from config import BIRTHDAY_ROLE_NAME, BIRTHDAY_CHANNEL_ID


class TimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Initialize DB first
        await database.setup_database()

        # Start loop AFTER DB is ready
        if not self.birthday_loop.is_running():
            self.birthday_loop.start()

        await self.bot.tree.sync()

    # =============================
    # /mytime
    # =============================
    @app_commands.command(name="mytime", description="Set your local time")
    async def mytime(self, interaction: discord.Interaction, time_str: str):
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

            async with database.db.acquire() as conn:
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

        except Exception as e:
            print("Error in /mytime:", e)
            await interaction.response.send_message(
                "❌ Invalid format. Example: 1:27 pm or 13:27"
            )

    # =============================
    # BIRTHDAY LOOP
    # =============================
    @tasks.loop(minutes=1)
    async def birthday_loop(self):
        if database.db is None:
            return  # safety guard

        utc_now = datetime.now(UTC)

        async with database.db.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users")

        for guild in self.bot.guilds:
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
                    today = local_time.strftime("%m-%d")
                    current_year = local_time.year

                    if today == row["birthday"]:

                        if role and role not in member.roles:
                            await member.add_roles(role)

                        if row["last_announced"] != current_year:
                            if channel:
                                await channel.send(
                                    f"🎉🎂 HAPPY BIRTHDAY {member.mention}! 🎂🎉"
                                )

                            async with database.db.acquire() as conn:
                                await conn.execute("""
                                    UPDATE users 
                                    SET last_announced = $1 
                                    WHERE user_id = $2
                                """, current_year, row["user_id"])
                    else:
                        if role and role in member.roles:
                            await member.remove_roles(role)


async def setup(bot):
    await bot.add_cog(TimeCog(bot))
