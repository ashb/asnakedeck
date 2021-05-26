from collections.abc import Awaitable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .deck import Deck


class KeyDisplayHandler(Protocol):
    def __call__(self, deck: "Deck", key: dict, key_number: int) -> Awaitable[None]:
        ...
