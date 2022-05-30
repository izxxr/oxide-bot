# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

import logging
from common.bot import OxideBot
from common import env

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] [%(name)s:%(lineno)s] [%(levelname)s] %(message)s"
    )
    logging.getLogger("discord").setLevel(logging.INFO)
    bot = OxideBot()

    if env.BOT_TOKEN is None:
        raise RuntimeError("'OXIDE_BOT_TOKEN' enivornement variable is not set.")

    bot.run(env.BOT_TOKEN)
