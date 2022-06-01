# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional
from typing_extensions import Self
from dataclasses import dataclass
from discord.ext import commands
from discord import app_commands, ui

from common.database import connect
from common.helpers import Color, CustomEmoji
from common.views import Confirmation

import asyncio
import discord

if TYPE_CHECKING:
    from common.bot import OxideBot


@dataclass(frozen=True)
class Setting:
    value: str
    friendly_name: str
    description: str
    enable_note: str
    disable_note: str


SETTINGS: Dict[str, Setting] = {
    "allow_anonymous": Setting(value="allow_anonymous", friendly_name="Anonymous Suggestions",
                               description="Allow users to post anonymous suggestions",
                               enable_note="Enable anonymous suggestions",
                               disable_note="Disable anonymous suggestions."),

    "action_notification_enabled": Setting(value="action_notification_enabled",
                                           friendly_name="Action Notification",
                                           description="Send author a notification when suggestion is acted upon.",
                                           enable_note="Enable action notification.",
                                           disable_note="Disable action notification."),

    "allow_attachments": Setting(value="allow_attachments", friendly_name="Attachments",
                                 description="Allow users to include file attachments in suggestions",
                                 enable_note="Allow attachments in suggestions.",
                                 disable_note="Disallow attachments in suggestions."),

    "allow_edits": Setting(value="allow_edits", friendly_name="Edits",
                           description="Allow users to edit suggestions after posting.",
                           enable_note="Enable edits after posting suggestion",
                           disable_note="Disable edits after posting suggestion"),

    "enabled": Setting(value="enabled", friendly_name="Toggle",
                       description="Temporary disable or enable suggestions in channel.",
                       enable_note="Enable the suggestion channel.",
                       disable_note="Temporarily disable suggestions in this channel."),
}


