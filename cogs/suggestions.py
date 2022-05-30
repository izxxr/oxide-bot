# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands
from discord import app_commands

from common.database import connect
from common.views import Confirmation

import discord

if TYPE_CHECKING:
    from common.bot import OxideBot

@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
class Suggestions(commands.GroupCog, group_name="suggestions"):
    """Manage suggestion channels with ease."""

    def __init__(self, bot: OxideBot) -> None:
        self.bot = bot

    @app_commands.command()
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Setup suggestions in a channel.

        This command by default requires the "Manage Channels" permission.

        Parameters
        ----------
        channel:
            The channel to setup suggestions in.
        """
        async with connect("databases/suggestions.db") as conn:
            check = await conn.execute(
                "SELECT * FROM config WHERE channel_id = ? and guild_id = ?",
                (channel.id, interaction.guild_id),
                fetch_one=True,
            )
            if check:
                await interaction.response.send_message(":x: Suggestions are already configured in this channel.", ephemeral=True)
                return

            await conn.execute(
                "INSERT INTO config (guild_id, channel_id) VALUES (?, ?)",
                (interaction.guild_id, channel.id),
            )
            await interaction.response.send_message(":white_check_mark: Configured suggestions in %s" % channel.mention)

    @app_commands.command(name="reset-channel")
    async def reset(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Completely remove suggestions setup from a channel.

        This command by default requires the "Manage Channels" permission.

        Parameters
        ----------
        channel:
            The channel to reset suggestions from.
        """
        view = Confirmation()
        await interaction.response.send_message(
            ":warning: This will reset any suggestions setup in this channel, are you sure to proceed?",
            view=view,
        )
        await view.wait()

        if view.confirmed is None:
            await interaction.edit_original_message(
                content=":x: You didn't respond in time.",
                view=None,
            )
            return

        if not view.confirmed:
            await interaction.edit_original_message(
                content=":ok_hand: No changes were made.",
                view=None,
            )
            return

        async with connect("databases/suggestions.db") as conn:
            await conn.execute(
                "DELETE FROM config WHERE channel_id = ? and guild_id = ?",
                (channel.id, interaction.guild_id),
            )

        await interaction.edit_original_message(
            content=":white_check_mark: Reset any suggestions configuration in %s" % channel.mention,
            view=None,
        )

async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Suggestions(bot))
