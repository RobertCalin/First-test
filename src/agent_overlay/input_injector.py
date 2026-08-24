"""The agent's "hands": synthesizes mouse and keyboard input via SendInput so actions
land on whatever app currently has focus. Only ever called from OverlayWindow's
hand-gesture control path, which is opt-in (Ctrl+Alt+H) -- nothing here runs
automatically just because the app is running.
"""

from .native import click_at, move_to, type_text

__all__ = ["click_at", "move_to", "type_text"]
