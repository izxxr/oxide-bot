# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional
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


class SuggestionStatusType:
    PENDING = 0
    ACCEPTED = 1
    DECLINED = 2
    CONSIDERED = 3


class SuggestionConfirmation(ui.View):
    def __init__(
        self,
        *,
        author: discord.abc.Snowflake,
        data: Dict[str, Any],
        channel: discord.TextChannel,
        attachment: Optional[discord.Attachment] = None,
    ) -> None:
        super().__init__()
        self.author = author
        self.data = data
        self.channel = channel
        self.attachment = attachment

    @ui.button(label="Post", style=discord.ButtonStyle.green)
    async def post(self, interaction: discord.Interaction, button: ui.Button[Self]) -> None:
        modal = SuggestionEntryModal(data=self.data, channel=self.channel, attachment=self.attachment)
        await interaction.response.send_modal(modal)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{CustomEmoji.CROSS} You cannot interact with this.")
            return False

        return True


class SuggestionEntryModal(ui.Modal):
    suggestion: ui.TextInput[Self] = ui.TextInput(
        label="Suggestion",
        style=discord.TextStyle.long,
        placeholder="Enter your suggestion (10-4000 characters)",
        required=True,
        min_length=10,
        max_length=4000,
    )
    suggestion_type: ui.Select[Self] = ui.Select(
        options=[
            discord.SelectOption(label="Normal", value="0", description="Non-anonymous suggestion", default=True),
            discord.SelectOption(label="Anonymous", value="1", description="Anonymous suggestion, only moderators can see the author.")
        ],
        disabled=False,
    )

    def __init__(
        self,
        *,
        data: Dict[str, Any],
        channel: discord.TextChannel,
        attachment: Optional[discord.Attachment] = None,
    ) -> None:
        super().__init__(title="Posting a suggestion")
        self.data = data
        self.channel = channel
        self.attachment = attachment

        # TODO: Discord currently has a bug where disabled select inside
        # a modal cause internal error, so this currently does not work
        # if data["allow_anonymous"]:
        #     self.suggestion_type.disabled = False
        # else:
        #     self.suggestion_type.disabled = True

        if attachment:
            self.suggestion.required = False

    async def on_submit(self, interaction: discord.Interaction) -> None:
        is_anonymous = int(self.suggestion_type.values[0])

        # TODO: Remove this check when Discord bug is fixed
        if is_anonymous and not self.data["allow_anonymous"]:
            await interaction.response.edit_message(content=f"{CustomEmoji.CROSS} Anonymous suggestions are not allowed in this channel.", view=None, embed=None)
            return

        channel = self.channel

        async with connect("databases/suggestions.db") as conn:
            suggestions = await conn.execute(
                "SELECT id FROM store WHERE guild_id = ?",
                (interaction.guild_id,),
                fetch_all=True,
            )
            suggestion_id = len(suggestions) + 1
            embed = discord.Embed(
                title=f"Suggestion #{suggestion_id}",
                color=Color.NEUTRAL,
                timestamp=discord.utils.utcnow(),
            )

            content = self.suggestion.value
            attachment = self.attachment
            if content:
                embed.description = content
            if attachment:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    embed.set_image(url=attachment.url)
                else:
                    embed.add_field(name="Attachment", value=f"[{attachment.filename}]({attachment.url})")
            if is_anonymous:
                embed.set_author(name="Anonymous Suggestion")
            else:
                embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
            embed.set_footer(text="Status: Pending")

            try:
                message = await channel.send(embed=embed)
                await message.add_reaction("<:upvote:967992002056695859>")
                await message.add_reaction("<:downvote:967992002371285032>")
            except discord.Forbidden:
                await interaction.response.edit_message(
                    content=f"{CustomEmoji.CROSS} Failed to send message in {channel.mention}",
                    embed=None,
                    view=None
                )
            else:
                await conn.execute(
                    """INSERT INTO store (id, guild_id, channel_id, author_id, message_id, content,
                    attachment_url, anonymous, status, edited_at, action_updated_at, action_note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)""",
                    (suggestion_id, interaction.guild_id, channel.id, interaction.user.id, message.id, content,
                    attachment and attachment.url, is_anonymous, SuggestionStatusType.PENDING),  # type: ignore
                )
                embed = discord.Embed(
                    title=f"{CustomEmoji.SUCCESS} Suggestions • Posted",
                    description=f"Successfully posted a suggestion. The suggestion ID is #{suggestion_id}.",
                    color=Color.SUCCESS,
                )
                embed.add_field(name="Jump URL", value=f"[Click here...]({message.jump_url})")

                if is_anonymous:
                    await interaction.response.defer()
                    await interaction.user.send(embed=embed)
                else:
                    await interaction.response.edit_message(embed=embed, view=None, content=None)

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


