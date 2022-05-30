# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing_extensions import Self
from typing import Optional
from discord import ui

import discord


class Confirmation(ui.View):
    def __init__(self, prompt: str = "Are you sure?", *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.prompt = prompt
        self.confirmed = None

    @discord.ui.button(label="Confirm")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.confirmed = False
        await interaction.response.defer()
        self.stop()
