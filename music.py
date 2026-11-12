"""Optional, dependency-free accompaniment for the terminal tree."""

from __future__ import annotations

import sys
import threading
from typing import Callable

if sys.platform == "win32":
    try:
        import winsound
    except ImportError:
        winsound = None
else:
    winsound = None


# Jingle Bells, in C. A frequency of zero is a rest.
_E, _D, _C, _G, _F = 659, 587, 523, 784, 698
_MELODY = (
    (_E, 145), (_E, 145), (_E, 290), (0, 145),
    (_E, 145), (_E, 145), (_E, 290), (0, 145),
    (_E, 145), (_G, 145), (_C, 220), (_D, 145), (_E, 320),
    (0, 200),
    (_F, 145), (_F, 145), (_F, 145), (_F, 145),
    (_F, 145), (_E, 145), (_E, 145), (_E, 145),
    (_E, 145), (_D, 145), (_D, 145), (_E, 145),
    (_D, 290), (_G, 290), (0, 200),
    (_E, 145), (_E, 145), (_E, 290), (0, 145),
    (_E, 145), (_E, 145), (_E, 290), (0, 145),
    (_E, 145), (_G, 145), (_C, 220), (_D, 145), (_E, 320),
    (0, 200),
    (_F, 145), (_F, 145), (_F, 145), (_F, 145),
    (_F, 145), (_E, 145), (_E, 145), (_E, 145),
    (_G, 145), (_G, 145), (_F, 145), (_D, 145),
    (_C, 320), (0, 900),
)


class MusicPlayer:
    """Loop a short tune on Windows; stay silent on other platforms.

    ``start()`` and ``toggle()`` return whether music is now enabled.
    ``enabled`` becomes false if the machine cannot play a note.
    """

    def __init__(self) -> None:
        self._beep: Callable[[int, int], None] | None = (
            winsound.Beep if winsound is not None else None
        )
        self._enabled = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def start(self) -> bool:
        with self._lock:
            if self._enabled:
                return True
            if self._beep is None:
                return False
            self._stop_event = threading.Event()
            self._enabled = True
            self._thread = threading.Thread(
                target=self._play,
                args=(self._stop_event,),
                name="christmas-music",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            self._enabled = False
            self._stop_event.set()
            thread = self._thread
        # Beep itself cannot be interrupted, so notes stay under a third of a second.
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.4)

    def toggle(self) -> bool:
        if self.enabled:
            self.stop()
            return False
        return self.start()

    def _play(self, stop_event: threading.Event) -> None:
        try:
            while not stop_event.is_set():
                for frequency, duration in _MELODY:
                    if stop_event.is_set():
                        return
                    if frequency and self._beep is not None:
                        self._beep(frequency, duration)
                        if stop_event.wait(0.022):
                            return
                    elif stop_event.wait(duration / 1000):
                        return
        except (RuntimeError, OSError):
            # Some Windows audio setups reject Beep. The tree can carry on quietly.
            pass
        finally:
            with self._lock:
                if self._stop_event is stop_event:
                    self._enabled = False
