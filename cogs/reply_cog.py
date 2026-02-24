import discord
from discord.ext import commands
from config import SUDO_ID, HIMENO_ID, GIF_SUDO_TAG, GIF_HIMENO_REPLY


class ReplyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # HIMENO reply reaction
        if message.reference and message.reference.resolved:
            if message.reference.resolved.author.id == HIMENO_ID:
                embed = discord.Embed(
                    description="what did you say?",
                    color=discord.Color.red()
                )
                embed.set_image(url=GIF_HIMENO_REPLY)
                await message.channel.send(embed=embed)

        # SUDO mention reaction
        if any(user.id == SUDO_ID for user in message.mentions):
            embed = discord.Embed(
                description="sudo be like:",
                color=discord.Color.red()
            )
            embed.set_image(url=GIF_SUDO_TAG)
            await message.channel.send(embed=embed)

        await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(ReplyCog(bot))
