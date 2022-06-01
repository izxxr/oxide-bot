# Licensed under the MIT license. Copyright (C) nerdguyahmad 2022-2023

from __future__ import annotations

from typing_extensions import Self
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, overload
from discord.utils import MISSING

import aiosqlite


def _dict_factory(cursor: aiosqlite.Cursor, row: aiosqlite.Row[Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    for idx, col in enumerate(cursor.description):  # type: ignore
        d[col[0]] = row[idx]  # type: ignore
    return d


class _Connection:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn = MISSING

    async def __aenter__(self) -> Self:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = _dict_factory
        return self

    async def __aexit__(self, *_) -> None:
        await self._conn.close()
        self._conn = MISSING

    @overload
    async def execute(
        self,
        sql: str,
        values: Optional[Tuple[Any, ...]] = ...,
        *,
        fetch_one: Literal[False] = False,
        fetch_all: Literal[False] = False,
    ) -> None:
        ...

    @overload
    async def execute(
        self,
        sql: str,
        values: Optional[Tuple[Any, ...]] = ...,
        *,
        fetch_one: Literal[True] = True,
        fetch_all: Literal[False] = False,
    ) -> Optional[Dict[str, Any]]:
        ...

    @overload
    async def execute(
        self,
        sql: str,
        values: Optional[Tuple[Any, ...]] = ...,
        *,
        fetch_one: Literal[False] = False,
        fetch_all: Literal[True] = True,
    ) -> List[Dict[str, Any]]:
        ...

    async def execute(
        self,
        sql: str,
        values: Optional[Tuple[Any, ...]] = None,
        *,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Execute SQL in this connection."""
        if fetch_one and fetch_all:
            raise TypeError("Cannot mix fetch_one and fetch_all")
        if self._conn is MISSING:
            raise RuntimeError("SQL can only be executed within 'async with' context")

        ret: Any = None
        async with self._conn.cursor() as cur:
            res = await cur.execute(sql, values or ())
            if fetch_one:
                ret = await res.fetchone()  # type: ignore
            elif fetch_all:
                ret = await res.fetchall()  # type: ignore
            else:
                await self._conn.commit()
            await res.close()

        return ret


def connect(path: str) -> _Connection:
    """Returns a context manager interface for executing SQL."""
    return _Connection(path)
