import os

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
