from __future__ import annotations

import asyncio
import io
import logging
import sys
import threading
from typing import TYPE_CHECKING, Type
import weakref

from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.graphics import Line, Color, RoundedRectangle
from kivy.config import Config
from StreamDeck.Devices.StreamDeck import StreamDeck
from StreamDeck.Transport.Dummy import Dummy

if TYPE_CHECKING:
    from ..deck import Deck


Config.set('graphics', 'resizable', False)

log = logging.getLogger(__name__)


class Key(ButtonBehavior, Image):
    always_release = True

    def prepare(self):
        assert self.canvas
        with self.canvas.after:
            # Fully transparent by default
            self.mask_color = Color(1, 1, 1, 0)
            self.mask = RoundedRectangle(radius=(10,))
            Color(0.3, 0.3, 0.3, 1)
            self.line = Line(rounded_rectangle=(0, 0, 72, 72, 10))

        def update_border(instance, value):
            self.mask.pos = instance.pos
            self.mask.size = instance.size
            self.line.rounded_rectangle = (instance.x, instance.y, instance.width, instance.width, 10)

        def on_state_change(instance, state):
            self.mask_color.a = 0 if state == "normal" else 0.5

        # listen to changes
        self.bind(pos=update_border, size=update_border)  # type: ignore
        self.bind(state=on_state_change)  # type: ignore


async def shutdown(loop, signal=None):
    """Cleanup tasks tied to the service's shutdown."""
    if signal:
        logging.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    [task.cancel() for task in tasks]

    logging.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


class AsyncApp(App):

    keys: dict[int, Key]
    root: GridLayout
    rows: int
    cols: int

    deck: weakref.ProxyType[Deck]
    simulation: weakref.ReferenceType[SimulatedDeck]

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        super().__init__()

    def build(self):

        self.keys = {}
        self.title = "asnakedeck"
        sim = self.simulation()
        assert sim

        layout = GridLayout(
            rows=self.rows,
            cols=self.cols,
            padding=[10],
            spacing=[10],
            row_force_default=True,
            row_default_height=sim.KEY_PIXEL_HEIGHT,
            col_force_default=True,
            col_default_width=sim.KEY_PIXEL_WIDTH,
        )

        for y in range(self.rows):
            for x in range(self.cols):
                idx = y * self.cols + x
                key = self.keys[idx] = Key(x=x, y=y)
                key.prepare()
                key.fbind('on_press', self.on_keypress, idx=idx, state=True)
                key.fbind('on_release', self.on_keypress, idx=idx, state=False)
                sim.set_key_image(idx, None)
                layout.add_widget(key)

        return layout

    def on_keypress(self, _, idx: int, state: bool):
        asyncio.create_task(self.deck.on_keypress(self.simulation(), idx, state))

    def on_start(self):
        from ..deck import Deck
        from ..plugin_manager import PluginManager

        from kivy.core.window import Window


        self.root.do_layout()
        if list(Window.size) != list(self.root.minimum_size):
            log.info("Resizing window from %r to %r", Window.size, self.root.minimum_size)

        pm = PluginManager()
        self.deck = Deck(self.simulation(), plugin_manager=pm)  # type: ignore

    def on_stop(self):
        asyncio.create_task(shutdown(asyncio.get_running_loop()))
        ...


class SimulatedDeck(StreamDeck):

    serial_number: str
    app: AsyncApp

    KEY_FLIP = (False, False)

    def __init__(self, app: AsyncApp, serial_number: str):
        self.serial_number = serial_number
        self.app = app
        super().__init__(Dummy.Device("asnakedeck", "gui"))

    def _read_key_states(self):
        log.info("_read_key_states called")
        return [False] * self.KEY_COUNT

    def _reset_key_stream(self):
        pass

    def reset(self):
        pass

    def set_brightness(self, percent):
        pass

    def get_serial_number(self):
        return self.serial_number

    def get_firmware_version(self):
        return "N/A"

    def set_key_image(self, key, image):
        image = bytes(image or self.BLANK_KEY_IMAGE)  # type: ignore
        kivy_image = CoreImage(io.BytesIO(image), ext=self.KEY_IMAGE_FORMAT.lower())
        assert self.app.keys
        self.app.keys[key].texture = kivy_image.texture
        pass

    def _setup_reader(self, callback):

        if callback is None:
            return

        self.callback = callback
        self.run_read_thread = True
        self.read_thread = threading.Thread(target=callback)
        self.read_thread.daemon = True
        self.read_thread.join = lambda: 0  # type: ignore
        # BUT DON'T RUN IT - We call the callback directly from the AsyncApp instead

    @classmethod
    def make_simulation(cls, serial_number: str, kind: Type[StreamDeck]):
        # Make a quess at the size before we create the window
        # 10 px between keys, and 10 px either side
        Config.set('graphics', 'width', 10 + (kind.KEY_COLS * kind.KEY_PIXEL_WIDTH) + (kind.KEY_COLS-1) * 10 + 10)
        Config.set('graphics', 'height', 10 + (kind.KEY_ROWS * kind.KEY_PIXEL_HEIGHT) + (kind.KEY_ROWS-1) * 10 + 10)
        app = AsyncApp(kind.KEY_ROWS, kind.KEY_COLS)
        sim = SimulatedDeck(app, serial_number)

        app.simulation = weakref.ref(sim)

        # Copy across constants
        for name, val in kind.__dict__.items():
            if name != "KEY_FLIP" and name == name.upper():
                setattr(sim, name, val)
        app.hardware = weakref.proxy(sim)

        return sim


async def main(serial: str, kind: Type[StreamDeck]):

    hardware = SimulatedDeck.make_simulation(serial, kind)
    app = hardware.app

    try:
        await asyncio.gather(app.async_run())
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    from StreamDeck.Devices.StreamDeckOriginalV2 import StreamDeckOriginalV2
    asyncio.run(main(sys.argv[1], StreamDeckOriginalV2))
