import os
from functools import cached_property
from itertools import chain
from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from .types import KeyDisplayHandler

# Set a couple of directory paths for later use.
# This follows the spec at the following address:
# https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME")
if not XDG_CONFIG_HOME:
    XDG_CONFIG_HOME = os.path.join(os.environ["HOME"], ".config")
CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, "snakedeck")

XDG_STATE_HOME = os.environ.get("XDG_STATE_HOME")
if not XDG_STATE_HOME:
    XDG_STATE_HOME = os.path.join(os.environ["HOME"], ".local", "state")
STATE_DIR = os.path.join(XDG_STATE_HOME, "snakedeck")


class PluginManager(pluggy.PluginManager):
    def __init__(self):
        from . import hookspecs
        from .displayers import clock

        super().__init__("asnakedeck")

        self.add_hookspecs(hookspecs)
        self.register(clock)

    @cached_property
    def key_displayers(self) -> dict[str, "KeyDisplayHandler"]:
        # Only load entrypoints on demand. This imports _all_ entrypoints for
        # "displayers" here. Better might be to only load the specific name
        # when asked, but pluggy doesn't give us that level of freedom.
        self.load_setuptools_entrypoints("asnakedeck", "displayers")
        return {key_displayer.__name__: key_displayer for key_displayer in chain(*self.hook.register_key_displayers())}
