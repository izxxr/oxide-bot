# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional
from typing_extensions import Self
from discord.ext import commands
from discord import app_commands, ui

from common.database import connect
from common.views import Confirmation

import discord

if TYPE_CHECKING:
    from common.bot import OxideBot


class ChannelSelection(ui.View):
    def __init__(self, *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.channel = None
        self.canceled = False

    async def setup(self, guild: discord.Guild) -> List[int]:
        """Setups the view for the given guild."""
        self.channel_select.options = []

        async with connect("databases/suggestions.db") as conn:
            res = await conn.execute(
                "SELECT channel_id FROM config WHERE guild_id = ?",
                (guild.id,),
                fetch_all=True,
            )

        channel_ids = [int(c["channel_id"]) for c in res]
        for channel_id in channel_ids:
            channel = guild.get_channel(channel_id)
            if channel:
                self.channel_select.add_option(
                    label=f"#{channel.name}",
                    description=channel.topic or "No description", # type: ignore # channel is always Text
                    value=str(channel.id),
                )
            else:
                channel_ids.remove(channel_id)

        return channel_ids

    @ui.select(
        min_values=1,
        max_values=1,
        placeholder="Select a channel.",
    )
    async def channel_select(self, interaction: discord.Interaction, select: ui.Select[Self]) -> None:
        channel = interaction.guild.get_channel(int(select.values[0]))  # type: ignore
        if not channel:
            await interaction.response.send_message(":x: An error occured!")
        else:
            await interaction.response.defer()
        self.channel = channel
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button[Self]) -> None:
        await interaction.response.defer()
        self.canceled = True
        self.stop()


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

    @app_commands.command(name="reset")
    async def reset(self, interaction: discord.Interaction) -> None:
        """Completely reset suggestions setup.

        This command by default requires the "Manage Channels" permission.
        """
        await interaction.response.defer()

        guild: discord.Guild = interaction.guild  # type: ignore
        view = ChannelSelection()
        channel_ids = await view.setup(guild)

        if not channel_ids:
            await interaction.followup.send(":thinking_face: No suggestion channels exist yet.")
            return

        if len(channel_ids) == 1:
            channel = guild.get_channel(int(channel_ids[0]))
        else:
            message = await interaction.followup.send(
                "Resetting the suggestion configuration, select the target channel.",
                view=view,
                wait=True,
            )
            timed_out = await view.wait()
            channel = view.channel

            if timed_out:
                await message.edit(content=":x: No channel selected.", view=None)
                return

            if view.canceled:
                await message.edit(content=":ok_hand: No changes were made.", view=None)
                return

        if channel is None:
            await interaction.edit_original_message(content=":x: An error occured.", view=None)
            return

        view = Confirmation()
        await interaction.edit_original_message(
            content=":warning: This will completely reset the suggestions setup, are you sure to proceed?",
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
            content=":white_check_mark: Successfully reset the suggestions configuration in %s" % channel.mention,
            view=None,
        )

async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Suggestions(bot))
