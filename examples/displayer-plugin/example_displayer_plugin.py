import asyncio
import time
from typing import TYPE_CHECKING

from asnakedeck import hookimpl
from asnakedeck.types import KeyDisplayHandler

if TYPE_CHECKING:
    from asnakedeck.deck import Deck


@hookimpl
def register_key_displayers() -> list[KeyDisplayHandler]:
    return [foo]


async def foo(deck: "Deck", key, key_number) -> None:
    while True:
        key["label"] = "Foo\n" + time.strftime("%H:%M:%S")
        deck.update_key(key_number, key)
        await asyncio.sleep(1)
