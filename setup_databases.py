from __future__ import annotations

from typing import Dict, Tuple
import sqlite3
import os

if not os.path.exists("./databases"):
    os.mkdir("./databases")

ENTIRES: Dict[str, Tuple[str, ...]] = {}

def setup_databases():
    for db, queries in ENTIRES:
        with sqlite3.connect(db) as conn:
            cursor = conn.cursor()
            for query in queries:
                cursor.execute(query)
            conn.commit()
            cursor.close()


if __name__ == "__main__":
    setup_databases()
