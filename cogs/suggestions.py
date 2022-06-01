# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional
from typing_extensions import Self
from discord.ext import commands
from discord import app_commands, ui

from common.database import connect
from common.helpers import Color, CustomEmoji
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
            await interaction.response.send_message("I cannot see that channel, was it deleted?")
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

    async def prompt_channel_select(
        self,
        interaction: discord.Interaction,
        *,
        prompt: str = "Select the target suggestion channel"
    ) -> Optional[discord.TextChannel]:
        await interaction.response.defer()

        embed = discord.Embed(title="Suggestions • Channel Selection", color=Color.NEUTRAL)
        guild: discord.Guild = interaction.guild  # type: ignore

        view = ChannelSelection()
        channel_ids = await view.setup(guild)

        if not channel_ids:
            await interaction.followup.send(content="No channel has suggestions setup in this server. Use `/suggestions setup` to setup one.")
            return

        if len(channel_ids) == 1:
            channel = guild.get_channel(int(channel_ids[0]))
        else:
            embed.description = prompt
            message = await interaction.followup.send(view=view, wait=True, embed=embed)
            timed_out = await view.wait()

            if timed_out:
                await message.edit(content=f"{CustomEmoji.CROSS} You didn't select a channel in time.", view=None)
                return

            channel = view.channel

            if view.canceled:
                await message.edit(content="This operation was canceled and no changes were made.", view=None)
                return

        if channel is None:
            await interaction.edit_original_message(embed=None, content=f"{CustomEmoji.CROSS} Channel not found.", view=None)
            return

        return channel  # type: ignore # Always TextChannel

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
                await interaction.response.send_message(f"{CustomEmoji.CROSS} Suggestions are already configured in this channel.", ephemeral=True)
                return

            await conn.execute(
                "INSERT INTO config (guild_id, channel_id) VALUES (?, ?)",
                (interaction.guild_id, channel.id),
            )

        embed = discord.Embed(
            title=f"{CustomEmoji.SUCCESS} Suggestions • Setup",
            description=f"Suggestions have been sucessfully configured in {channel.mention}",
            color=Color.SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove-setup")
    async def remove_setup(self, interaction: discord.Interaction) -> None:
        """Remove suggestions setup from a channel.

        This command by default requires the "Manage Channels" permission.
        """
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        await interaction.delete_original_message()

        view = Confirmation()
        view.confirm_button.style = discord.ButtonStyle.gray  # UX
        embed = discord.Embed(
            title=f" Suggestions • Setup Removal",
            description=f"This will completely remove the suggestions from {channel.mention}, are you sure to proceed?",
            color=Color.WARNING,
        )

        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await view.wait()

        if view.confirmed is None:
            await message.edit(
                content=f"{CustomEmoji.CROSS} Timed out.",
                embed=None,
                view=None,
            )
        if not view.confirmed:
            await message.edit(
                content="Operation canceled. No changes were made.",
                embed=None,
                view=None,
            )
        else:
            async with connect("databases/suggestions.db") as conn:
                await conn.execute(
                    "DELETE FROM config WHERE channel_id = ? and guild_id = ?",
                    (channel.id, interaction.guild_id),
                )

            await message.edit(
                content=f"{CustomEmoji.SUCCESS} Suggestions have been removed from {channel.mention}",
                view=None,
                embed=None,
            )

async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Suggestions(bot))
