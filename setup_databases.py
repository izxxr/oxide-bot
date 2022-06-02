from __future__ import annotations

from typing import Dict, Tuple
import sqlite3
import os

if not os.path.exists("./databases"):
    os.mkdir("./databases")

ENTIRES: Dict[str, Tuple[str, ...]] = {
    "./databases/suggestions.db": (
        """CREATE TABLE IF NOT EXISTS config (
            channel_id INT PRIMARY KEY, guild_id INT, role_id INT DEFAULT NULL,
            allow_anonymous INT DEFAULT 0, action_notification_enabled INT DEFAULT 0,
            allow_attachments INT DEFAULT 0, allow_edits INT DEFAULT 0, enabled INT DEFAULT 1
        )""",
        """CREATE TABLE IF NOT EXISTS blacklist (
            guild_id INT, channel_id INT, user_id INT, reason TEXT DEFAULT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS store (
            id INT, guild_id INT, channel_id INT, author_id INT, message_id INT, content TEXT,
            attachment_url TEXT, anonymous INT, status TEXT, edited_at TEXT,
            action_updated_at TEXT, action_note TEXT
        )""",
    )
}

def setup_databases():
    for db, queries in ENTIRES.items():
        with sqlite3.connect(db) as conn:
            cursor = conn.cursor()
            for query in queries:
                cursor.execute(query)
            conn.commit()
            cursor.close()


if __name__ == "__main__":
    setup_databases()
