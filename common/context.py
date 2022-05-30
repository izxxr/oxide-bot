# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from bot import OxideBot

__all__ = (
    "OxideContext",
)


class OxideContext(commands.Context[OxideBot]):
    """A :class:`discord.ext.commands.Context` that implements some custom operations"""
