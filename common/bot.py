# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations
from typing import TYPE_CHECKING

import os
import logging
import discord
from discord.ext import commands
from common import env

if TYPE_CHECKING:
    from aiohttp import ClientSession

__all__ = (
    "OxideBot",
)

_log = logging.getLogger(__name__)

# Meta data
__version__ = "1.0.0a1"


class OxideBot(commands.Bot):
    """A class that maintains the bot.

    This is a subclass of :class:`discord.ext.commands.Bot` with some
    custom implementations. All properties of former are also valid here.
    """
    def __init__(self) -> None:
        super().__init__(
            command_prefix=["oxy ", "oxi "],
            intents=discord.Intents.all(),
            description="A generic Discord bot.",
            max_messages=None,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=False,
                replied_user=True,
            ),
        )
        self.version: str = __version__

    async def on_ready(self) -> None:
        user = self.user
        assert user is not None
        _log.info("Logged in as %s (ID: %s)", user.name, user.id)

    @property
    def session(self) -> ClientSession:
        """Returns the HTTP client session associated to the bot.

        This returns the session initialized by discord.py internally
        and is therefore only valid after logging in.
        """
        return self.http.__HTTPClient_session  # type: ignore

    async def _setup_extensions(self, *, clean: bool = False) -> None:
        if clean:
            for name, _ in self.extensions.items():
                await self.unload_extension(name)

        # Stripping the entry here prevents trailing whitespaces
        # when whitespaces are used between comma and extension
        # names.
        exclude = [item.strip() for item in env.EXTS_EXCLUDE.split(",")]
        failed = 0
        processed = 0
        for file in os.listdir(env.EXTS_DIRECTORY):
            if file.startswith("_") or not file.endswith(".py"):
                # Ignoring internal (starting with _) and non-py files
                continue
            ext = f"{os.path.dirname(env.EXTS_DIRECTORY)}.{file[:-3]}"
            if ext in exclude:
                continue
            try:
                await self.load_extension(ext)
            except Exception as e:
                _log.error("Failed to load extension %r with error: %s", ext, e)
                failed += 1
            else:
                _log.debug("Loaded extension %r successfully", ext)
                processed += 1

        _log.info("Loaded %s extension(s). (%s extensions failed to load)", processed, failed)

    async def setup_hook(self) -> None:
        """A hook that gets called before websocket is connected.

        This hook is used to perform pre-connect asynchronous initalization
        such as extensions setup.
        """
        await self._setup_extensions(clean=False)
