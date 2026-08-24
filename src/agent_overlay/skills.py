"""Record a demonstrated sequence of mouse actions and replay it later -- Phase 1 of
"learning by demonstration": pure literal replay of recorded (x, y) positions and click
timing, no generalization. Recording works by polling cursor position and button state
(the same approach already used elsewhere in this app for eye tracking and click-blink
detection), not a low-level input hook.

Phase 2, not built yet, is where this connects to agent_brain.py: instead of replaying
fixed pixel coordinates, a real AgentBrain could take a screenshot at each recorded step
and use an LLM to locate the analogous on-screen target, so a skill still works after a
window moves or content shifts slightly.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QThread

from . import native

SKILLS_DIR = Path(__file__).parent / "skills_data"


@dataclass
class RecordedEvent:
    t: float  # seconds since recording started
    kind: str  # "move" | "click"
    x: int
    y: int


class SkillRecorder:
    """Call poll() every tick (e.g. from the same timer already driving eye tracking)
    while recording is active; it's a no-op cost-wise to call it every 16ms since it just
    compares against the last recorded position."""

    def __init__(self) -> None:
        self.events: list[RecordedEvent] = []
        self._start_time = 0.0
        self._last_pos: tuple[int, int] | None = None
        self._was_down = False

    def start(self) -> None:
        self.events = []
        self._start_time = time.monotonic()
        self._last_pos = None
        self._was_down = False

    def poll(self, x: int, y: int) -> None:
        t = time.monotonic() - self._start_time
        pos = (x, y)
        if pos != self._last_pos:
            self.events.append(RecordedEvent(t, "move", x, y))
            self._last_pos = pos

        # Reads the live button state directly rather than distinguishing real vs.
        # hand-gesture-injected clicks -- a demonstration should capture whatever
        # actually happened, regardless of source.
        is_down = native.is_left_button_down()
        if is_down and not self._was_down:
            self.events.append(RecordedEvent(t, "click", x, y))
        self._was_down = is_down

    def save(self, name: str) -> Path:
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        path = SKILLS_DIR / f"{_safe_filename(name)}.json"
        path.write_text(json.dumps([asdict(e) for e in self.events], indent=2))
        return path


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or "unnamed"


def list_skills() -> list[str]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(path.stem for path in SKILLS_DIR.glob("*.json"))


def load_skill(name: str) -> list[RecordedEvent]:
    path = SKILLS_DIR / f"{_safe_filename(name)}.json"
    data = json.loads(path.read_text())
    return [RecordedEvent(**d) for d in data]


def replay_skill(events: list[RecordedEvent], speed: float = 1.0) -> None:
    """Blocking -- sleeps between events to reproduce the original timing (divided by
    speed). Call this from a background thread, never the Qt GUI thread."""
    last_t = 0.0
    for event in events:
        delay = (event.t - last_t) / speed
        if delay > 0:
            time.sleep(delay)
        last_t = event.t

        if event.kind == "move":
            native.move_to(event.x, event.y)
        elif event.kind == "click":
            native.click_at(event.x, event.y)


class SkillReplayThread(QThread):
    """Runs replay_skill() on a background thread so its blocking time.sleep() calls
    between events never stall the Qt GUI thread. Connect to the inherited `finished`
    signal (thread-safe, built into QThread) to know when playback is done."""

    def __init__(self, events: list[RecordedEvent], speed: float = 1.0, parent=None) -> None:
        super().__init__(parent)
        self._events = events
        self._speed = speed

    def run(self) -> None:
        replay_skill(self._events, self._speed)
