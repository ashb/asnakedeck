from typing import Iterable

import pluggy

from .types import KeyDisplayHandler

hookspec = pluggy.HookspecMarker("asnakedeck")


@hookspec
def register_key_displayers() -> Iterable[KeyDisplayHandler]:
    """
    :return: A list of key behaviour actions
    """
