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

    loop = asyncio.get_event_loop()
    if not WINDOWS:
        # TODO: Get this working again!
        # register signal handlers to cancel listener when program is asked to terminate
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler(sig.name, asyncio.get_running_loop())))

    if WINDOWS:
        # Pre-load hidapi.dll so we can "find" it
        preload_dll()

    dm = DeviceManager()

    decks = []

    pm = PluginManager()

    for device in dm.enumerate():
        deck = Deck(device, plugin_manager=pm)
        decks.append(deck)

    running = True

    async def signal_handler(signame, loop):
        nonlocal running
        running = False
        for task in asyncio.all_tasks(loop=loop):
            # cancel all tasks other than this signal_handler
            if task is not asyncio.current_task():
                task.cancel(msg=f"Signal {signame} received")

    while running:
        try:
            await asyncio.gather(*[task for deck in decks for task in deck.tasks])
        except asyncio.CancelledError:
            pass


def preload_dll():
    import ctypes

    path = Path(__file__).parents[1] / 'hidapi.dll'
    ctypes.cdll.LoadLibrary(str(path))


# Run event loop until main_task finishes
if __name__ == "__main__":
    asyncio.run(main())
