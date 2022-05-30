# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

if TYPE_CHECKING:
    from common.context import OxideContext
    from common.bot import OxideBot


class Miscellaneous(commands.Cog):
    """Some random miscellaneous commands."""

    def __init__(self, bot: OxideBot) -> None:
        self.bot = bot

    @commands.command()
    async def ping(self, ctx: OxideContext) -> None:
        """Determines the current websocket latency of the bot."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f":ping_pong: Ping Pong! Current websocket latency is {latency}ms.")


async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Miscellaneous(bot))
