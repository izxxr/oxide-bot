# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from discord.ext import commands

import discord

if TYPE_CHECKING:
    from common.context import OxideContext
    from common.bot import OxideBot


class Admin(commands.Cog, command_attrs=dict(hidden=True)):
    """Administration commands for Oxide bot.

    These commands can be used by bot owners and administrators only and are
    totally irrelevant to normal users. Don't even try.
    """

    def __init__(self, bot: OxideBot) -> None:
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx: OxideContext, guild: Optional[discord.Object] = None) -> None:
        """Syncs the application commands.

        If no `guild` is passed, global commands are synced. A guild ID
        can optionally be passed to sync commands for that guild only.
        """
        commands = await self.bot.tree.sync(guild=guild)
        resp = ":ok_hand: Synced %s application commands" % len(commands)
        if guild:
            resp += " for guild %s." % guild.id
        await ctx.send(resp)


async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Admin(bot))
