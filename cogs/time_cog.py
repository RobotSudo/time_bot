import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
from database import get_db


class TimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =============================
    # /setutc
    # =============================
    @app_commands.command(name="setutc", description="Set your UTC offset (example: -5 or 3.5)")
    async def setutc(self, interaction: discord.Interaction, offset: float):
        db = get_db()

        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, utc_offset)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id)
                DO UPDATE SET utc_offset = $3
            """, interaction.user.id, str(interaction.user), offset)

        await interaction.response.send_message(
            f"✅ UTC offset set to {offset}",
            ephemeral=True
        )

    # =============================
    # /time
    # =============================
    @app_commands.command(name="time", description="Check someone's local time")
    async def time(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        db = get_db()

        async with db.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT utc_offset FROM users WHERE user_id = $1",
                member.id
            )

        if not result or result["utc_offset"] is None:
            await interaction.response.send_message(
                "❌ That user has not set their UTC offset.",
                ephemeral=True
            )
            return

        offset = result["utc_offset"]
        now_utc = datetime.now(timezone.utc)
        local_time = now_utc + timedelta(hours=offset)

        embed = discord.Embed(
            title=f"🕒 {member.display_name}'s Local Time",
            description=local_time.strftime("%Y-%m-%d %H:%M:%S"),
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(TimeCog(bot))
