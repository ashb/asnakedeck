import asyncio
import logging
import signal

logging.basicConfig(level=logging.DEBUG)


async def main():
    from StreamDeck.DeviceManager import DeviceManager

    from .deck import Deck
    from .plugin_manager import PluginManager

    loop = asyncio.get_event_loop()
    # register signal handlers to cancel listener when program is asked to terminate
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler(sig.name, asyncio.get_running_loop())))

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


# Run event loop until main_task finishes
asyncio.run(main())
