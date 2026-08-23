"""Win32 interop via ctypes: layered/click-through window styles, global hotkeys, and
SendInput for mouse/keyboard injection. Kept isolated here so the rest of the app never
touches ctypes directly.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080  # hide from alt-tab / taskbar

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

SM_CXSCREEN = 0
SM_CYSCREEN = 1

VK_LBUTTON = 0x01

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


# Explicit argtypes/restype for every function used, rather than relying on ctypes'
# defaults -- those default to c_int, which silently truncates pointer-sized values on
# 64-bit and can't accept None for a NULL handle. This can't be exercised/tested outside
# Windows, so being explicit here removes a whole class of easy-to-miss ctypes bugs.
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def set_click_through(hwnd: int, click_through: bool) -> None:
    style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
    if click_through:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)


def is_left_button_down() -> bool:
    """Live state of the physical/synthesized left mouse button, queried directly rather
    than via a window message -- works regardless of which window (if any) has focus, and
    doesn't distinguish a real click from one this app injected via click_at()."""
    return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def register_hotkey(hotkey_id: int, modifiers: int, vk: int) -> bool:
    """Registers a thread-associated hotkey (NULL hwnd): WM_HOTKEY is posted to this
    thread's message queue, where Qt's native event filter picks it up."""
    return bool(user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk))


def unregister_hotkey(hotkey_id: int) -> None:
    user32.UnregisterHotKey(None, hotkey_id)


def _send(*inputs: INPUT) -> None:
    array = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def move_to(x: int, y: int) -> None:
    """Moves the cursor to absolute coordinates on the primary monitor."""
    width = user32.GetSystemMetrics(SM_CXSCREEN)
    height = user32.GetSystemMetrics(SM_CYSCREEN)
    normalized_x = int(x * 65535 / max(1, width - 1))
    normalized_y = int(y * 65535 / max(1, height - 1))

    mi = MOUSEINPUT(normalized_x, normalized_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)
    _send(INPUT(INPUT_MOUSE, _InputUnion(mi=mi)))


def click_at(x: int, y: int) -> None:
    """Moves the cursor to absolute coordinates and left-clicks there.

    Deliberately does NOT add a delay between the down and up events to make the button
    state easier to poll elsewhere (e.g. to detect this click for blink feedback) -- doing
    that with time.sleep() here would block whatever thread calls click_at(), which for
    hand-gesture clicks is the Qt GUI thread; stalling it, even briefly, on every click is
    worse than the alternative. Callers that need to react to their own synthesized clicks
    should trigger that directly at the call site instead of relying on external polling
    to observe a state change that may be too brief to reliably catch."""
    move_to(x, y)
    down = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
    up = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)
    _send(
        INPUT(INPUT_MOUSE, _InputUnion(mi=down)),
        INPUT(INPUT_MOUSE, _InputUnion(mi=up)),
    )


def type_text(text: str) -> None:
    """Types literal text into whatever control currently has focus."""
    inputs: list[INPUT] = []
    for ch in text:
        down = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, None)
        up = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
        inputs.append(INPUT(INPUT_KEYBOARD, _InputUnion(ki=down)))
        inputs.append(INPUT(INPUT_KEYBOARD, _InputUnion(ki=up)))
    _send(*inputs)
