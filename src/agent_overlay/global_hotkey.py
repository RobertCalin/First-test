"""System-wide hotkeys via RegisterHotKey plus a Qt native event filter that watches the
main thread's message queue for WM_HOTKEY. One GlobalHotkeys instance serves every
registered combo; install it on the QApplication once at startup.
"""

from __future__ import annotations

from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

from . import native


class GlobalHotkeys(QAbstractNativeEventFilter):
    def __init__(self) -> None:
        super().__init__()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1

    def register(self, modifiers: int, vk: int, callback: Callable[[], None]) -> int | None:
        """Registers a hotkey and returns its id, or None if the combo is already taken
        (most commonly by another running application)."""
        hotkey_id = self._next_id
        self._next_id += 1
        if not native.register_hotkey(hotkey_id, modifiers, vk):
            return None
        self._callbacks[hotkey_id] = callback
        return hotkey_id

    def unregister_all(self) -> None:
        for hotkey_id in list(self._callbacks):
            native.unregister_hotkey(hotkey_id)
        self._callbacks.clear()

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0

        msg = wintypes.MSG.from_address(int(message))
        if msg.message == native.WM_HOTKEY:
            callback = self._callbacks.get(msg.wParam)
            if callback is not None:
                callback()
        return False, 0
