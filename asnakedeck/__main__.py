import asyncio
import logging
from pathlib import Path
import signal
import sys

logging.basicConfig(level=logging.DEBUG)

WINDOWS = sys.platform == "win32"

async def main():
    from StreamDeck.DeviceManager import DeviceManager

    from .deck import Deck
    from .plugin_manager import PluginManager

    task = asyncio.current_task()
    task.set_name("main")

    loop = asyncio.get_event_loop()

    if WINDOWS:
        # Pre-load hidapi.dll so we can "find" it
        preload_dll()

    dm = DeviceManager()

    decks = []

    pm = PluginManager()

    for device in dm.enumerate():
        deck = Deck(device, plugin_manager=pm)
        decks.append(deck)

    while True:
        try:
            tasks = [task for deck in decks for task in deck.tasks]
            if not tasks:
                break
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            break


def preload_dll():
    import ctypes

    path = Path(__file__).parents[1] / 'hidapi.dll'
    ctypes.cdll.LoadLibrary(str(path))


# Run event loop until main_task finishes
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