class ChannelSelection(ui.View):
    def __init__(self, *, author: discord.abc.Snowflake, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.author = author
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{CustomEmoji.CROSS} You cannot interact with this.")
            return False

        return True

class SuggestionSettingsModal(ui.Modal):
    toggle: ui.Select[Self] = ui.Select(
        max_values=1,
        min_values=1,
        options=[
            discord.SelectOption(label="Enabled", description="Enable this setting", value="1"),
            discord.SelectOption(label="Disabled", description="Disable this setting", value="0"),
        ],
    )

    def __init__(
        self,
        *,
        author: discord.abc.Snowflake,
        parent: SuggestionSettings,
        title: str,
        value: str,
        channel_id: int
    ) -> None:
        super().__init__(title=title)
        self.author = author
        self.parent = parent
        self.value = value
        self.channel_id = channel_id

        options = self.toggle.options
        setting = SETTINGS[value]
        options[0].description = setting.enable_note
        options[1].description = setting.disable_note

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with connect("databases/suggestions.db") as conn:
            value = int(self.toggle.values[0])
            setting = self.value
            await conn.execute(
                f"UPDATE config SET {setting} = ? WHERE channel_id = ?",
                (value, self.channel_id)
            )
            await interaction.response.defer()
            await self.parent.update(setting, value)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{CustomEmoji.CROSS} You cannot interact with this.")
            return False

        return True


class SuggestionSettings(ui.View):
    SETTING_PLACEHOLDER_TEXT = {
        0: "DISABLED",
        1: "ENABLED",
    }
    SETTING_PLACEHOLDER_EMOJI = {
        0: "<:_:967991996344066059>",
        1: "<:_:967991994888642580>",
    }

    def __init__(self, *, author: discord.abc.Snowflake, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.author = author
        self.channel: Optional[discord.abc.Snowflake] = None
        self.message: Optional[discord.Message] = None
        self.closed: bool = False

    async def update(self, setting: str, toggle: int) -> None:
        assert self.message is not None
        for option in self.settings_select.options:
            value = option.value

            if value == setting:
                friendly_name = SETTINGS[value].friendly_name
                toggle_text = self.SETTING_PLACEHOLDER_TEXT[toggle]
                option.label = f"{friendly_name}: {toggle_text}"
                option.emoji = discord.PartialEmoji.from_str(self.SETTING_PLACEHOLDER_EMOJI[toggle])
                self.settings_select.placeholder = f"{toggle_text.capitalize()} \"{friendly_name}\" successfully."
                break

        await self.message.edit(view=self)
        await asyncio.sleep(2)
        self.settings_select.placeholder = "Settings"
        await self.message.edit(view=self)

    async def setup(self, channel: discord.abc.Snowflake) -> bool:
        """Setups the view for the given channel."""
        self.channel = channel
        async with connect("databases/suggestions.db") as conn:
            data: Optional[Dict[str, int]] = await conn.execute(
                "SELECT * FROM config WHERE channel_id = ?",
                (channel.id,),
                fetch_one=True,
            )
            if not data:
                return False

        select = self.settings_select
        select.options = []

        for value, setting in SETTINGS.items():
            toggle = data[value]
            select.add_option(
                label=f"{setting.friendly_name}: {self.SETTING_PLACEHOLDER_TEXT[toggle]}",
                description=setting.description,
                value=value,
                emoji=self.SETTING_PLACEHOLDER_EMOJI[toggle],
            )

        return True

    @ui.select(
        placeholder="Settings",
        min_values=1,
        max_values=1,
    )
    async def settings_select(self, interaction: discord.Interaction, select: ui.Select[Self]) -> None:
        assert self.channel is not None
        value = select.values[0]
        modal = SuggestionSettingsModal(
            author=interaction.user,
            parent=self,
            title=f"Editing: {SETTINGS[value].friendly_name}",
            value=value,
            channel_id=self.channel.id
        )
        await interaction.response.send_modal(modal)

    @ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button[Self]) -> None:
        await interaction.response.defer()
        self.closed = True
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{CustomEmoji.CROSS} You cannot interact with this.")
            return False

        return True

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

        view = ChannelSelection(author=interaction.user)
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

        view = Confirmation(author=interaction.user)
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

    @app_commands.command(name="settings")
    async def settings(self, interaction: discord.Interaction) -> None:
        """View or edit the settings of a suggestion channel."""
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        view = SuggestionSettings(author=interaction.user)
        success = await view.setup(channel)
        if not success:
            await interaction.followup.send(f"{CustomEmoji.CROSS} An error occured. Try again.")
            return

        embed = discord.Embed(
            title=":gear: Suggestions • Settings",
            description=(
                "Welcome to suggestions settings panel. From here, you can customize "
                "the settings for suggestion channels according to your needs. "
                "\n\n**In order to modify a setting, click on it from the dropdown below.**"
            ),
            color=Color.NEUTRAL,
        )
        view.message = await interaction.followup.send(embed=embed, view=view, wait=True)

        while True:
            await view.wait()

            if view.closed:
                await view.message.delete()
                return

    @app_commands.command(name="restrict")
    async def restrict(self, interaction: discord.Interaction, role: Optional[discord.Role] = None) -> None:
        """Restrict posting of suggestions to a specific role.

        Parameters
        ----------
        role:
            The role to restrict suggestions to. Omit this parameter to remove
            restriction or view current role.
        """
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        if role is None:
            async with connect("databases/suggestions.db") as conn:
                data = await conn.execute(
                    "SELECT role_id FROM config WHERE channel_id = ?",
                    (channel.id,),
                    fetch_one=True,
                )

            if data is not None:
                resolved_role = interaction.guild.get_role(data["role_id"])  # type: ignore
            else:
                await interaction.followup.send(f"No role restriction is configured on this channel.")
                return

            if resolved_role is None:
                await interaction.followup.send(f"No role restriction is configured on this channel.")
                return

            embed = discord.Embed(
                title=":construction: Suggestions • Role Restriction",
                description=f"This suggestion channel is currently restricted to users with {resolved_role.mention} role. \n\nTo remove this restriction, use `/suggestions unrestrict`.",
                color=Color.NEUTRAL,
            )
            await interaction.followup.send(embed=embed)
        else:
            async with connect("databases/suggestions.db") as conn:
                await conn.execute(
                    "UPDATE config SET role_id = ? WHERE channel_id = ?",
                    (role.id, channel.id,),
                )

            embed = discord.Embed(
                title=f"{CustomEmoji.SUCCESS} Suggestions • Role Restriction",
                description=f"Restricted posting of suggestions in this channel to {role.mention} role. Users must have this role to post suggestions now.",
                color=Color.SUCCESS,
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="unrestrict")
    async def unrestrict(self, interaction: discord.Interaction) -> None:
        """Remove any restriction on posting of suggestions.

        Parameters
        ----------
        role:
            The role to restrict suggestions to. Omit this parameter to remove
            restriction or view current role.
        """
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        async with connect("databases/suggestions.db") as conn:
            await conn.execute("UPDATE config SET role_id = NULL WHERE channel_id = ?", (channel.id,))

        await interaction.followup.send(f"{CustomEmoji.SUCCESS} Removed role restriction from this channel.")


async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Suggestions(bot))
