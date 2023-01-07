from __future__ import annotations

import asyncio
import importlib
import logging
import os
from functools import cache
from pathlib import Path

import typer

from . import platform

logging.basicConfig(level=logging.DEBUG)

cli = typer.Typer()


async def real_hardware() -> None:
    from StreamDeck.DeviceManager import DeviceManager

    from .deck import Deck
    from .plugin_manager import PluginManager

    task = asyncio.current_task()
    assert task
    task.set_name("main")

    if platform.WINDOWS:
        # Pre-load hidapi.dll so we can "find" it
        preload_dll()

    dm = DeviceManager()

    decks: list[Deck] = []

    pm = PluginManager()

    for device in dm.enumerate():
        deck = Deck(device, plugin_manager=pm)
        decks.append(deck)
        deck.open()

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


@cache
def all_serial_numbers():
    return [item.stem for item in platform.CONFIG_DIR.glob("*.yaml")]


@cache
def all_deck_types():
    import importlib
    import pkgutil

    mod = importlib.import_module('StreamDeck.Devices')

    return [
        submod.name
        for submod in pkgutil.iter_modules(mod.__path__)
        # Ignore the ABC
        if submod.name != "StreamDeck"
    ]


def validate_serial(serial: str):
    if serial not in all_serial_numbers():
        raise typer.BadParameter(f'No config file found for serial {serial!r}')


def validate_kind(kind: str):
    try:
        mod = importlib.import_module(f'StreamDeck.Devices.{kind}')
        return getattr(mod, kind)
    except ImportError:
        raise typer.BadParameter(f'Deck type {kind!r} is not known to StreamDeck library. See `deck-types` command')


@cli.command()
def fake(serial: str, kind=typer.Option(..., callback=validate_kind)):
    os.environ.setdefault('KIVY_LOG_MODE', 'MIXED')

    from .simulation.app import main

    asyncio.run(main(serial, kind))


@cli.command()
def run():
    try:
        asyncio.run(real_hardware())
    except KeyboardInterrupt:
        pass


@cli.command()
def serial_numbers():
    """List the serial numbers for which config files exist"""
    for serial in all_serial_numbers():
        print(serial)


@cli.command()
def deck_types():
    """Print the known StreamDeck types"""
    for kind in all_deck_types():
        print(kind)


@cli.callback(invoke_without_command=True)
def default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        return ctx.invoke(run)


# Run event loop until main_task finishes
if __name__ == "__main__":
    cli()