class Suggestions(commands.Cog):
    """Manage suggestion channels with ease."""

    def __init__(self, bot: OxideBot) -> None:
        self.bot = bot

    async def prompt_channel_select(
        self,
        interaction: discord.Interaction,
        *,
        prompt: str = "Select the target suggestion channel",
        ephemeral: bool = False,
    ) -> Optional[discord.TextChannel]:
        await interaction.response.defer(ephemeral=ephemeral)

        embed = discord.Embed(title="Suggestions • Channel Selection", color=Color.NEUTRAL)
        guild: discord.Guild = interaction.guild  # type: ignore

        view = ChannelSelection(author=interaction.user)
        channel_ids = await view.setup(guild)

        if not channel_ids:
            await interaction.followup.send(content="No channel has suggestions setup in this server. Use `/suggestions setup` to setup one.", ephemeral=ephemeral)
            return

        if len(channel_ids) == 1:
            channel = guild.get_channel(int(channel_ids[0]))
        else:
            embed.description = prompt
            message = await interaction.followup.send(view=view, wait=True, embed=embed, ephemeral=ephemeral)
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

    async def update_suggestion_status(
        self,
        interaction: discord.Interaction,
        status: int,
        suggestion_id: int,
        note: Optional[str] = None,
    ) -> None:
        await interaction.response.defer()
        async with connect("databases/suggestions.db") as conn:
            suggestion = await conn.execute(
                "SELECT * FROM store WHERE guild_id = ? AND id = ?",
                (interaction.guild_id, suggestion_id),
                fetch_one=True,
            )

            if suggestion is None:
                await interaction.followup.send(f"{CustomEmoji.CROSS} Invalid suggestion ID.")
                return

        if int(suggestion["status"]) != SuggestionStatusType.PENDING:
            await interaction.followup.send(f"{CustomEmoji.CROSS} That suggestion is already acted upon.")
            return

        channel_id = suggestion["channel_id"]
        message_id = suggestion["message_id"]

        channel: discord.TextChannel = interaction.guild.get_channel(channel_id)  # type: ignore

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.followup.send(f"{CustomEmoji.CROSS} Suggestion message not found.")
        else:
            now = discord.utils.utcnow()
            async with connect("databases/suggestions.db") as conn:
                await conn.execute(
                    f"""UPDATE store SET status = {status},
                        action_updated_at = ?, action_note = ? WHERE guild_id = ?
                        AND id = ?""",
                    (now.isoformat(), note, interaction.guild_id, suggestion_id),
                )
                config = await conn.execute(
                    "SELECT action_notification_enabled FROM config WHERE channel_id = ?",
                    (suggestion["channel_id"],),
                    fetch_one=True,
                )

                if config is None:
                    await interaction.followup.send(f"{CustomEmoji.CROSS} Suggestion channel not found.")
                    return

            if status == SuggestionStatusType.ACCEPTED:
                status_friendly = "accepted"
                color = Color.SUCCESS
            elif status == SuggestionStatusType.DECLINED:
                status_friendly = "declined"
                color = Color.DANGER
            else:
                status_friendly = "considered"
                color = Color.WARNING

            embed = message.embeds[0]
            embed.set_footer(text=f"Status: {status_friendly.capitalize()}")
            embed.color = color
            embed.timestamp = now
            if note:
                embed.add_field(name="Staff Note", value=note)
            await message.edit(embed=embed)

            msg = f"{CustomEmoji.SUCCESS} Suggestion status has been updated successfully."

            if config["action_notification_enabled"]:
                member = interaction.guild.get_member(suggestion["author_id"])  # type: ignore

                if member is None:
                    msg += " Suggestion author could not be notified because they left the guild."
                else:
                    embed = discord.Embed(
                        title=f"{CustomEmoji.SUCCESS} Suggestions • Action",
                        description=f"Your suggestion #{suggestion['id']} in **{interaction.guild.name}** has been {status_friendly}.",  # type: ignore
                        color=color,
                    )
                    if note:
                        embed.add_field(name="Staff Note", value=note)
                    embed.add_field(name="Jump to Suggestion", value=f"[Click here...]({message.jump_url})")

                    try:
                        await member.send(embed=embed)
                    except discord.Forbidden:
                        msg += " Suggestion author could not be notified."
                    else:
                        msg += " Suggestion author was notified."

            await interaction.followup.send(msg)

    suggestions = app_commands.Group(
        name="suggestions",
        description="Manage suggestions with ease",
        default_permissions=discord.Permissions(manage_channels=True),
        guild_only=True,
    )

    @app_commands.command()
    @app_commands.guild_only()
    async def suggest(self, interaction: discord.Interaction, attachment: Optional[discord.Attachment] = None) -> None:
        """Post a suggestion.

        Parameters
        ----------
        attachment:
            The file to attach to suggestion.
        """
        channel = await self.prompt_channel_select(interaction, prompt="In which channel do you want to post the suggestion?", ephemeral=True)
        if not channel:
            return

        async with connect("databases/suggestions.db") as conn:
            blacklisted = await conn.execute(
                "SELECT reason FROM blacklist WHERE guild_id = ? AND user_id = ? AND channel_id = ?",
                (interaction.guild_id, interaction.user.id, channel.id),
                fetch_one=True,
            )
            if blacklisted:
                embed = discord.Embed(
                    title=f"{CustomEmoji.DANGER} Suggestions • Blacklisted",
                    description="You are blacklisted from posting suggestions in this channel.",
                    color=Color.DANGER,
                )
                embed.add_field(name="Reason", value=blacklisted["reason"])
                await interaction.edit_original_message(embed=None, view=None, content=None)
                return

            data = await conn.execute(
                "SELECT * FROM config WHERE channel_id = ? and guild_id = ?",
                (channel.id, interaction.guild_id),
                fetch_one=True,
            )

        if data is None:
            await interaction.edit_original_message(content=f"No suggestion channels are setup. Ask a moderator to use `/suggestions setup`.")
            return

        if not data["enabled"]:
            await interaction.edit_original_message(content=f"{CustomEmoji.DANGER} Suggestions are temporarily disabled in this channel.")
            return

        user: discord.Member = interaction.user  # type: ignore
        guild: discord.Guild = interaction.guild  # type: ignore

        role = guild.get_role(data["role_id"])

        if role and role not in user.roles:
            await interaction.edit_original_message(content=f"{CustomEmoji.CROSS} You need `{role.name}` role to post a suggestion in this channel.")
            return

        if attachment and not data["allow_attachments"]:
            await interaction.edit_original_message(content=f"{CustomEmoji.CROSS} Attachments are not allowed in this channel.")
            return

        view = SuggestionConfirmation(author=interaction.user, data=data, channel=channel, attachment=attachment)
        await interaction.edit_original_message(content=f"Posting a suggestion in {channel.mention}, click the button to proceed.", embed=None, view=view)
        await view.wait()

    @suggestions.command()
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

    @suggestions.command(name="remove-setup")
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

    @suggestions.command(name="settings")
    async def settings(self, interaction: discord.Interaction) -> None:
        """View or edit the settings of a suggestion channel."""
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        view = SuggestionSettings(author=interaction.user)
        success = await view.setup(channel)
        if not success:
            await interaction.edit_original_message(
                content=f"{CustomEmoji.CROSS} An error occured. Try again.",
                embed=None,
                view=None
            )
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
        await interaction.edit_original_message(embed=embed, view=view, content=None)
        view.message = await interaction.original_message()

        while True:
            await view.wait()

            if view.closed:
                await view.message.delete()
                return

    @suggestions.command(name="restrict")
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
                await interaction.edit_original_message(
                    content=f"No role restriction is configured on this channel.",
                    embed=None,
                    view=None
                )
                return

            if resolved_role is None:
                await interaction.edit_original_message(
                    content=f"No role restriction is configured on this channel.",
                    embed=None,
                    view=None
                )
                return

            embed = discord.Embed(
                title=":construction: Suggestions • Role Restriction",
                description=f"This suggestion channel is currently restricted to users with {resolved_role.mention} role. \n\nTo remove this restriction, use `/suggestions unrestrict`.",
                color=Color.NEUTRAL,
            )
            await interaction.edit_original_message(embed=embed, view=None, content=None)
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
            await interaction.edit_original_message(embed=embed, view=None, content=None)

    @suggestions.command(name="unrestrict")
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

        await interaction.edit_original_message(content=f"{CustomEmoji.SUCCESS} Removed role restriction from this channel.", embed=None, view=None)

    @suggestions.command(name="accept")
    @app_commands.rename(suggestion_id="suggestion-id")
    async def accept(self, interaction: discord.Interaction, suggestion_id: int, note: Optional[str] = None) -> None:
        """Accepts a suggestion.

        Parameters
        ----------
        suggestion-id:
            The ID of suggestion that you want to accept.
        note:
            The optional note for this action.
        """
        await self.update_suggestion_status(interaction, SuggestionStatusType.ACCEPTED, suggestion_id, note)


    @suggestions.command(name="decline")
    @app_commands.rename(suggestion_id="suggestion-id")
    async def decline(self, interaction: discord.Interaction, suggestion_id: int, note: Optional[str] = None) -> None:
        """Decline a suggestion.

        Parameters
        ----------
        suggestion-id:
            The ID of suggestion that you want to decline.
        note:
            The optional note for this action.
        """
        await self.update_suggestion_status(interaction, SuggestionStatusType.DECLINED, suggestion_id, note)


    @suggestions.command(name="consider")
    @app_commands.rename(suggestion_id="suggestion-id")
    async def consider(self, interaction: discord.Interaction, suggestion_id: int, note: Optional[str] = None) -> None:
        """Consider a suggestion.

        Parameters
        ----------
        suggestion-id:
            The ID of suggestion that you want to consider.
        note:
            The optional note for this action.
        """
        await self.update_suggestion_status(interaction, SuggestionStatusType.CONSIDERED, suggestion_id, note)

    blacklist = app_commands.Group(
        name="blacklist",
        description="Manage suggestions users blacklist",
        parent=suggestions
    )

    @blacklist.command()
    async def add(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None) -> None:
        """Blacklist a user from posting suggestions.

        Parameters
        ----------
        user:
            The user to blacklist.
        reason:
            The reason of blacklisting.
        """
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        async with connect("databases/suggestions.db") as conn:
            existing = await conn.execute(
                "SELECT * FROM blacklist WHERE channel_id = ? and user_id = ?",
                (channel.id, user.id),
                fetch_one=True,
            )
            if existing:
                if reason is not None:
                    await conn.execute(
                        "UPDATE blacklist SET reason = ? where user_id = ? and channel_id = ?",
                        (reason, user.id, channel.id)
                    )
                    await interaction.edit_original_message(
                        content=f"{CustomEmoji.SUCCESS} User is already blacklisted, reason has been updated.",
                        embed=None,
                        view=None
                    )
                else:
                    await interaction.edit_original_message(
                        content=f"{CustomEmoji.SUCCESS} User is already blacklisted.",
                        embed=None,
                        view=None
                    )
            else:
                await conn.execute(
                    """INSERT INTO blacklist (guild_id, channel_id, user_id, reason)
                       VALUES (?, ?, ?, ?)""",
                    (interaction.guild_id, interaction.channel.id, user.id, reason)  # type: ignore
                )
                await interaction.edit_original_message(
                    content=f"{CustomEmoji.SUCCESS} Successfully blacklisted {user}. They can no longer post suggestions in {channel.mention}.",
                    view=None,
                    embed=None,
                )

    @blacklist.command()
    async def remove(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Removes a user from blacklist.

        Parameters
        ----------
        user:
            The user to remove from blacklist.
        """
        channel = await self.prompt_channel_select(interaction)
        if not channel:
            return

        async with connect("databases/suggestions.db") as conn:
            await conn.execute(
                "DELETE FROM blacklist WHERE channel_id = ? and user_id = ?",
                (channel.id, user.id),
            )
            await interaction.edit_original_message(content=f"{CustomEmoji.SUCCESS} Successfully removed {user} from blacklist.", embed=None, view=None)


async def setup(bot: OxideBot) -> None:
    await bot.add_cog(Suggestions(bot))
