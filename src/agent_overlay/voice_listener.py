"""Placeholder for speech-to-text. Not wired to the microphone or to any recognition
engine yet -- the real choice (offline Whisper vs. a cloud STT API) depends on
latency/accuracy/privacy tradeoffs that haven't been made yet. This just defines the
shape the rest of the app expects so that decision can be dropped in later without
touching callers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class VoiceListener(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def on_phrase(self, callback: Callable[[str], None]) -> None: ...


class NullVoiceListener:
    """No-op implementation used until a real engine is wired in."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def on_phrase(self, callback: Callable[[str], None]) -> None:
        pass
